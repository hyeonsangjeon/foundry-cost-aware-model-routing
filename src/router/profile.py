"""Deterministic task profiles and replay strata for offline evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from policy import TaskClass

from .classify import classify_task

Difficulty = Literal["easy", "medium", "hard", "unspecified"]
Risk = Literal["low", "moderate", "high"]

@dataclass(frozen=True)
class TaskProfile:
    """Normalized task class, difficulty, and risk used by offline evals."""

    task_class: TaskClass
    difficulty: Difficulty
    risk: Risk

    def to_dict(self) -> dict[str, str]:
        return {
            "class": self.task_class.value,
            "difficulty": self.difficulty,
            "risk": self.risk,
        }


def profile_task(task: Mapping[str, Any]) -> TaskProfile:
    """Derive a stable evaluation profile without mutating the workload row."""

    task_class = classify_task(task)
    difficulty = _difficulty(task.get("difficulty"))
    risk = _risk(task_class, difficulty, _int_or_zero(task.get("diff_size_lines")))
    return TaskProfile(task_class=task_class, difficulty=difficulty, risk=risk)


def stratify_traces(traces: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group replay tasks by normalized risk and difficulty."""

    return {
        "by_risk": _stratify(traces, "risk"),
        "by_difficulty": _stratify(traces, "difficulty"),
    }


def _stratify(
    traces: Sequence[Mapping[str, Any]],
    key: str,
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for trace in traces:
        name = str(trace.get(key) or "unspecified")
        bucket = buckets.setdefault(name, {"tasks": 0, "accepted": 0, "cost_usd": 0.0})
        bucket["tasks"] += 1
        bucket["accepted"] += 1 if _trace_accepted(trace) else 0
        bucket["cost_usd"] = round(
            bucket["cost_usd"] + float(trace.get("cost_usd") or 0.0),
            6,
        )
    return buckets


def _difficulty(value: Any) -> Difficulty:
    normalized = str(value or "").strip().lower()
    if normalized == "easy":
        return "easy"
    if normalized == "medium":
        return "medium"
    if normalized == "hard":
        return "hard"
    return "unspecified"


def _risk(task_class: TaskClass, difficulty: Difficulty, diff_size: int) -> Risk:
    if task_class == TaskClass.REPO_PATCH or diff_size >= 400:
        return "high"
    if task_class == TaskClass.GENERATE:
        return "moderate" if difficulty == "hard" else "low"
    if difficulty == "hard":
        return "high"
    return "moderate"


def _trace_accepted(trace: Mapping[str, Any]) -> bool:
    chosen = trace.get("chosen")
    return any(
        attempt.get("model") == chosen and bool(attempt.get("accepted"))
        for attempt in trace.get("attempts", [])
    )


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
