"""Trace construction for routing decisions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from policy import Candidate, TaskClass

from .budget import BudgetDecision
from .profile import profile_task
from .select import SelectionResult


def build_trace(
    *,
    task: Mapping[str, Any],
    task_class: TaskClass,
    candidates: tuple[Candidate, ...],
    selection: SelectionResult,
    budget: BudgetDecision | None = None,
    measured: bool = False,
) -> dict[str, Any]:
    """Build a serializable trace for a completed offline decision."""

    profile = profile_task(task)
    return {
        "task_id": task.get("task_id"),
        "class": task_class.value,
        "difficulty": profile.difficulty,
        "risk": profile.risk,
        "candidates": [
            {
                "model": candidate.model,
                "rank": rank,
                "prior_pass": candidate.prior_pass,
                "prior_usd_resolved": candidate.prior_usd_resolved,
            }
            for rank, candidate in enumerate(candidates)
        ],
        "mode": selection.mode,
        "budget": _budget_payload(budget),
        "attempts": [
            {
                "model": attempt.model,
                "signals": attempt.signals,
                "accepted": attempt.accepted,
                "score": attempt.score,
            }
            for attempt in selection.attempts
        ],
        "chosen": selection.chosen_model,
        "reason": selection.reason,
        "tokens": dict(task.get("tokens", {})),
        "cost_usd": _chosen_cost(selection),
        "labels": {"measured": measured},
    }


def _chosen_cost(selection: SelectionResult) -> float | None:
    if selection.chosen_model is None:
        return None
    for attempt in selection.attempts:
        if attempt.model == selection.chosen_model:
            value = attempt.signals.get("cost_usd")
            return float(value) if isinstance(value, int | float) else None
    return None


def _budget_payload(budget: BudgetDecision | None) -> dict[str, Any] | None:
    if budget is None:
        return None
    return {
        "selection_mode": budget.selection_mode,
        "value": budget.value,
        "reason": budget.reason,
    }
