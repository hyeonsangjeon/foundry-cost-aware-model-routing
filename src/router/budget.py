"""Small local budget gate for choosing a selection mode."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from policy import Candidate

SelectionMode = Literal["ordered", "compare"]


@dataclass(frozen=True)
class BudgetDecision:
    """The local gate output used by the offline selector."""

    selection_mode: SelectionMode
    value: float
    reason: str


@dataclass(frozen=True)
class BudgetGate:
    """Choose cheap ordered selection or full comparison from task metadata."""

    compare_min_value: float = 0.75
    min_compare_candidates: int = 2

    def decide(
        self,
        task: Mapping[str, Any],
        candidates: tuple[Candidate, ...],
    ) -> BudgetDecision:
        value = _task_value(task)
        enough_candidates = len(candidates) >= self.min_compare_candidates
        if enough_candidates and value >= self.compare_min_value:
            return BudgetDecision(
                selection_mode="compare",
                value=value,
                reason="value-threshold-met",
            )
        return BudgetDecision(
            selection_mode="ordered",
            value=value,
            reason="ordered-default",
        )


def _task_value(task: Mapping[str, Any]) -> float:
    explicit = task.get("value")
    if isinstance(explicit, int | float):
        return _clamp(float(explicit))

    difficulty = str(task.get("difficulty", "")).lower()
    value = {
        "easy": 0.25,
        "medium": 0.55,
        "hard": 0.85,
    }.get(difficulty, 0.40)

    diff_size = _int_or_zero(task.get("diff_size_lines"))
    if diff_size >= 400:
        value += 0.15
    elif diff_size >= 100:
        value += 0.05

    task_class = str(task.get("class") or task.get("task_class") or "").replace("-", "_")
    if task_class == "repo_patch":
        value += 0.05

    return _clamp(value)


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
