"""Tests for the measured live-run harness (``router.measure``, BOLT Phase 0).

Network-free: every run is driven through a scripted fake :class:`MeasureClient`
so the dry-run estimate, snapshot layout (§3), deterministic replay, budget
guard, 429 retry accounting, prereg gate (D8), resume, honest ``measured``
labels and the range-contract validator are all pinned without egress.
"""

from __future__ import annotations

import itertools
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from router import cli
from router.measure import (
    AttemptResult,
    MeasureCandidate,
    MeasuredContract,
    PreregDecision,
    RetryPolicy,
    compute_summary,
    estimate_dry_run,
    evaluate_prereg,
    format_dry_run_table,
    load_prompt_workload,
    replay_measure,
    run_measure,
    verify_contract,
    workload_fingerprint,
)
from router.pricing import PricingTable

PRICING = Path("samples/pricing/foundry-5series.yaml")
WORKLOAD = Path("samples/telemetry/curated-arena-live.sample.jsonl")


def _pricing() -> PricingTable:
    return PricingTable.from_yaml(PRICING)


def _workload() -> dict[str, dict]:
    return load_prompt_workload(WORKLOAD)


def _candidates() -> list[MeasureCandidate]:
    return [
        MeasureCandidate("gpt-5.4-nano", "gpt-5.4-nano"),
        MeasureCandidate("gpt-5.4", "gpt-5.4"),
    ]


def _fixed_clock():
    counter = itertools.count()
    return lambda: f"2026-07-26T00:00:{next(counter) % 60:02d}.000000+00:00"


def _prereg() -> PreregDecision:
    return PreregDecision(
        True, "abc123", "2026-07-25T00:00:00+00:00", "prereg committed before run"
    )


class ScriptedClient:
    """Deterministic fake: fixed usage/latency, optional 429 script per cell."""

    def __init__(self, *, throttle: dict[tuple[str, str], int] | None = None, provenance="live",
                 always_429: bool = False):
        self.throttle = dict(throttle or {})
        self.provenance = provenance
        self.always_429 = always_429
        self.calls: list[tuple[str, str]] = []

    def attempt(self, *, deployment, provider, task):
        key = (deployment, task["task_id"])
        self.calls.append(key)
        if self.always_429:
            return AttemptResult(http_status=429, latency_ms=1.0, provenance=self.provenance)
        remaining = self.throttle.get(key, 0)
        if remaining > 0:
            self.throttle[key] = remaining - 1
            return AttemptResult(http_status=429, latency_ms=1.0, provenance=self.provenance)
        usage = task.get("tokens") or {
            "input": 1000, "cached": 200, "output": 500, "reasoning": 100
        }
        return AttemptResult(
            http_status=200, model=deployment, usage=usage, latency_ms=12.3,
            provenance=self.provenance,
        )


def _run(tmp_path, client, **kwargs):
    defaults = dict(
        client=client, pricing=_pricing(), exp_id="curated",
        run_dir=tmp_path / "curated" / "RUN", run_id="RUN", n=2,
        retry=RetryPolicy(max_retries=3, base_backoff_ms=1.0),
        sleeper=lambda _s: None, clock=_fixed_clock(),
        now=datetime(2026, 7, 26, tzinfo=UTC), prereg=_prereg(),
    )
    defaults.update(kwargs)
    workload = defaults.pop("workload", _workload())
    candidates = defaults.pop("candidates", _candidates())
    return run_measure(workload, candidates, **defaults)


# --------------------------------------------------------------------------- #
# Dry-run estimate (no live calls)
# --------------------------------------------------------------------------- #


def test_dry_run_estimate_counts_and_budget():
    estimate = estimate_dry_run(_workload(), _candidates(), n=3, pricing=_pricing())
    assert estimate["tasks"] == 5
    assert estimate["candidates"] == 2
    assert estimate["calls"] == 5 * 2 * 3
    assert estimate["labels"]["measured"] is False
    assert estimate["est_total_usd"] > 0
    table = format_dry_run_table(estimate, budget_usd=estimate["est_total_usd"] + 1)
    assert "within budget" in table
    assert "NO live calls" in table
    over = format_dry_run_table(estimate, budget_usd=0.0)
    assert "OVER BUDGET" in over


# --------------------------------------------------------------------------- #
# Snapshot layout (§3) + honest labels
# --------------------------------------------------------------------------- #


