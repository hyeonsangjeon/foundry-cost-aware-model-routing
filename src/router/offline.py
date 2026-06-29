"""Offline routing helpers over local sample files."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from policy import Candidate, PolicyTable, load_default_policy

from .budget import BudgetDecision, BudgetGate
from .classify import classify_task
from .pricing import PricingTable
from .select import SelectionResult, SignalMap, compare_select, ordered_select
from .trace import build_trace

_QUALITY_CHECKS = ("compiles", "tests_pass", "lint_pass")
_DIFFICULTY_PENALTY = {"easy": 0.0, "medium": 0.08, "hard": 0.18}
_DEFAULT_PENALTY = 0.10


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


def synthesize_signals(
    workload: Mapping[str, Mapping[str, Any]],
    policy: PolicyTable | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Deterministically derive offline check signals for an entire workload.

    Each task is classified, its policy candidates are looked up, and a stable
    set of boolean checks is produced per candidate model. The result depends
    only on the task id, model name, difficulty, and prior_pass, so it never
    touches the network and is identical on every run and platform.
    """

    policy = policy or load_default_policy()
    signals: dict[str, dict[str, dict[str, Any]]] = {}
    for task_id, task in workload.items():
        candidates = policy.candidates_for(classify_task(task))
        signals[str(task_id)] = synthesize_task_signals(task, candidates)
    return signals


def synthesize_task_signals(
    task: Mapping[str, Any],
    candidates: tuple[Candidate, ...],
) -> dict[str, dict[str, Any]]:
    """Build deterministic per-model check signals for one task.

    The most expensive candidate always resolves cleanly, so every task has a
    guaranteed clean fallback. Cheaper candidates pass each quality check only
    when a stable hash of (task_id, model, check) clears a prior-derived
    threshold, which yields a realistic mix of clean-first and escalated runs.
    """

    task_id = str(task.get("task_id", ""))
    penalty = _DIFFICULTY_PENALTY.get(str(task.get("difficulty", "")).lower(), _DEFAULT_PENALTY)
    last_index = len(candidates) - 1
    signals: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(candidates):
        if index == last_index:
            signals[candidate.model] = {
                "applies": True,
                **{check: True for check in _QUALITY_CHECKS},
            }
            continue
        threshold = _clamp_unit(candidate.prior_pass - penalty)
        row: dict[str, Any] = {"applies": True}
        for check in _QUALITY_CHECKS:
            row[check] = _stable_unit(task_id, candidate.model, check) < threshold
        signals[candidate.model] = row
    return signals


def _stable_unit(*parts: str) -> float:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


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
