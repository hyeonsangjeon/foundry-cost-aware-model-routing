"""Trace construction for routing decisions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from policy import Candidate, TaskClass

from .select import SelectionResult


def build_trace(
    *,
    task: Mapping[str, Any],
    task_class: TaskClass,
    candidates: tuple[Candidate, ...],
    selection: SelectionResult,
    measured: bool = False,
) -> dict[str, Any]:
    """Build a serializable trace for a completed offline decision."""

    return {
        "task_id": task.get("task_id"),
        "class": task_class.value,
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