def test_run_writes_full_snapshot(tmp_path):
    result = _run(tmp_path, ScriptedClient())
    run_dir = result.run_dir
    for name in (
        "manifest.json", "prereg.md", "traces.jsonl", "summary.json", "pricing.snapshot.yaml"
    ):
        assert (run_dir / name).is_file(), name
    # one trace row per (task × repeat × candidate) with no throttling
    rows = [json.loads(line) for line in (run_dir / "traces.jsonl").read_text().splitlines()]
    assert len(rows) == 5 * 2 * 2
    row = rows[0]
    for field in ("run_id", "exp_id", "task_id", "repeat_idx", "candidate_model", "attempt_idx",
                  "tokens", "latency_ms", "http_status", "retries", "backoff_ms_total",
                  "cost_usd", "pass", "score", "fail_reason", "labels", "ts"):
        assert field in row, field
    assert set(row["tokens"]) == {"input", "cached", "output", "reasoning"}
    # manifest fingerprints cover every payload file
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert set(manifest["fingerprints"]) == {
        "traces.jsonl", "summary.json", "pricing.snapshot.yaml", "prereg.md"
    }
    assert manifest["n"] == 2
    assert manifest["prereg"]["commit_hash"] == "abc123"
    assert manifest["labels"]["measured"] is True
    # D14: the input workload identity is sealed alongside the outputs
    assert manifest["schema_version"] == 2
    assert manifest["workload_fingerprint"] == workload_fingerprint(_workload())
    assert manifest["workload_fingerprint"].startswith("sha256:")


def test_workload_fingerprint_tracks_prompt_changes(tmp_path):
    base = {
        "t-0001": {"task_id": "t-0001", "class": "generate", "user_prompt": "write a foo"},
        "t-0002": {"task_id": "t-0002", "class": "validate", "user_prompt": "check the bar"},
    }
    same = {  # same content, different insertion order → same fingerprint
        "t-0002": {"class": "validate", "task_id": "t-0002", "user_prompt": "check the bar"},
        "t-0001": {"class": "generate", "task_id": "t-0001", "user_prompt": "write a foo"},
    }
    changed = json.loads(json.dumps(base))
    changed["t-0001"]["user_prompt"] = "write a foo differently"

    fp = workload_fingerprint(base)
    assert fp.startswith("sha256:")
    assert workload_fingerprint(same) == fp  # order-insensitive, content-identical
    assert workload_fingerprint(changed) != fp  # a changed prompt → a different experiment


def test_measured_label_true_only_for_live_provenance(tmp_path):
    live = _run(tmp_path / "a", ScriptedClient(provenance="live"))
    assert live.summary["labels"]["measured"] is True
    recorded = _run(tmp_path / "b", ScriptedClient(provenance="recorded"))
    assert recorded.summary["labels"]["measured"] is False


def test_summary_ungraded_without_grader(tmp_path):
    result = _run(tmp_path, ScriptedClient())
    assert result.summary["coverage"] is None
    assert result.summary["labels"]["accuracy"] == "ungraded"


def test_summary_graded_with_grader(tmp_path):
    # grade nano as fail, gpt-5.4 as pass → coverage 0.5
    def grader(task_id, task, model, usage):
        return model == "gpt-5.4"

    result = _run(tmp_path, ScriptedClient(), grader=grader)
    cov = result.summary["coverage"]
    assert cov is not None
    assert cov["basis"] == "graded"
    assert cov["coverage"] == pytest.approx(0.5)
    assert result.summary["labels"]["accuracy"] == "graded"


# --------------------------------------------------------------------------- #
# Deterministic replay (§3.4)
# --------------------------------------------------------------------------- #


def test_replay_is_byte_identical(tmp_path):
    result = _run(tmp_path, ScriptedClient())
    report = replay_measure(result.run_dir)
    assert report.ok
    assert report.summary_matches
    assert report.fingerprints_ok
    assert report.cost_mismatches == ()


def test_two_runs_produce_identical_traces(tmp_path):
    a = _run(tmp_path / "a", ScriptedClient())
    b = _run(tmp_path / "b", ScriptedClient())
    assert (a.run_dir / "traces.jsonl").read_bytes() == (b.run_dir / "traces.jsonl").read_bytes()
    assert (a.run_dir / "summary.json").read_bytes() == (b.run_dir / "summary.json").read_bytes()


