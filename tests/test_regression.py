"""Tests for the deterministic base-vs-candidate regression report.

The regression guard scores the base and candidate policies on a single set of
shared synthetic signals (built from the union of both policies' candidates with
base-preferred priors). These tests pin that behaviour: a prior_pass-only change
must produce zero delta, and dropping an expensive fallback must surface the
coverage risk it creates instead of masking it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from router.cli import main
from router.pipeline import regression_report

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = ROOT / "samples" / "telemetry" / "mixed-coding-workload.sample.jsonl"
PRICING = ROOT / "samples" / "pricing" / "illustrative.yaml"
SEED = ROOT / "src" / "policy" / "seed_policy.yaml"
CANDIDATE = ROOT / "samples" / "policy" / "candidate.example.yaml"


def _report(candidate: Path = CANDIDATE) -> dict:
    return regression_report(
        workload_path=WORKLOAD,
        pricing_path=PRICING,
        candidate_policy_path=candidate,
        base_policy_path=SEED,
        synth=True,
    )


def _prior_only_candidate(tmp_path: Path) -> Path:
    """Seed policy with every prior_pass nudged up but models/order/cost intact."""

    data = yaml.safe_load(SEED.read_text())
    data["version"] = int(data.get("version", 1)) + 1
    for candidates in data["classes"].values():
        for cand in candidates:
            cand["prior_pass"] = round(min(cand["prior_pass"] + 0.05, 1.0), 4)
    out = tmp_path / "prior-only.candidate.yaml"
    out.write_text(yaml.safe_dump(data, sort_keys=False))
    return out


def test_regression_report_is_deterministic() -> None:
    assert _report() == _report()


def test_regression_uses_shared_evaluation_signals() -> None:
    report = _report()
    assert report["evaluation"] == {"signals": "shared-synth", "tasks": 100}


def test_regression_prior_pass_only_change_is_zero_delta(tmp_path: Path) -> None:
    # The shared signals are derived from base priors, so a candidate that only
    # raises prior_pass (same models/order/cost) routes exactly like base. This
    # catches the prior bug where per-policy synthesis let a prior_pass bump
    # inflate the candidate's signals and fake an improvement.
    report = _report(_prior_only_candidate(tmp_path))
    assert report["cost_delta_usd"] == 0.0
    assert report["coverage_delta"] == 0.0
    assert report["candidate"]["routed_total_usd"] == report["base"]["routed_total_usd"]
    assert report["candidate"]["coverage"] == report["base"]["coverage"] == 1.0


def test_regression_fallback_removal_surfaces_coverage_risk() -> None:
    # candidate.example.yaml drops premium-max from repo_patch. Under shared
    # signals the union still forces premium-max clean, so base keeps full
    # coverage while the candidate loses its guaranteed fallback -> the coverage
    # risk becomes visible instead of being hidden behind bumped priors.
    report = _report()
    assert report["base"]["tasks"] == 100
    assert report["candidate"]["tasks"] == 100
    assert report["base"]["coverage"] == 1.0
    assert report["candidate"]["coverage"] == 0.93
    assert report["coverage_delta"] == -0.07
    assert report["candidate"]["routed_total_usd"] == 1.337137
    assert report["base"]["routed_total_usd"] == 1.659167
    assert report["cost_delta_usd"] == -0.32203


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
    assert "shared" in out
    assert "routed_total_usd" in out
    assert "delta" in out

