"""Budget gate, replay, and eval tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from policy import Candidate, load_default_policy
from router import (
    BudgetGate,
    PricingTable,
    baseline_cost_usd,
    baseline_model_for_task,
    load_signal_fixture,
    load_workload,
    route_tasks,
    summarize_traces,
)

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_PATH = ROOT / "samples" / "telemetry" / "mixed-coding-workload.sample.jsonl"
SIGNALS_PATH = ROOT / "samples" / "responses" / "routing-signals.sample.json"
PRICING_PATH = ROOT / "samples" / "pricing" / "illustrative.yaml"


def test_budget_gate_defaults_easy_tasks_to_ordered() -> None:
    decision = BudgetGate().decide(
        {"difficulty": "easy"},
        (Candidate("a", 0.5, 0.1), Candidate("b", 0.8, 0.2)),
    )
    assert decision.selection_mode == "ordered"
    assert decision.reason == "ordered-default"


def test_budget_gate_uses_compare_for_high_value_tasks() -> None:
    decision = BudgetGate().decide(
        {"difficulty": "hard", "class": "repo_patch", "diff_size_lines": 500},
        (Candidate("a", 0.5, 0.1), Candidate("b", 0.8, 0.2)),
    )
    assert decision.selection_mode == "compare"
    assert decision.value == 1.0


def test_pricing_table_costs_cached_tokens_separately() -> None:
    pricing = PricingTable.from_yaml(PRICING_PATH)
    cost = pricing.cost_usd(
        "mini-fast",
        {"input": 1000, "cached": 400, "output": 200, "reasoning": 100},
    )
    assert cost == 0.000286


def test_route_tasks_summary_is_deterministic() -> None:
    policy = load_default_policy()
    workload = load_workload(WORKLOAD_PATH)
    signals = load_signal_fixture(SIGNALS_PATH)
    pricing = PricingTable.from_yaml(PRICING_PATH)
    traces = route_tasks(workload, signals, policy=policy, pricing=pricing)
    summary = summarize_traces(traces)

    assert summary["tasks"] == 5
    assert summary["accepted"] == 5
    assert summary["coverage"] == 1.0
    assert summary["mode_counts"] == {"ordered": 4, "compare": 1}


def test_baseline_uses_highest_cost_prior_candidate() -> None:
    policy = load_default_policy()
    workload = load_workload(WORKLOAD_PATH)
    assert baseline_model_for_task(workload["t-0001"], policy) == "balanced-pro"
    assert baseline_model_for_task(workload["t-0003"], policy) == "premium-max"


def test_baseline_cost_is_above_routed_cost_for_sample() -> None:
    policy = load_default_policy()
    workload = load_workload(WORKLOAD_PATH)
    signals = load_signal_fixture(SIGNALS_PATH)
    selected_workload = {task_id: workload[task_id] for task_id in signals}
    pricing = PricingTable.from_yaml(PRICING_PATH)
    traces = route_tasks(selected_workload, signals, policy=policy, pricing=pricing)
    routed = summarize_traces(traces)
    baseline = baseline_cost_usd(selected_workload, policy, pricing)

    assert baseline > routed["total_cost_usd"]


def test_replay_script_runs() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "samples" / "python" / "replay_route.py"),
            str(WORKLOAD_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "summary tasks=5 accepted=5 coverage=100.0%" in result.stdout


def test_route_once_script_runs() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "samples" / "python" / "route_once.py"),
            "--task-id",
            "t-0003",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert '"task_id": "t-0003"' in result.stdout
    assert '"class": "repo_patch"' in result.stdout


def test_eval_script_runs() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "evals" / "run.py"),
            "--workload",
            str(WORKLOAD_PATH),
            "--signals",
            str(SIGNALS_PATH),
            "--pricing",
            str(PRICING_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "tasks: 5" in result.stdout
    assert "coverage: 100.0%" in result.stdout
    assert "mode_counts:" in result.stdout