def test_replay_detects_tampering(tmp_path):
    result = _run(tmp_path, ScriptedClient())
    traces_path = result.run_dir / "traces.jsonl"
    lines = traces_path.read_text().splitlines()
    tampered = json.loads(lines[0])
    tampered["cost_usd"] = 999.0
    lines[0] = json.dumps(tampered, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    traces_path.write_text("\n".join(lines) + "\n")
    report = replay_measure(result.run_dir)
    assert not report.ok
    # either the fingerprint breaks or the recomputed cost no longer matches
    assert (not report.fingerprints_ok) or report.cost_mismatches


# --------------------------------------------------------------------------- #
# Budget guard (partial snapshot)
# --------------------------------------------------------------------------- #


def test_budget_guard_halts_and_marks_partial(tmp_path):
    result = _run(tmp_path, ScriptedClient(), budget_usd=0.02)
    assert result.partial is True
    assert result.summary["labels"]["partial"] is True
    assert result.manifest["partial"] is True
    assert "budget cap reached" in (result.stopped_reason or "")
    # a partial snapshot must still replay clean
    assert replay_measure(result.run_dir).ok
    # and it stopped before running the full 20-cell sweep
    assert result.summary["attempts"] < 5 * 2 * 2


# --------------------------------------------------------------------------- #
# 429 retry accounting (§3.2 / D6)
# --------------------------------------------------------------------------- #


def test_429_retry_records_one_row_per_attempt(tmp_path):
    # nano on t-0001 gets one 429 then succeeds
    client = ScriptedClient(throttle={("gpt-5.4-nano", "t-0001"): 1})
    result = _run(tmp_path, client)
    rows = [json.loads(line) for line in (result.run_dir / "traces.jsonl").read_text().splitlines()]
    cell = [r for r in rows if r["candidate_model"] == "gpt-5.4-nano"
            and r["task_id"] == "t-0001" and r["repeat_idx"] == 1]
    assert len(cell) == 2  # one 429 attempt row + one success row
    assert cell[0]["http_status"] == 429
    assert cell[0]["fail_reason"] == "throttled_429"
    assert cell[1]["http_status"] == 200
    assert cell[1]["retries"] == 1
    assert cell[1]["backoff_ms_total"] > 0
    throttle = result.summary["throttle"]
    assert throttle["http_429"] == 1
    assert throttle["retries"] == 1
    assert throttle["throttle_exhausted"] == 0


def test_throttle_exhaustion_is_a_recorded_failure(tmp_path):
    client = ScriptedClient(always_429=True)
    result = _run(
        tmp_path, client, workload={"t-0001": _workload()["t-0001"]},
        candidates=[MeasureCandidate("gpt-5.4-nano", "gpt-5.4-nano")],
        n=1, retry=RetryPolicy(max_retries=2, base_backoff_ms=1.0),
    )
    rows = [json.loads(line) for line in (result.run_dir / "traces.jsonl").read_text().splitlines()]
    assert len(rows) == 3  # 3 attempts, all 429
    assert rows[-1]["fail_reason"] == "throttle_exhausted"
    assert result.summary["calls"] == 0
    assert result.summary["throttle"]["throttle_exhausted"] == 1
    assert len(result.summary["failures"]) == 3
    assert replay_measure(result.run_dir).ok


def test_http_error_is_non_retryable_failure(tmp_path):
    class ErrorClient:
        def attempt(self, *, deployment, provider, task):
            return AttemptResult(http_status=400, latency_ms=1.0, error="bad request")

    result = _run(
        tmp_path, ErrorClient(), workload={"t-0001": _workload()["t-0001"]},
        candidates=[MeasureCandidate("gpt-5.4", "gpt-5.4")], n=1,
    )
    rows = [json.loads(line) for line in (result.run_dir / "traces.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["fail_reason"] == "http_400"
    assert result.summary["throttle"]["http_429"] == 0


# --------------------------------------------------------------------------- #
# prereg gate (D8)
# --------------------------------------------------------------------------- #


def test_prereg_gate_refuses_uncommitted(tmp_path):
    pf = tmp_path / "prereg.md"
    pf.write_text("expected coverage ~1.0\n")
    started = datetime.now(UTC)
    decision = evaluate_prereg(pf, run_started_at=started, committed_at_fn=lambda _p: None)
    assert decision.allowed is False


def test_prereg_gate_bypass_is_recorded(tmp_path):
    pf = tmp_path / "prereg.md"
    pf.write_text("x\n")
    decision = evaluate_prereg(
        pf, run_started_at=datetime.now(UTC), allow_no_prereg=True, committed_at_fn=lambda _p: None
    )
    assert decision.allowed is True
    assert decision.bypassed is True


def test_prereg_gate_requires_commit_before_run(tmp_path):
    pf = tmp_path / "prereg.md"
    pf.write_text("expected coverage ~1.0\n")
    started = datetime(2026, 7, 26, tzinfo=UTC)
    after = evaluate_prereg(
        pf, run_started_at=started,
        committed_at_fn=lambda _p: ("h", "2026-07-27T00:00:00+00:00"),
    )
    assert after.allowed is False
    before = evaluate_prereg(
        pf, run_started_at=started,
        committed_at_fn=lambda _p: ("hash9", "2026-07-25T00:00:00+00:00"),
    )
    assert before.allowed is True
    assert before.commit_hash == "hash9"


# --------------------------------------------------------------------------- #
# Resume / checkpoint
# --------------------------------------------------------------------------- #


def test_resume_completes_remaining_cells(tmp_path):
    run_dir = tmp_path / "curated" / "RUN"
    # first pass halts on budget after a couple of cells
    first = _run(tmp_path, ScriptedClient(), run_dir=run_dir, budget_usd=0.02)
    assert first.partial is True
    done_after_first = first.summary["attempts"]
    # resume the same run id with no budget → finishes the sweep
    second = _run(tmp_path, ScriptedClient(), run_dir=run_dir, resume=True, budget_usd=None)
    assert second.partial is False
    assert second.summary["attempts"] == 5 * 2 * 2
    assert second.summary["attempts"] > done_after_first
    assert replay_measure(second.run_dir).ok


# --------------------------------------------------------------------------- #
# Measured range-contract (§7.2)
# --------------------------------------------------------------------------- #


def test_contract_pass_and_fail(tmp_path):
    result = _run(tmp_path, ScriptedClient())
    summary = result.summary
    ok = verify_contract(summary, MeasuredContract(min_savings_pct=10.0, max_failure_rate=0.5))
    assert all(c.ok for c in ok if c.name != "freshness")
    bad = verify_contract(summary, MeasuredContract(min_savings_pct=99.9))
    assert any(c.name == "savings_floor" and not c.ok for c in bad)


def test_contract_freshness_warns_on_stale(tmp_path):
    result = _run(tmp_path, ScriptedClient())
    stale_manifest = {"timestamp": "2000-01-01T00:00:00+00:00"}
    checks = verify_contract(result.summary, MeasuredContract(), manifest=stale_manifest)
    fresh = [c for c in checks if c.name == "freshness"]
    assert fresh and fresh[0].ok is False and "STALE" in fresh[0].detail


def test_contract_coverage_floor_needs_grader(tmp_path):
    result = _run(tmp_path, ScriptedClient())  # ungraded
    checks = verify_contract(result.summary, MeasuredContract(min_coverage=0.9))
    coverage = [c for c in checks if c.name == "coverage_floor"]
    assert coverage and coverage[0].ok is False


# --------------------------------------------------------------------------- #
# CLI surface
# --------------------------------------------------------------------------- #


def test_cli_measure_run_dry_run_gate(capsys):
    code = cli.main([
        "measure", "run", "curated",
        "--candidates", "gpt-5.4-nano,gpt-5.4", "--n", "3", "--budget-usd", "5",
    ])
    assert code == 2  # no --live → estimate-only gate
    out = capsys.readouterr().out
    assert "dry-run cost estimate" in out
    assert "no live calls were made" in out


def test_cli_measure_replay_and_verify(tmp_path, capsys):
    result = _run(tmp_path, ScriptedClient())
    code = cli.main(["measure", "replay", "--run", str(result.run_dir)])
    assert code == 0
    assert "status: PASS" in capsys.readouterr().out

    contract = tmp_path / "contract.yaml"
    contract.write_text("expect:\n  min_savings_pct: 10\n  max_failure_rate: 0.5\n")
    code = cli.main(
        ["measure", "verify", "--run", str(result.run_dir), "--contract", str(contract)]
    )
    assert code == 0
    assert "status: PASS" in capsys.readouterr().out


def test_cli_measure_replay_fails_on_tamper(tmp_path, capsys):
    result = _run(tmp_path, ScriptedClient())
    summary_path = result.run_dir / "summary.json"
    data = json.loads(summary_path.read_text())
    data["cost"]["total_usd"] = 42.0
    summary_path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    code = cli.main(["measure", "replay", "--run", str(result.run_dir)])
    assert code == 1
    assert "status: FAIL" in capsys.readouterr().out


def test_compute_summary_is_pure_and_order_stable():
    pricing = _pricing()
    traces = [
        {"task_id": "t1", "repeat_idx": 1, "candidate_model": "gpt-5.4-nano", "attempt_idx": 1,
         "http_status": 200, "retries": 0, "backoff_ms_total": 0.0, "latency_ms": 10.0,
         "cost_usd": pricing.cost_usd("gpt-5.4-nano", {"input": 100, "output": 50}),
         "tokens": {"input": 100, "cached": 0, "output": 50, "reasoning": 0},
         "pass": None, "score": None, "fail_reason": None, "labels": {"measured": True}},
    ]
    a = compute_summary(traces, pricing, exp_id="e", run_id="r", n=1,
                        task_ids=["t1"], candidate_models=["gpt-5.4-nano"], partial=False)
    b = compute_summary(traces, pricing, exp_id="e", run_id="r", n=1,
                        task_ids=["t1"], candidate_models=["gpt-5.4-nano"], partial=False)
    assert a == b
    assert a["integrity"]["cost_mismatches"] == []
