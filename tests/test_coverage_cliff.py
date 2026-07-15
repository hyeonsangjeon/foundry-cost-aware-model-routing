"""Experiment 03 — the coverage cliff (:mod:`router.pipeline.regression_report`).

Deleting the expensive fallback models (``experiments/policies/cost-cut.yaml``)
looks cheaper but silently drops coverage. These tests pin the exact, honest,
deterministic numbers cited in the lab notebook so they cannot drift.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from policy import PolicyTable
from router.pipeline import regression_report

_ROOT = Path(__file__).resolve().parents[1]
_WORKLOAD = _ROOT / "samples" / "telemetry" / "mixed-coding-workload.sample.jsonl"
_PRICING = _ROOT / "samples" / "pricing" / "illustrative.yaml"
_COST_CUT = _ROOT / "experiments" / "policies" / "cost-cut.yaml"


def _report() -> dict:
    return regression_report(
        workload_path=_WORKLOAD,
        pricing_path=_PRICING,
        candidate_policy_path=_COST_CUT,
        base_policy_path=None,
        synth=True,
    )


def test_cost_cut_policy_is_valid() -> None:
    # A tempting-but-wrong policy is still a *valid* policy — the lesson is about
    # coverage, not schema. It must load and validate cleanly.
    PolicyTable.from_yaml(_COST_CUT).validate()


def test_cost_cut_collapses_coverage() -> None:
    report = _report()
    assert report["base"]["coverage"] == pytest.approx(1.0)
    assert report["candidate"]["coverage"] == pytest.approx(0.67)
    assert report["coverage_delta"] == pytest.approx(-0.33)


def test_cost_cut_looks_cheaper_only_by_dropping_work() -> None:
    report = _report()
    base = report["base"]["routed_total_usd"]
    cand = report["candidate"]["routed_total_usd"]
    assert base == pytest.approx(1.659167, abs=1e-6)
    assert cand == pytest.approx(0.727969, abs=1e-6)
    # Cheaper on paper …
    assert cand < base
    assert report["cost_delta_usd"] == pytest.approx(-0.931198, abs=1e-6)
    # … but only because coverage fell below the base's full coverage.
    assert report["candidate"]["coverage"] < report["base"]["coverage"]


def test_evaluation_uses_shared_synth_signals() -> None:
    report = _report()
    assert report["evaluation"] == {"signals": "shared-synth", "tasks": 100}
