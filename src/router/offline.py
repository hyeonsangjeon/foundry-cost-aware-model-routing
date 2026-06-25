"""Offline routing helpers over local sample files."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from policy import PolicyTable, load_default_policy

from .budget import BudgetDecision, BudgetGate
from .classify import classify_task
from .pricing import PricingTable
from .select import SelectionResult, SignalMap, compare_select, ordered_select
from .trace import build_trace


def load_workload(path: Path | str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            rows[str(row["task_id"])] = row
    return rows


def load_signal_fixture(path: Path | str) -> dict[str, SignalMap]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    tasks = data.get("tasks")
    if not isinstance(tasks, dict):
        raise ValueError("signal fixture must contain a top-level 'tasks' mapping")
    return {str(task_id): signals for task_id, signals in tasks.items()}


def route_task(
    task: Mapping[str, Any],
    signals_by_model: SignalMap,
    *,
    policy: PolicyTable | None = None,
    pricing: PricingTable | None = None,
    budget_gate: BudgetGate | None = None,
) -> dict[str, Any]:
    policy = policy or load_default_policy()
    budget_gate = budget_gate or BudgetGate()
    task_class = classify_task(task)
    candidates = policy.candidates_for(task_class)
    priced_signals = _with_costs(signals_by_model, task, pricing) if pricing else signals_by_model
    budget = budget_gate.decide(task, candidates)
    selection = select_with_budget(candidates, priced_signals, budget)
    return build_trace(
        task=task,
        task_class=task_class,
        candidates=candidates,
        selection=selection,
        budget=budget,
    )


def route_tasks(
    workload: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, SignalMap],
    *,
    task_ids: Iterable[str] | None = None,
    policy: PolicyTable | None = None,
    pricing: PricingTable | None = None,
    budget_gate: BudgetGate | None = None,
) -> list[dict[str, Any]]:
    ids = list(task_ids) if task_ids is not None else list(signals.keys())
    return [
        route_task(
            workload[task_id],
            signals[task_id],
            policy=policy,
            pricing=pricing,
            budget_gate=budget_gate,
        )
        for task_id in ids
    ]


def select_with_budget(
    candidates,
    signals_by_model: SignalMap,
    budget: BudgetDecision,
) -> SelectionResult:
    if budget.selection_mode == "compare":
        return compare_select(candidates, signals_by_model)
    return ordered_select(candidates, signals_by_model)


def summarize_traces(traces: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(traces)
    accepted = [trace for trace in rows if _trace_accepted(trace)]
    total_cost = sum(float(trace.get("cost_usd") or 0.0) for trace in rows)
    mode_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    for trace in rows:
        mode = str(trace.get("mode"))
        reason = str(trace.get("reason"))
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return {
        "tasks": len(rows),
        "accepted": len(accepted),
        "coverage": (len(accepted) / len(rows)) if rows else 0.0,
        "total_cost_usd": round(total_cost, 6),
        "mode_counts": mode_counts,
        "reason_counts": reason_counts,
    }


def _with_costs(
    signals_by_model: SignalMap,
    task: Mapping[str, Any],
    pricing: PricingTable,
) -> dict[str, dict[str, Any]]:
    tokens = task.get("tokens", {})
    return {
        model: {**dict(signals), "cost_usd": pricing.cost_usd(model, tokens)}
        for model, signals in signals_by_model.items()
    }


def _trace_accepted(trace: Mapping[str, Any]) -> bool:
    chosen = trace.get("chosen")
    for attempt in trace.get("attempts", []):
        if attempt.get("model") == chosen:
            return bool(attempt.get("accepted"))
    return False
