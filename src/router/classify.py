"""Rule-based task classification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from policy import TaskClass


class Classifier(Protocol):
    """Minimal interface for pluggable classifiers."""

    def classify(self, task: Mapping[str, Any]) -> TaskClass:
        """Return the task class for a task payload."""


@dataclass(frozen=True)
class RuleBasedClassifier:
    """Classify tasks from explicit metadata, diff size, and text keywords."""

    repo_patch_line_threshold: int = 40

    def classify(self, task: Mapping[str, Any]) -> TaskClass:
        explicit = task.get("class") or task.get("task_class")
        if explicit:
            return _parse_task_class(str(explicit))

        diff_size = _int_or_zero(task.get("diff_size_lines"))
        if diff_size >= self.repo_patch_line_threshold:
            return TaskClass.REPO_PATCH

        text = _task_text(task)
        if _contains_any(text, ("patch", "diff", "repository", "repo", "pull request")):
            return TaskClass.REPO_PATCH
        if _contains_any(text, ("test", "pytest", "unit test", "coverage")):
            return TaskClass.TEST
        if _contains_any(text, ("validate", "verify", "lint", "typecheck", "review")):
            return TaskClass.VALIDATE
        if _contains_any(text, ("plan", "design", "decompose", "architecture")):
            return TaskClass.PLAN
        return TaskClass.GENERATE


def classify_task(task: Mapping[str, Any], classifier: Classifier | None = None) -> TaskClass:
    """Classify a task with the provided classifier or the default rules."""

    return (classifier or RuleBasedClassifier()).classify(task)


def _parse_task_class(value: str) -> TaskClass:
    normalized = value.strip().lower().replace("-", "_")
    return TaskClass.from_str(normalized)


def _task_text(task: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in ("title", "summary", "description", "prompt", "text"):
        value = task.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts).lower()


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
