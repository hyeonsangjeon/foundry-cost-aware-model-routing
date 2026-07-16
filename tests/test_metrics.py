"""Tests for the Foundry-shaped metrics common module (:mod:`router.metrics`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from router.experiment import load_experiment, run_experiment
from router.metrics import (
    SCHEMA_VERSION,
    ExperimentMetrics,
    FoundryMetricsEmitter,
    JsonlMetricsStore,
    extract_experiment_metrics,
    fanout_stats,
    record_experiment_metrics,
    utc_now_iso,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)


# -- fanout_stats -----------------------------------------------------------

def _compare_trace(chosen: str, attempts: list[tuple[str, float]]) -> dict:
    return {
        "mode": "compare",
        "chosen": chosen,
        "attempts": [{"model": m, "signals": {"cost_usd": c}} for m, c in attempts],
    }


def _ordered_trace(model: str, cost: float) -> dict:
    return {
        "mode": "ordered",
        "chosen": model,
        "attempts": [{"model": model, "signals": {"cost_usd": cost}}],
    }


def test_fanout_stats_sums_losers_as_tax() -> None:
    traces = [
        _compare_trace("mid", [("cheap", 0.01), ("mid", 0.02), ("top", 0.05)]),
        _ordered_trace("cheap", 0.01),
    ]
    stats = fanout_stats(traces)
    assert stats["ensemble_tasks"] == 1
    assert stats["single_tasks"] == 1
    assert stats["fanout_candidates"] == 3
    assert stats["fanout_usd"] == pytest.approx(0.08)
    assert stats["winner_usd"] == pytest.approx(0.02)
    assert stats["ensemble_tax_usd"] == pytest.approx(0.06)
    assert stats["tax_ratio"] == pytest.approx(0.08 / 0.02, abs=1e-4)


def test_fanout_stats_empty_is_zeroed() -> None:
    stats = fanout_stats([])
    assert stats["ensemble_tasks"] == 0
    assert stats["fanout_usd"] == 0.0
    assert stats["tax_ratio"] == 0.0


def test_fanout_stats_ordered_only_never_fans_out() -> None:
    traces = [_ordered_trace("cheap", 0.01)]
    stats = fanout_stats(traces)
    assert stats["ensemble_tasks"] == 0
    assert stats["single_tasks"] == 1
    assert stats["ensemble_tax_usd"] == 0.0


# -- extract_experiment_metrics --------------------------------------------

def test_extract_is_deterministic_and_pure() -> None:
    result = run_experiment(load_experiment("ensemble"))
    a = extract_experiment_metrics(result)
    b = extract_experiment_metrics(result)
    assert a == b
    assert a.recorded_at is None  # pure: no clock unless asked
    assert a.measured is False
    assert a.schema_version == SCHEMA_VERSION
    assert a.run_id == "38fb40ba53080601"


def test_extract_pins_ensemble_numbers() -> None:
    metrics = extract_experiment_metrics(run_experiment(load_experiment("ensemble")))
    assert metrics.tasks == 6
    assert metrics.coverage == pytest.approx(1.0)
    assert metrics.routed_usd == pytest.approx(0.132801, abs=1e-6)
    assert metrics.baseline_usd == pytest.approx(0.250728, abs=1e-6)
    assert metrics.delta_pct == pytest.approx(0.4703, abs=1e-4)
    assert metrics.ensemble_tasks == 6
    assert metrics.single_tasks == 0
    assert metrics.fanout_usd == pytest.approx(0.496812, abs=1e-6)
    assert metrics.ensemble_tax_usd == pytest.approx(0.364011, abs=1e-6)
    assert metrics.tax_ratio == pytest.approx(3.741, abs=1e-3)
    assert metrics.spotlight_task == "t-0032"
    assert metrics.reproducible is True


def test_extract_run_id_changes_with_content() -> None:
    ensemble = extract_experiment_metrics(run_experiment(load_experiment("ensemble")))
    hero = extract_experiment_metrics(run_experiment(load_experiment("hero")))
    assert ensemble.run_id != hero.run_id


# -- to_metric_records (Azure Monitor / OTel shape) -------------------------

def test_to_metric_records_are_foundry_shaped() -> None:
    metrics = extract_experiment_metrics(
        run_experiment(load_experiment("ensemble")), recorded_at="2026-01-01T00:00:00Z"
    )
    records = metrics.to_metric_records()
    names = {r["name"] for r in records}
    assert "router.cost.routed_usd" in names
    assert "router.ensemble.tax_usd" in names
    assert "router.quality.coverage" in names
    for record in records:
        assert set(record) == {"name", "value", "unit", "timestamp", "dimensions"}
        assert record["timestamp"] == "2026-01-01T00:00:00Z"
        assert record["dimensions"]["experiment"] == "ensemble"
        assert record["dimensions"]["measured"] == "false"
    routed = next(r for r in records if r["name"] == "router.cost.routed_usd")
    assert routed["value"] == pytest.approx(0.132801, abs=1e-6)
    assert routed["unit"] == "USD"


# -- JsonlMetricsStore ------------------------------------------------------

def _metrics(
    name: str = "demo", recorded_at: str | None = "2026-01-01T00:00:00Z"
) -> ExperimentMetrics:
    return ExperimentMetrics(
        run_id="abc123",
        experiment=name,
        title="Demo",
        source="fixture",
        tasks=3,
        accepted=3,
        coverage=1.0,
        routed_usd=0.5,
        baseline_usd=1.0,
        delta_usd=0.5,
        delta_pct=0.5,
        avg_usd_per_task=0.166667,
        ensemble_tasks=1,
        single_tasks=2,
        fanout_candidates=3,
        fanout_usd=0.7,
        ensemble_tax_usd=0.2,
        tax_ratio=1.4,
        spotlight_task="t-1",
        spotlight_ratio=2.0,
        reproducible=True,
        recorded_at=recorded_at,
    )


def test_store_round_trips_history(tmp_path: Path) -> None:
    store = JsonlMetricsStore(tmp_path / "history.jsonl")
    assert store.history() == []
    store.record(_metrics("alpha", "2026-01-01T00:00:00Z"))
    store.record(_metrics("beta", "2026-01-02T00:00:00Z"))
    rows = store.history()
    assert [row["experiment"] for row in rows] == ["alpha", "beta"]
    assert rows[0]["measured"] is False


def test_store_filters_and_tail_limits(tmp_path: Path) -> None:
    store = JsonlMetricsStore(tmp_path / "history.jsonl")
    store.record(_metrics("alpha", "2026-01-01T00:00:00Z"))
    store.record(_metrics("beta", "2026-01-02T00:00:00Z"))
    store.record(_metrics("alpha", "2026-01-03T00:00:00Z"))
    assert len(store.history(experiment="alpha")) == 2
    assert len(store.history(limit=1)) == 1
    assert store.history(limit=1)[0]["recorded_at"] == "2026-01-03T00:00:00Z"


def test_store_latest_per_experiment(tmp_path: Path) -> None:
    store = JsonlMetricsStore(tmp_path / "history.jsonl")
    store.record(_metrics("alpha", "2026-01-01T00:00:00Z"))
    store.record(_metrics("alpha", "2026-01-05T00:00:00Z"))
    latest = store.latest_per_experiment()
    assert set(latest) == {"alpha"}
    assert latest["alpha"]["recorded_at"] == "2026-01-05T00:00:00Z"


def test_store_rejects_corrupt_line(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid metrics JSON"):
        JsonlMetricsStore(path).history()


# -- FoundryMetricsEmitter --------------------------------------------------

def test_emitter_offline_by_default() -> None:
    emitter = FoundryMetricsEmitter(env={})
    assert emitter.configured is False
    records = emitter.emit(_metrics())
    assert records == emitter.captured
    assert len(records) == 15


def test_emitter_reports_configured_with_connection_string() -> None:
    env = {"AZURE_AI_FOUNDRY_CONNECTION_STRING": "InstrumentationKey=abc;IngestionEndpoint=https://x"}
    emitter = FoundryMetricsEmitter(env=env)
    assert emitter.configured is True


def test_emitter_forwards_only_through_injected_sink() -> None:
    forwarded: list = []
    emitter = FoundryMetricsEmitter(
        connection_string="InstrumentationKey=abc", sink=forwarded.append
    )
    emitter.emit(_metrics())
    assert len(forwarded) == 1
    assert forwarded[0][0]["dimensions"]["measured"] == "false"


# -- record_experiment_metrics ----------------------------------------------

def test_record_fans_out_to_store_and_emitter(tmp_path: Path) -> None:
    store = JsonlMetricsStore(tmp_path / "history.jsonl")
    emitter = FoundryMetricsEmitter(env={})
    result = run_experiment(load_experiment("ensemble"))
    metrics = record_experiment_metrics(
        result, store=store, emitter=emitter, recorded_at="2026-01-01T00:00:00Z"
    )
    assert metrics.recorded_at == "2026-01-01T00:00:00Z"
    assert len(store.history()) == 1
    assert len(emitter.captured) == 15


def test_record_stamps_wall_clock_when_unset(tmp_path: Path) -> None:
    store = JsonlMetricsStore(tmp_path / "history.jsonl")
    result = run_experiment(load_experiment("curated"))
    metrics = record_experiment_metrics(result, store=store)
    assert metrics.recorded_at is not None
    assert metrics.recorded_at.endswith("Z")


def test_utc_now_iso_is_zulu() -> None:
    stamp = utc_now_iso()
    assert stamp.endswith("Z")
    assert "T" in stamp


def test_metrics_to_dict_is_json_serializable() -> None:
    metrics = extract_experiment_metrics(run_experiment(load_experiment("ensemble")))
    payload = json.dumps(metrics.to_dict())
    assert "ensemble_tax_usd" in payload
