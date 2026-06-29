"""Tests for the deterministic base-vs-candidate regression report."""

from __future__ import annotations

from pathlib import Path

import pytest

from router.cli import main
from router.pipeline import regression_report

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = ROOT / "samples" / "telemetry" / "mixed-coding-workload.sample.jsonl"
PRICING = ROOT / "samples" / "pricing" / "illustrative.yaml"
SEED = ROOT / "src" / "policy" / "seed_policy.yaml"
CANDIDATE = ROOT / "samples" / "policy" / "candidate.example.yaml"


def _report() -> dict:
    return regression_report(
        workload_path=WORKLOAD,
        pricing_path=PRICING,
        candidate_policy_path=CANDIDATE,
        base_policy_path=SEED,
        synth=True,
    )


def test_regression_report_is_deterministic() -> None:
    assert _report() == _report()


def test_regression_candidate_cheaper_full_coverage() -> None:
    report = _report()
    assert report["base"]["tasks"] == 100
    assert report["candidate"]["tasks"] == 100
    assert report["candidate"]["coverage"] == 1.0
    assert report["candidate"]["routed_total_usd"] == 1.478647
    assert report["base"]["routed_total_usd"] == 1.659167
    assert report["cost_delta_usd"] == -0.18052
    assert report["coverage_delta"] == 0.0


def test_regression_report_has_required_fields() -> None:
    report = _report()
    for side in ("base", "candidate"):
        section = report[side]
        for key in ("tasks", "coverage", "accepted", "routed_total_usd",
                    "baseline_total_usd", "delta_usd", "delta_pct",
                    "mode_counts", "reason_counts", "by_class"):
            assert key in section
    assert "premium-max (removed)" in report["diff"]


def test_regression_cli_outputs_diff_and_deltas(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["policy", "regression", "--candidate", str(CANDIDATE), "--synth"]) == 0
    out = capsys.readouterr().out
    assert "policy diff v1 -> v2" in out
    assert "routed_total_usd" in out
    assert "delta" in out
