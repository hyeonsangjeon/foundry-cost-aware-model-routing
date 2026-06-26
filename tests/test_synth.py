"""Tests for deterministic offline signal synthesis and full-workload replay."""

from __future__ import annotations

from pathlib import Path

from policy import TaskClass, load_default_policy
from router import (
    classify_task,
    load_workload,
    run_evals,
    run_replay,
    synthesize_signals,
    synthesize_task_signals,
)

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = ROOT / "samples" / "telemetry" / "mixed-coding-workload.sample.jsonl"
PRICING = ROOT / "samples" / "pricing" / "illustrative.yaml"

GENERIC_MODELS = {"mini-fast", "swift-coder", "balanced-pro", "deep-reasoner", "premium-max"}


def test_seed_policy_uses_only_generic_placeholder_names() -> None:
    policy = load_default_policy()
    names = {
        candidate.model
        for task_class in TaskClass
        for candidate in policy.candidates_for(task_class)
    }
    assert names <= GENERIC_MODELS


def test_synthesized_signals_cover_every_candidate() -> None:
    policy = load_default_policy()
    workload = load_workload(WORKLOAD)
    signals = synthesize_signals(workload, policy)

    assert set(signals) == set(workload)
    for task_id, task in workload.items():
        candidates = policy.candidates_for(classify_task(task))
        assert set(signals[task_id]) == {candidate.model for candidate in candidates}


def test_synthesized_model_names_are_generic_placeholders() -> None:
    policy = load_default_policy()
    workload = load_workload(WORKLOAD)
    signals = synthesize_signals(workload, policy)
    seen = {model for per_task in signals.values() for model in per_task}
    assert seen <= GENERIC_MODELS


def test_synthesis_is_deterministic() -> None:
    policy = load_default_policy()
    workload = load_workload(WORKLOAD)
    assert synthesize_signals(workload, policy) == synthesize_signals(workload, policy)


def test_most_expensive_candidate_always_resolves_clean() -> None:
    policy = load_default_policy()
    workload = load_workload(WORKLOAD)
    for task in workload.values():
        candidates = policy.candidates_for(classify_task(task))
        signals = synthesize_task_signals(task, candidates)
        fallback = candidates[-1].model
        checks = [value for value in signals[fallback].values() if isinstance(value, bool)]
        assert checks and all(checks)


def test_full_workload_replay_summary_is_stable() -> None:
    report = run_replay(workload_path=WORKLOAD, pricing_path=PRICING, synth=True)
    summary = report.summary
    assert summary["tasks"] == 100
    assert summary["accepted"] == 100
    assert summary["coverage"] == 1.0
    assert summary["mode_counts"] == {"ordered": 74, "compare": 26}


def test_full_workload_eval_numbers_are_stable() -> None:
    report = run_evals(workload_path=WORKLOAD, pricing_path=PRICING, synth=True)
    assert report["tasks"] == 100
    assert report["accepted"] == 100
    assert report["coverage"] == 1.0
    assert report["routed_total_usd"] == 1.659167
    assert report["baseline_total_usd"] == 2.226910
    assert report["delta_usd"] == 0.567743
    assert report["routed_total_usd"] < report["baseline_total_usd"]
    assert report["reason_counts"] == {
        "clean-first": 19,
        "escalated": 55,
        "compared": 18,
        "tie-broken": 8,
    }


def test_full_workload_replay_is_deterministic() -> None:
    first = run_replay(workload_path=WORKLOAD, pricing_path=PRICING, synth=True)
    second = run_replay(workload_path=WORKLOAD, pricing_path=PRICING, synth=True)
    assert first.traces == second.traces
