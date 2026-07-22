"""Pin the canonical measured audit (``router.ledger.measured``): the hash-chained,
cost-replayable ledger that gives real live-call rows the same integrity the
strict offline ledger has — tamper-evidence plus deterministic cost replay —
without ever touching the offline audit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from router import cli
from router.ledger import (
    MeasuredJsonlLedger,
    MeasuredLedgerRecord,
    verify_measured_ledger,
    verify_measured_records,
)
from router.ledger.measured import pricing_from_snapshot, pricing_snapshot
from router.pricing import PricingTable, TokenRates

CAPTURED_AT = "2026-07-26T00:00:00+00:00"


def _pricing() -> PricingTable:
    rates = TokenRates(input=1.0, cached=0.25, output=4.0, reasoning=4.0)
    return PricingTable(models={"m1": rates, "m2": rates}, default=rates, version=2)


def _outcome(cost: float = 0.003, *, model: str = "m1") -> dict:
    # usage {input:1000, output:500} priced at (1000*1 + 500*4)/1e6 = 0.003
    return {
        "task_id": "t-0",
        "title": "t",
        "prompt": "p",
        "arms": {
            "premium": {
                "arm": "premium",
                "strategy": "single",
                "deployment": "gpt",
                "chosen_model": model,
                "fanout": 1,
                "billing": "selected-execution-only",
                "cost_usd": cost,
                "latency_ms": 10.0,
                "calls": [
                    {
                        "deployment": "gpt",
                        "model": model,
                        "usage": {"input": 1000, "output": 500},
                        "latency_ms": 10.0,
                        "cost_usd": cost,
                        "provenance": "live",
                    }
                ],
            }
        },
        "winners": {"cost": "premium"},
        "labels": {"measured": True, "provenance": "live"},
    }


def _record(outcome: dict, pricing: PricingTable | None = None) -> MeasuredLedgerRecord:
    return MeasuredLedgerRecord.build(
        outcome, pricing=pricing or _pricing(), captured_at=CAPTURED_AT
    )


# -- the pricing snapshot round-trip ----------------------------------------


def test_pricing_snapshot_round_trips() -> None:
    pricing = _pricing()
    snapshot = pricing_snapshot(pricing, ["m1"])
    rebuilt = pricing_from_snapshot(snapshot)
    assert rebuilt.version == 2
    assert rebuilt.cost_usd("m1", {"input": 1000, "output": 500}) == pytest.approx(0.003)


# -- the record: build, seal, validate --------------------------------------


def test_build_seals_a_valid_hash_chained_record() -> None:
    record = _record(_outcome())
    assert record.schema_version == 1
    assert record.previous_hash is None
    assert len(record.record_hash) == 64
    assert len(record.pricing_hash) == 64
    assert set(record.pricing_snapshot["models"]) == {"m1"}  # only priced models pinned
    record.validate()  # does not raise


def test_from_dict_rejects_unknown_fields() -> None:
    payload = _record(_outcome()).to_dict()
    payload["surprise"] = 1
    with pytest.raises(ValueError, match="unknown measured ledger fields"):
        MeasuredLedgerRecord.from_dict(payload)


def test_validate_rejects_a_mismatched_record_hash() -> None:
    payload = _record(_outcome()).to_dict()
    payload["outcome"]["arms"]["premium"]["cost_usd"] = 999.0  # tamper, don't re-seal
    with pytest.raises(ValueError, match="record_hash"):
        MeasuredLedgerRecord.from_dict(payload)


def test_validate_rejects_a_mismatched_pricing_hash() -> None:
    payload = _record(_outcome()).to_dict()
    payload["pricing_snapshot"]["version"] = 99  # snapshot no longer hashes to pricing_hash
    with pytest.raises(ValueError, match="record_hash|pricing_hash"):
        MeasuredLedgerRecord.from_dict(payload)


def test_validate_requires_measured_label() -> None:
    outcome = _outcome()
    del outcome["labels"]["measured"]
    with pytest.raises(ValueError, match="labels must include 'measured'"):
        _record(outcome)


# -- the store: append, chain, read -----------------------------------------


def test_append_many_chains_across_flushes(tmp_path: Path) -> None:
    ledger = MeasuredJsonlLedger(tmp_path / "m.jsonl")
    first = ledger.append_many([_record(_outcome())])
    second = ledger.append_many([_record(_outcome())])
    assert first[0].previous_hash is None
    assert second[0].previous_hash == first[0].record_hash
    stored = ledger.read_all()
    assert [r.record_hash for r in stored] == [first[0].record_hash, second[0].record_hash]


def test_read_all_detects_a_broken_chain(tmp_path: Path) -> None:
    path = tmp_path / "m.jsonl"
    ledger = MeasuredJsonlLedger(path)
    ledger.append_many([_record(_outcome()), _record(_outcome())])
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["outcome"]["title"] = "edited"  # breaks this row's own record_hash
    path.write_text(json.dumps(first) + "\n" + lines[1] + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="record_hash|hash chain"):
        ledger.read_all()


# -- the verifier: deterministic cost replay --------------------------------


def test_verify_measured_ledger_replays_costs(tmp_path: Path) -> None:
    path = tmp_path / "m.jsonl"
    MeasuredJsonlLedger(path).append_many([_record(_outcome()), _record(_outcome(model="m2"))])
    report = verify_measured_ledger(path)
    assert report.ok
    assert report.records == 2
    assert report.replayed == 2
    assert report.to_dict()["mismatches"] == []


def test_verify_flags_a_cost_that_does_not_match_usage() -> None:
    # A record sealed with an internally-inconsistent cost: the hash is valid
    # (it was sealed over the wrong number), but cost replay catches the lie.
    dishonest = _record(_outcome(cost=0.009))  # real cost for this usage is 0.003
    dishonest.validate()  # hash is self-consistent, so validation passes
    report = verify_measured_records([dishonest])
    assert not report.ok
    assert report.replayed == 0
    assert report.mismatches[0]["issues"] == ["arms.premium.calls[0].cost_usd"]


def test_verify_empty_ledger_is_not_ok(tmp_path: Path) -> None:
    report = verify_measured_ledger(tmp_path / "missing.jsonl")
    assert not report.ok
    assert report.records == 0


# -- the CLI: `ledger measured-replay` --------------------------------------


def test_cli_measured_replay_passes_on_honest_ledger(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "m.jsonl"
    MeasuredJsonlLedger(path).append_many([_record(_outcome())])
    assert cli.main(["ledger", "measured-replay", "--ledger", str(path)]) == 0
    out = capsys.readouterr().out
    assert "replayed: 1" in out
    assert "status: PASS" in out


def test_cli_measured_replay_fails_on_tampered_ledger(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "m.jsonl"
    MeasuredJsonlLedger(path).append_many([_record(_outcome())])
    row = json.loads(path.read_text(encoding="utf-8"))
    row["outcome"]["arms"]["premium"]["cost_usd"] = 999.0  # tamper, don't re-seal
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert cli.main(["ledger", "measured-replay", "--ledger", str(path)]) == 1
    assert "status: FAIL" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# The committed experiment-10 sample: a durable, independently-verifiable audit
# of the measured live-arena run. These guard that the shipped ledger always
# replays PASS and stays byte-in-sync with its offline generator.
# --------------------------------------------------------------------------- #

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMITTED_SAMPLE = REPO_ROOT / "samples" / "ledger" / "arena-measured.ledger.jsonl"


def _load_sample_generator():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_measured_ledger_sample",
        REPO_ROOT / "scripts" / "build_measured_ledger_sample.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_measured_ledger_sample_replays_pass() -> None:
    report = verify_measured_ledger(COMMITTED_SAMPLE)
    assert report.records == 5
    assert report.replayed == report.records
    assert report.ok
    assert not report.mismatches


def test_committed_measured_ledger_sample_regenerates_byte_identical(tmp_path: Path) -> None:
    generator = _load_sample_generator()
    regenerated = tmp_path / "regenerated.ledger.jsonl"
    report = generator.build_measured_ledger(out_path=regenerated)
    assert report.ok
    assert regenerated.read_bytes() == COMMITTED_SAMPLE.read_bytes()


def test_cli_measured_replay_passes_on_committed_sample(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["ledger", "measured-replay", "--ledger", str(COMMITTED_SAMPLE)]) == 0
    out = capsys.readouterr().out
    assert "records: 5" in out
    assert "status: PASS" in out
