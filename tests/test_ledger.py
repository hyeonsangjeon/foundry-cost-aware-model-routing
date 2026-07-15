"""Phase A acceptance: task strata, single-call arms, and replayable audit ledger."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from policy import load_default_policy
from router import (
    BudgetGate,
    PricingTable,
    classify_task,
    load_workload,
    route_task,
    synthesize_task_signals,
)
from router.cli import main
from router.ledger import (
    JsonlLedger,
    LedgerRecord,
    build_ledger_record,
    record_completeness,
    verify_records,
)
from router.ledger.record import stable_hash
from router.pipeline import resolve_paths, run_replay, run_route_once

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = ROOT / "samples" / "telemetry" / "mixed-coding-workload.sample.jsonl"
SIGNALS = ROOT / "samples" / "responses" / "routing-signals.sample.json"
PRICING = ROOT / "samples" / "pricing" / "illustrative.yaml"


def _synth(*, ledger_path: Path | None = None):
    return run_replay(
        workload_path=WORKLOAD,
        pricing_path=PRICING,
        synth=True,
        ledger_path=ledger_path,
    )


def test_trace_profiles_stratify_the_full_synth_workload() -> None:
    report = _synth()
    assert all(trace["difficulty"] in {"easy", "medium", "hard"} for trace in report.traces)
    assert all(trace["risk"] in {"low", "moderate", "high"} for trace in report.traces)
    assert report.summary["strata"] == {
        "by_risk": {
            "high": {"tasks": 32, "accepted": 32, "cost_usd": 1.228623},
            "low": {"tasks": 26, "accepted": 26, "cost_usd": 0.063457},
            "moderate": {"tasks": 42, "accepted": 42, "cost_usd": 0.367087},
        },
        "by_difficulty": {
            "easy": {"tasks": 37, "accepted": 37, "cost_usd": 0.17243},
            "hard": {"tasks": 22, "accepted": 22, "cost_usd": 0.630214},
            "medium": {"tasks": 41, "accepted": 41, "cost_usd": 0.856523},
        },
    }


def test_single_call_baseline_arms_are_pinned() -> None:
    arms = _synth().summary["baseline_arms"]
    assert {
        arm: {
            "selection": stats["selection"],
            "tasks": stats["tasks"],
            "accepted": stats["accepted"],
            "coverage": stats["coverage"],
            "total_cost_usd": stats["total_cost_usd"],
        }
        for arm, stats in arms.items()
    } == {
        "cost": {
            "selection": "cheapest-candidate",
            "tasks": 100,
            "accepted": 22,
            "coverage": 0.22,
            "total_cost_usd": 0.187913,
        },
        "balanced": {
            "selection": "middle-candidate",
            "tasks": 100,
            "accepted": 38,
            "coverage": 0.38,
            "total_cost_usd": 1.323157,
        },
        "quality": {
            "selection": "most-expensive-candidate",
            "tasks": 100,
            "accepted": 100,
            "coverage": 1.0,
            "total_cost_usd": 2.22691,
        },
    }
    assert all(
        stats["labels"] == {"measured": False, "equivalent": "illustrative"}
        for stats in arms.values()
    )


def test_synth_replay_writes_and_verifies_complete_ledger(tmp_path: Path) -> None:
    ledger_path = tmp_path / "audit" / "routing.jsonl"
    report = _synth(ledger_path=ledger_path)
    ledger = report.summary["ledger"]

    assert ledger == {
        "path": str(ledger_path),
        "appended": 100,
        "records": 100,
        "matched": 100,
        "completeness": 1.0,
        "mismatches": [],
        "ok": True,
    }
    records = JsonlLedger(ledger_path).read_all()
    assert len(records) == 100
    assert all(record_completeness(record) == 1.0 for record in records)
    assert {record.aggregation["method"] for record in records} == {"ordered", "compare"}
    assert all(record.labels == {"measured": False, "offline": True} for record in records)
    assert all(record.task["risk"] in {"low", "moderate", "high"} for record in records)
    assert records[0].previous_hash is None
    assert all(
        record.previous_hash == records[index - 1].record_hash
        for index, record in enumerate(records[1:], start=1)
    )
    assert all(record.cost["billing_basis"] == "selected-execution-only" for record in records)


def test_ledger_output_is_deterministic_across_files(tmp_path: Path) -> None:
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    _synth(ledger_path=first)
    _synth(ledger_path=second)
    assert first.read_bytes() == second.read_bytes()


def test_ledger_is_append_only_across_replay_and_route_once(tmp_path: Path) -> None:
    ledger_path = tmp_path / "routing.jsonl"
    _synth(ledger_path=ledger_path)
    prefix = ledger_path.read_bytes()
    paths = resolve_paths(root=ROOT)
    run_route_once(
        task_id="t-0001",
        workload_path=paths["workload"],
        pricing_path=paths["pricing"],
        synth=True,
        ledger_path=ledger_path,
    )
    assert ledger_path.read_bytes().startswith(prefix)
    report = verify_records(JsonlLedger(ledger_path).read_all())
    assert report.records == report.matched == 101
    assert report.completeness == 1.0
    assert report.ok is True


def test_tampered_final_is_reported_as_replay_mismatch(tmp_path: Path) -> None:
    ledger_path = tmp_path / "routing.jsonl"
    _synth(ledger_path=ledger_path)
    record = JsonlLedger(ledger_path).read_all()[0]
    final = {**record.final, "chosen_model": "premium-max"}
    tampered = replace(record, final=final, record_hash="").with_previous_hash(
        record.previous_hash
    )

    report = verify_records([tampered])
    assert report.ok is False
    assert report.matched == 0
    assert report.mismatches[0]["request_hash"] == record.request_hash
    assert report.mismatches[0]["expected"]["chosen_model"] == "premium-max"
    assert report.mismatches[0]["actual"]["chosen_model"] != "premium-max"


def test_replay_detects_contradictory_gate_order_cost_and_candidate_flags(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "routing.jsonl"
    _synth(ledger_path=ledger_path)
    record = JsonlLedger(ledger_path).read_all()[0]
    raw_candidates = [dict(item) for item in record.raw_candidates]
    raw_candidates[0]["accepted"] = not raw_candidates[0]["accepted"]
    tampered = replace(
        record,
        gate_decision={**record.gate_decision, "selection_mode": "compare"},
        aggregation={
            **record.aggregation,
            "candidate_order": list(reversed(record.aggregation["candidate_order"])),
        },
        raw_candidates=raw_candidates,
        cost={**record.cost, "total_usd": 999.0},
        record_hash="",
    ).with_previous_hash(record.previous_hash)

    report = verify_records([tampered])
    assert report.ok is False
    issues = set(report.mismatches[0]["issues"])
    assert {
        "gate_decision",
        "aggregation.candidate_order",
        "raw_candidates[0].accepted",
        "cost.total_usd",
    } <= issues


def test_replay_detects_currency_relabeling(tmp_path: Path) -> None:
    ledger_path = tmp_path / "routing.jsonl"
    _synth(ledger_path=ledger_path)
    record = JsonlLedger(ledger_path).read_all()[0]
    tampered = replace(
        record,
        cost={**record.cost, "currency": "EUR"},
        record_hash="",
    ).with_previous_hash(record.previous_hash)
    report = verify_records([tampered])
    assert report.ok is False
    assert "cost.currency" in report.mismatches[0]["issues"]


def test_replay_uses_recorded_gate_config_not_current_defaults() -> None:
    policy = load_default_policy()
    workload = load_workload(WORKLOAD)
    task = workload["t-0001"]
    candidates = policy.candidates_for(classify_task(task))
    signals = synthesize_task_signals(task, candidates)
    pricing = PricingTable.from_yaml(PRICING)
    custom_gate = BudgetGate(compare_min_value=0.0)
    trace = route_task(
        task,
        signals,
        policy=policy,
        pricing=pricing,
        budget_gate=custom_gate,
    )
    record = build_ledger_record(
        task=task,
        signals_by_model=signals,
        trace=trace,
        policy=policy,
        pricing=pricing,
        signal_kind="synth",
        budget_gate=custom_gate,
    )
    report = verify_records([record])
    assert record.gate_decision["config"]["compare_min_value"] == 0.0
    assert record.aggregation["method"] == "compare"
    assert report.ok is True


def test_payload_tamper_without_resealing_is_rejected(tmp_path: Path) -> None:
    ledger_path = tmp_path / "routing.jsonl"
    _synth(ledger_path=ledger_path)
    payload = JsonlLedger(ledger_path).read_all()[0].to_dict()
    payload["cost"]["total_usd"] = 999.0
    with pytest.raises(ValueError, match="record_hash does not match"):
        LedgerRecord.from_dict(payload)


def test_unknown_top_level_field_is_rejected(tmp_path: Path) -> None:
    ledger_path = tmp_path / "routing.jsonl"
    _synth(ledger_path=ledger_path)
    payload = JsonlLedger(ledger_path).read_all()[0].to_dict()
    payload["forged_top_level"] = True
    with pytest.raises(ValueError, match="unknown ledger schema-v1 fields"):
        LedgerRecord.from_dict(payload)


def test_forged_provenance_and_backend_cardinality_are_rejected(tmp_path: Path) -> None:
    ledger_path = tmp_path / "routing.jsonl"
    _synth(ledger_path=ledger_path)
    record = JsonlLedger(ledger_path).read_all()[0]

    with pytest.raises(ValueError, match="policy_hash does not match"):
        replace(record, policy_hash="0" * 64, record_hash="").with_previous_hash(
            record.previous_hash
        )

    fake_backend = {
        "backend_id": "forged",
        "deployment_version": "synth-v1",
        "subset_hash": record.policy_hash,
        "selected_model": record.final["chosen_model"],
    }
    with pytest.raises(ValueError, match="exactly one offline backend"):
        replace(
            record,
            backends=[*record.backends, fake_backend],
            record_hash="",
        ).with_previous_hash(record.previous_hash)


def test_missing_nested_candidate_field_is_rejected_as_value_error(tmp_path: Path) -> None:
    ledger_path = tmp_path / "routing.jsonl"
    _synth(ledger_path=ledger_path)
    record = JsonlLedger(ledger_path).read_all()[0]
    raw_candidates = [dict(item) for item in record.raw_candidates]
    raw_candidates[0].pop("prior_pass")
    with pytest.raises(ValueError, match="raw candidate 0"):
        replace(
            record,
            raw_candidates=raw_candidates,
            record_hash="",
        ).with_previous_hash(record.previous_hash)


def test_invalid_task_token_shape_is_rejected_as_value_error(tmp_path: Path) -> None:
    ledger_path = tmp_path / "routing.jsonl"
    _synth(ledger_path=ledger_path)
    record = JsonlLedger(ledger_path).read_all()[0]
    with pytest.raises(ValueError, match="task tokens must be a mapping"):
        replace(
            record,
            task={**record.task, "tokens": "not-a-mapping"},
            record_hash="",
        ).with_previous_hash(record.previous_hash)


def test_invalid_jsonl_line_is_rejected_with_line_number(tmp_path: Path) -> None:
    ledger_path = tmp_path / "broken.jsonl"
    ledger_path.write_text("\nnot-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"broken\.jsonl:2"):
        JsonlLedger(ledger_path).read_all()


def test_append_handles_valid_final_record_without_newline(tmp_path: Path) -> None:
    ledger_path = tmp_path / "routing.jsonl"
    _synth(ledger_path=ledger_path)
    ledger_path.write_bytes(ledger_path.read_bytes().rstrip(b"\n"))
    paths = resolve_paths(root=ROOT)
    run_route_once(
        task_id="t-0001",
        workload_path=paths["workload"],
        pricing_path=paths["pricing"],
        synth=True,
        ledger_path=ledger_path,
    )
    records = JsonlLedger(ledger_path).read_all()
    assert len(records) == 101
    assert verify_records(records).ok is True


def test_unicode_line_separator_inside_json_string_is_not_a_record_boundary(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jsonl"
    _synth(ledger_path=source)
    record = JsonlLedger(source).read_all()[0]
    task = {**record.task, "domain": "left\u2028right"}
    unicode_record = replace(
        record,
        task=task,
        request_hash=stable_hash({"task": task}),
        previous_hash=None,
        record_hash="",
    ).with_previous_hash(None)

    ledger_path = tmp_path / "unicode.jsonl"
    JsonlLedger(ledger_path).append(unicode_record)
    records = JsonlLedger(ledger_path).read_all()
    assert len(records) == 1
    assert records[0].task["domain"] == "left\u2028right"
    assert verify_records(records).ok is True


def test_corrupt_existing_ledger_is_not_modified(tmp_path: Path) -> None:
    ledger_path = tmp_path / "corrupt.jsonl"
    ledger_path.write_text("not-json\n", encoding="utf-8")
    before = ledger_path.read_bytes()
    with pytest.raises(ValueError, match="invalid ledger JSON"):
        _synth(ledger_path=ledger_path)
    assert ledger_path.read_bytes() == before


def test_cli_records_then_replays_ledger(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ledger_path = tmp_path / "routing.jsonl"
    assert main(["replay", "--synth", "--ledger", str(ledger_path)]) == 0
    replay_out = capsys.readouterr().out
    assert f"ledger  path={ledger_path}" in replay_out
    assert "matched=100/100 completeness=100.0% status=PASS" in replay_out

    assert main(["ledger", "replay", "--ledger", str(ledger_path)]) == 0
    out = capsys.readouterr().out
    assert "records: 100" in out
    assert "matched: 100" in out
    assert "completeness: 100.0%" in out
    assert "status: PASS" in out


def test_cli_reports_corrupt_ledger_as_clean_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ledger_path = tmp_path / "broken.jsonl"
    ledger_path.write_text("not-json\n", encoding="utf-8")
    assert main(["ledger", "replay", "--ledger", str(ledger_path)]) == 1
    out = capsys.readouterr().out
    assert "invalid ledger JSON" in out
    assert "status: FAIL" in out


def test_cli_reports_non_object_json_as_clean_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ledger_path = tmp_path / "boolean.jsonl"
    ledger_path.write_text("true\n", encoding="utf-8")
    assert main(["ledger", "replay", "--ledger", str(ledger_path)]) == 1
    out = capsys.readouterr().out
    assert "ledger record must be a JSON object" in out
    assert "status: FAIL" in out
