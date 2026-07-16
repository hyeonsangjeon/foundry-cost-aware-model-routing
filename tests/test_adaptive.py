"""Pin experiment 06 (adaptive fan-out dial): the budget lever, the zero-tax
contract, and the deterministic fan-out sweep behind the dashboard panel."""

from __future__ import annotations

from pathlib import Path

import pytest

from router.budget import BudgetGate
from router.experiment import list_experiments, load_experiment, run_experiment
from router.pipeline import bundled_fanout_sweep

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)


# -- the budget lever (experiment schema -> BudgetGate) ---------------------


def test_adaptive_is_registered() -> None:
    assert "adaptive" in [experiment.name for experiment in list_experiments()]


def test_adaptive_experiment_fields() -> None:
    adaptive = load_experiment("adaptive")
    assert adaptive.compare_min_value == pytest.approx(1.1)
    assert adaptive.min_compare_candidates == 2
    assert adaptive.expect.max_tax_ratio == pytest.approx(0.01)
    # shares experiment 05's workload/signals so the only change is the dial
    ensemble = load_experiment("ensemble")
    assert adaptive.workload == ensemble.workload
    assert adaptive.signals == ensemble.signals


def test_budget_gate_is_built_from_the_experiment() -> None:
    gate = load_experiment("adaptive").budget_gate()
    assert isinstance(gate, BudgetGate)
    assert gate.compare_min_value == pytest.approx(1.1)
    assert gate.min_compare_candidates == 2


def test_experiment_without_budget_uses_the_default_gate() -> None:
    # ensemble sets no budget block -> no override -> default gate (fans out)
    assert load_experiment("ensemble").budget_gate() is None


def test_to_dict_round_trips_the_budget_block() -> None:
    payload = load_experiment("adaptive").to_dict()
    assert payload["budget"] == {"compare_min_value": 1.1, "min_compare_candidates": 2}
    assert payload["expect"]["max_tax_ratio"] == pytest.approx(0.01)


# -- the honest result: same savings + coverage, zero tax -------------------


def test_adaptive_keeps_savings_and_coverage_but_zeroes_the_tax() -> None:
    adaptive = run_experiment(load_experiment("adaptive")).report.summary
    ensemble = run_experiment(load_experiment("ensemble")).report.summary
    # identical winner cost, coverage, and savings to the fan-out-everything run
    assert adaptive["total_cost_usd"] == pytest.approx(ensemble["total_cost_usd"], abs=1e-9)
    assert adaptive["coverage"] == pytest.approx(1.0)
    assert adaptive["delta_pct"] == pytest.approx(ensemble["delta_pct"], abs=1e-9)
    # …but the dial is OFF: nothing fans out, so the ensemble tax is zero
    fan = adaptive["fanout"]
    assert fan["ensemble_tasks"] == 0
    assert fan["single_tasks"] == 6
    assert fan["ensemble_tax_usd"] == pytest.approx(0.0)
    assert fan["tax_ratio"] == pytest.approx(0.0)
    assert all(trace["mode"] == "ordered" for trace in run_adaptive_traces())


def run_adaptive_traces() -> list:
    return run_experiment(load_experiment("adaptive")).report.traces


def test_adaptive_contract_is_green_including_the_tax_ceiling() -> None:
    result = run_experiment(load_experiment("adaptive"))
    assert result.ok is True
    names = {check.name for check in result.checks}
    assert "fanout_tax_ceiling" in names
    tax_check = next(c for c in result.checks if c.name == "fanout_tax_ceiling")
    assert tax_check.ok is True


def test_tax_ceiling_bites_when_fan_out_is_on() -> None:
    # applying the adaptive tax ceiling to the fan-out-everything ensemble must FAIL
    import dataclasses

    from router.experiment import _evaluate

    ensemble = load_experiment("ensemble")
    result = run_experiment(ensemble)
    strict = dataclasses.replace(ensemble.expect, max_tax_ratio=0.01)
    checks = _evaluate(result.report, strict)
    tax_check = next(c for c in checks if c.name == "fanout_tax_ceiling")
    assert tax_check.ok is False
    assert "3.74" in tax_check.detail


# -- the fan-out sweep behind the dashboard panel ---------------------------


def test_fanout_sweep_shape_and_determinism() -> None:
    first = bundled_fanout_sweep()
    second = bundled_fanout_sweep()
    assert first == second  # deterministic
    assert first["measured"] is False
    assert first["tasks"] == 6
    assert first["baseline_usd"] == pytest.approx(0.250728, abs=1e-6)
    assert len(first["rows"]) == 4
    for row in first["rows"]:
        assert set(row) >= {
            "threshold",
            "fanout_tasks",
            "single_tasks",
            "coverage",
            "routed_usd",
            "delta_pct",
            "fanout_usd",
            "ensemble_tax_usd",
            "tax_ratio",
        }


def test_fanout_sweep_collapses_tax_while_holding_savings_and_coverage() -> None:
    rows = bundled_fanout_sweep()["rows"]
    # coverage, routed winner cost, and savings are invariant across the dial
    assert {row["fanout_tasks"] for row in rows} == {6, 5, 1, 0}
    for row in rows:
        assert row["coverage"] == pytest.approx(1.0)
        assert row["routed_usd"] == pytest.approx(0.132801, abs=1e-6)
        assert row["delta_pct"] == pytest.approx(0.4703, abs=1e-4)
    # the tax strictly collapses as fewer tasks fan out, reaching exactly zero
    taxes = [row["ensemble_tax_usd"] for row in rows]
    assert taxes == sorted(taxes, reverse=True)
    assert taxes[0] == pytest.approx(0.364011, abs=1e-6)
    assert taxes[-1] == pytest.approx(0.0)
