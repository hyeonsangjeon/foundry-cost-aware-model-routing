"""Typed task classes, candidate priors, and the policy table.

The policy maps each task class to an ordered list of candidate models, each
annotated with two priors: ``prior_pass`` (how often it solves this class) and
``prior_usd_resolved`` (gross cost per solved task). Candidates are ordered
cheapest-first so the selector can consult them cheapest-clean-first.

All priors shipped in ``seed_policy.yaml`` are illustrative placeholders, not
measured production values. Refresh them from local telemetry before relying on
them for decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent / "seed_policy.yaml"


class TaskClass(StrEnum):
    """The routable task classes."""

    PLAN = "plan"
    GENERATE = "generate"
    TEST = "test"
    VALIDATE = "validate"
    REPO_PATCH = "repo_patch"

    @classmethod
    def from_str(cls, value: str) -> TaskClass:
        try:
            return cls(value)
        except ValueError as exc:
            valid = ", ".join(c.value for c in cls)
            raise ValueError(
                f"unknown task class {value!r}; expected one of: {valid}"
            ) from exc


@dataclass(frozen=True)
class Candidate:
    """A candidate model for a task class, with its routing priors."""

    model: str
    prior_pass: float
    prior_usd_resolved: float

    def __post_init__(self) -> None:
        if not self.model or not self.model.strip():
            raise ValueError("candidate model must be a non-empty string")
        if not 0.0 <= self.prior_pass <= 1.0:
            raise ValueError(
                f"prior_pass for {self.model!r} must be in [0, 1], got {self.prior_pass}"
            )
        if self.prior_usd_resolved <= 0.0:
            raise ValueError(
                f"prior_usd_resolved for {self.model!r} must be > 0, got {self.prior_usd_resolved}"
            )


@dataclass(frozen=True)
class PolicyTable:
    """Task class -> ordered (cheapest-first) candidate models."""

    classes: dict[TaskClass, tuple[Candidate, ...]]
    version: int = 1

    def candidates_for(self, task_class: TaskClass | str) -> tuple[Candidate, ...]:
        tc = task_class if isinstance(task_class, TaskClass) else TaskClass.from_str(task_class)
        if tc not in self.classes:
            raise KeyError(f"no candidates defined for task class {tc.value!r}")
        return self.classes[tc]

    def validate(self) -> PolicyTable:
        """Enforce the data contract; return self so calls can chain."""
        for tc, cands in self.classes.items():
            if not cands:
                raise ValueError(f"class {tc.value!r} has no candidates")
            costs = [c.prior_usd_resolved for c in cands]
            if costs != sorted(costs):
                raise ValueError(
                    f"class {tc.value!r} candidates must be ordered cheapest-first by "
                    f"prior_usd_resolved; got {costs}"
                )
            models = [c.model for c in cands]
            if len(models) != len(set(models)):
                raise ValueError(f"class {tc.value!r} has duplicate candidate models: {models}")
        missing = [tc.value for tc in TaskClass if tc not in self.classes]
        if missing:
            raise ValueError(f"policy missing candidates for classes: {', '.join(missing)}")
        return self

    @classmethod
    def from_dict(cls, data: dict) -> PolicyTable:
        version = int(data.get("version", 1))
        raw_classes = data.get("classes")
        if not isinstance(raw_classes, dict):
            raise ValueError("policy document must have a top-level 'classes' mapping")
        parsed: dict[TaskClass, tuple[Candidate, ...]] = {}
        for name, items in raw_classes.items():
            tc = TaskClass.from_str(name)
            if not isinstance(items, list) or not items:
                raise ValueError(f"class {name!r} must list at least one candidate")
            try:
                cands = tuple(
                    Candidate(
                        model=str(item["model"]),
                        prior_pass=float(item["prior_pass"]),
                        prior_usd_resolved=float(item["prior_usd_resolved"]),
                    )
                    for item in items
                )
            except (KeyError, TypeError) as exc:
                raise ValueError(f"class {name!r} has a malformed candidate: {exc}") from exc
            parsed[tc] = cands
        return cls(classes=parsed, version=version)

    @classmethod
    def from_yaml(cls, path: Path | str = DEFAULT_POLICY_PATH) -> PolicyTable:
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        return cls.from_dict(data)


def load_default_policy() -> PolicyTable:
    """Load and validate the shipped seed policy."""
    return PolicyTable.from_yaml(DEFAULT_POLICY_PATH).validate()
