"""Phase 4 acceptance: the offline replay and its naive-vs-routed 'aha' block.

The replay must be deterministic, internally consistent (every task lands in
exactly one strategy bucket), never cost more than the naive premium baseline,
and stay honestly labelled as an offline projection (``measured`` is False).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from router.pipeline import format_replay_json, format_replay_text, run_replay

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = ROOT / "samples" / "telemetry" / "mixed-coding-workload.sample.jsonl"
SIGNALS = ROOT / "samples" / "responses" / "routing-signals.sample.json"
PRICING = ROOT / "samples" / "pricing" / "illustrative.yaml"


def _curated():
    return run_replay(workload_path=WORKLOAD, pricing_path=PRICING, signals_path=SIGNALS)


def _synth():
    return run_replay(workload_path=WORKLOAD, pricing_path=PRICING, synth=True)


@pytest.mark.parametrize("build", [_curated, _synth])
def test_replay_is_deterministic(build) -> None:
    first, second = build(), build()
    assert first.traces == second.traces
    assert first.summary == second.summary


@pytest.mark.parametrize("build", [_curated, _synth])
def test_strategy_buckets_partition_the_workload(build) -> None:
    summary = build().summary
    tasks = summary["tasks"]
    # Every routed task falls into exactly one mode and one reason bucket.
    assert sum(summary["mode_counts"].values()) == tasks
    assert sum(summary["reason_counts"].values()) == tasks
    assert summary["accepted"] <= tasks


@pytest.mark.parametrize("build", [_curated, _synth])
def test_routing_never_beats_a_zero_and_stays_under_baseline(build) -> None:
    summary = build().summary
    baseline = summary["baseline_total_usd"]
    routed = summary["total_cost_usd"]
    assert 0.0 < routed <= baseline
    assert summary["delta_usd"] == round(baseline - routed, 6)
    assert summary["delta_pct"] == pytest.approx(summary["delta_usd"] / baseline)


@pytest.mark.parametrize("build", [_curated, _synth])
def test_offline_replay_is_honestly_labelled(build) -> None:
    report = build()
    assert report.summary["measured"] is False
    assert all(trace["labels"]["measured"] is False for trace in report.traces)


def test_synth_before_after_matches_known_projection() -> None:
    # Pins the 30-second "aha": naive premium-on-every-task vs cost-aware routing
    # over the full 100-row synthetic workload. Deterministic and network-free.
    summary = _synth().summary
    assert summary["tasks"] == 100
    assert summary["coverage"] == 1.0
    assert summary["baseline_total_usd"] == 2.226910
    assert summary["total_cost_usd"] == 1.659167
    assert summary["delta_usd"] == 0.567743


@pytest.mark.parametrize("build", [_curated, _synth])
def test_three_way_strategy_tradeoff(build) -> None:
    # The dashboard's core message: neither single-tier strategy wins on both
    # axes. all-mini is cheapest but drops coverage; all-premium holds coverage
    # but costs the most; only the cost-aware mix keeps full coverage below the
    # premium cost.
    summary = build().summary
    strat = summary["strategies"]
    assert set(strat) == {"all_mini", "all_premium", "mix"}
    mini, prem, mix = strat["all_mini"], strat["all_premium"], strat["mix"]

    # Cost ordering: cheapest-only < mix < premium-only.
    assert mini["total_cost_usd"] < mix["total_cost_usd"] < prem["total_cost_usd"]

    # Coverage: premium and mix hold 100%; cheapest-only visibly drops below.
    assert prem["coverage"] == 1.0
    assert mix["coverage"] == 1.0
    assert mini["coverage"] < 1.0

    # The single-tier baselines reconcile with the headline totals so the bars
    # animate against the same numbers the KPIs show.
    assert prem["total_cost_usd"] == summary["baseline_total_usd"]
    assert mix["total_cost_usd"] == summary["total_cost_usd"]


def test_synth_strategy_numbers_are_pinned() -> None:
    # Deterministic three-way projection over the full synthetic workload.
    strat = _synth().summary["strategies"]
    assert strat["all_mini"] == {"total_cost_usd": 0.187913, "coverage": 0.22}
    assert strat["all_premium"] == {"total_cost_usd": 2.226910, "coverage": 1.0}
    assert strat["mix"] == {"total_cost_usd": 1.659167, "coverage": 1.0}


@pytest.mark.parametrize("build", [_curated, _synth])
def test_escalated_task_count_is_present_and_bounded(build) -> None:
    summary = build().summary
    escalated = summary["escalated_tasks"]
    assert isinstance(escalated, int)
    assert 0 <= escalated <= summary["tasks"]


def test_before_after_block_renders_in_text_not_json() -> None:
    report = _synth()
    text = format_replay_text(report)
    assert "before / after" in text
    assert "BEFORE  naive" in text
    assert "AFTER   cost-aware routing" in text
    assert "SAVED" in text
    assert "labels.measured=false" in text
    # The JSON view stays a pure trace list for machine consumers.
    payload = json.loads(format_replay_json(report))
    assert isinstance(payload, list)
    assert "before / after" not in format_replay_json(report)


@pytest.mark.parametrize("build", [_curated, _synth])
def test_breakdown_reconciles_with_top_line(build) -> None:
    summary = build().summary
    breakdown = summary["breakdown"]
    assert set(breakdown) == {"by_class", "by_model", "mode_cost_usd", "reason_counts"}

    by_class = breakdown["by_class"]
    # Per-class routed/baseline costs sum back to the headline totals.
    assert round(sum(c["routed_usd"] for c in by_class.values()), 6) == summary["total_cost_usd"]
    assert (
        round(sum(c["baseline_usd"] for c in by_class.values()), 6)
        == summary["baseline_total_usd"]
    )
    assert sum(c["tasks"] for c in by_class.values()) == summary["tasks"]

    by_model = breakdown["by_model"]
    assert sum(m["tasks"] for m in by_model.values()) == summary["tasks"]
    assert round(sum(m["routed_usd"] for m in by_model.values()), 6) == summary["total_cost_usd"]

    # mode cost split reconciles with routed total; reason counts partition tasks.
    assert round(sum(breakdown["mode_cost_usd"].values()), 6) == summary["total_cost_usd"]
    assert sum(breakdown["reason_counts"].values()) == summary["tasks"]


def test_breakdown_savings_are_non_negative_and_labelled() -> None:
    by_class = _synth().summary["breakdown"]["by_class"]
    for bucket in by_class.values():
        assert bucket["saved_usd"] == round(bucket["baseline_usd"] - bucket["routed_usd"], 6)
        assert bucket["saved_usd"] >= 0.0
        assert 0.0 <= bucket["saved_pct"] <= 1.0

