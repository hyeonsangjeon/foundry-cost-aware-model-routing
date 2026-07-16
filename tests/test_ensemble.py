"""Pin the ensemble fan-out experiment's numbers and reproducibility contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from router.experiment import list_experiments, load_experiment, run_experiment

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)


def test_ensemble_is_registered() -> None:
    assert "ensemble" in [experiment.name for experiment in list_experiments()]


def test_ensemble_experiment_fields() -> None:
    ensemble = load_experiment("ensemble")
    assert ensemble.synth is False
    assert ensemble.signals is not None
    assert ensemble.expect.min_coverage == 1.0
    assert ensemble.expect.min_delta_pct == pytest.approx(0.40)
    assert ensemble.expect.min_tasks == 6


def test_ensemble_run_is_green_and_all_fan_out() -> None:
    result = run_experiment(load_experiment("ensemble"))
    summary = result.report.summary
    assert result.ok is True
    assert summary["tasks"] == 6
    assert summary["coverage"] == pytest.approx(1.0)
    assert summary["total_cost_usd"] == pytest.approx(0.132801, abs=1e-6)
    assert summary["baseline_total_usd"] == pytest.approx(0.250728, abs=1e-6)
    assert summary["delta_pct"] == pytest.approx(0.4703, abs=1e-4)
    assert summary["measured"] is False
    # every high-value task fans out to all candidates (compare mode)
    assert all(trace["mode"] == "compare" for trace in result.report.traces)


def test_ensemble_fanout_tax_is_surfaced() -> None:
    summary = run_experiment(load_experiment("ensemble")).report.summary
    fan = summary["fanout"]
    assert fan["ensemble_tasks"] == 6
    assert fan["single_tasks"] == 0
    assert fan["fanout_usd"] == pytest.approx(0.496812, abs=1e-6)
    assert fan["ensemble_tax_usd"] == pytest.approx(0.364011, abs=1e-6)
    assert fan["tax_ratio"] == pytest.approx(3.741, abs=1e-3)


def test_ensemble_spotlight_is_deterministic() -> None:
    spotlight = run_experiment(load_experiment("ensemble")).spotlight
    assert spotlight is not None
    assert spotlight.task_id == "t-0032"
    assert spotlight.accepted is True
    assert spotlight.naive_usd > spotlight.routed_usd > 0.0


def test_strategy_arms_include_ensemble_all() -> None:
    # the synthetic hero workload carries the full strategy frontier including
    # the fan-out-everything arm (most expensive at full coverage).
    summary = run_experiment(load_experiment("hero")).report.summary
    strategies = summary["strategies"]
    assert set(strategies) >= {"all_mini", "all_premium", "all_ensemble", "mix"}
    ens = strategies["all_ensemble"]
    prem = strategies["all_premium"]
    assert ens["coverage"] == pytest.approx(1.0)
    assert ens["total_cost_usd"] == pytest.approx(4.225226, abs=1e-6)
    # ensemble-everything is strictly more expensive than premium-everything
    assert ens["total_cost_usd"] > prem["total_cost_usd"]
