"""Experiment 04 — the honest boundary: "there is no free lunch."

``experiments/limits.yaml`` routes a curated set of genuinely hard tasks where,
for every task, only the most expensive candidate passes the offline checks.
Cost-aware routing tries the cheap models, watches them fail, and escalates to
the top model on every task: routing == the naive arm, so savings are exactly
zero while coverage stays full.

These tests pin the exact deterministic numbers cited in the lab notebook and
exercise the two-sided reproducibility contract (``max_delta_pct``) so neither
the fixture nor the ceiling guard can silently drift.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from router.experiment import Expectation, load_experiment, run_experiment


def _result():
    return run_experiment(load_experiment("limits"))


def test_limits_keeps_full_coverage_with_zero_savings() -> None:
    result = _result()
    summary = result.summary
    assert summary["coverage"] == pytest.approx(1.0)
    assert summary["delta_pct"] == pytest.approx(0.0)
    assert summary["tasks"] == 6
    # Routing lands on exactly the naive (most-expensive) bill — no free lunch.
    assert summary["total_cost_usd"] == pytest.approx(0.236785, abs=1e-6)
    assert summary["baseline_total_usd"] == pytest.approx(0.236785, abs=1e-6)
    assert summary["delta_usd"] == pytest.approx(0.0, abs=1e-6)


def test_limits_escalates_every_task_to_the_top_model() -> None:
    result = _result()
    # Every task escalates above its cheapest candidate…
    assert result.summary["escalated_tasks"] == 6
    # …and for each task only the last (most-expensive) candidate is accepted.
    for trace in result.report.traces:
        attempts = trace["attempts"]
        accepted = [a["model"] for a in attempts if a["accepted"]]
        assert accepted == [attempts[-1]["model"]]
        assert trace["chosen"] == attempts[-1]["model"]


def test_limits_two_sided_contract_passes() -> None:
    result = _result()
    assert result.ok is True
    names = {check.name for check in result.checks}
    # The ceiling check only appears because limits sets max_delta_pct.
    assert "savings_ceiling" in names
    ceiling = next(c for c in result.checks if c.name == "savings_ceiling")
    assert ceiling.ok is True


def test_limits_has_no_spotlight() -> None:
    # No cheaper-model win exists to highlight — spotlight is disabled.
    assert _result().spotlight is None


def test_max_delta_pct_ceiling_catches_inflated_savings() -> None:
    # The hero run really does save ~25%. Capping savings at 0% must fail the
    # ceiling check — this is the guard against phantom/inflated savings claims.
    hero = load_experiment("hero")
    capped = replace(
        hero,
        expect=Expectation(min_coverage=0.0, min_delta_pct=0.0, min_tasks=1, max_delta_pct=0.0),
    )
    result = run_experiment(capped)
    ceiling = next(c for c in result.checks if c.name == "savings_ceiling")
    assert ceiling.ok is False
    assert result.ok is False


def test_expectation_max_delta_pct_round_trips() -> None:
    expect = Expectation.from_dict({"min_coverage": 1.0, "max_delta_pct": 0.0})
    assert expect.max_delta_pct == 0.0
    assert expect.to_dict()["max_delta_pct"] == 0.0
    # Unset ceiling stays None so existing experiments keep their three checks.
    assert Expectation.from_dict({}).max_delta_pct is None
