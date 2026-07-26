"""Machine-readable pass/fail rules for measured workloads (BOLT-02 B2/D12).

A prompt-bearing task carries a ``validation`` block that states — in a form a
machine can check without human judgment — what counts as a *pass*. This module
parses those blocks and evaluates them against a model's output string.

The point is honesty: coverage on a measured run must come from a deterministic
predicate over the actual output, not a subjective "looks good". Every rule type
here is a pure function of ``(rule, output)`` — no network, no model-as-judge.

Rule schema (a task's ``validation`` field)::

    {"type": "contains",     "value": "def solve", "case_sensitive": false}
    {"type": "not_contains", "value": "TODO"}
    {"type": "equals",       "value": "42", "trim": true}
    {"type": "regex",        "pattern": "^\\s*def\\s+\\w+"}
    {"type": "nonempty"}
    {"type": "json_valid"}
    {"type": "all", "rules": [ ...nested rules... ]}   # every child must pass
    {"type": "any", "rules": [ ...nested rules... ]}   # at least one child

``all``/``any`` compose the leaf rules so a task can require, say, "contains a
function definition AND does not contain a TODO". Unknown types or missing
fields raise :class:`ValidationSpecError` at authoring time so a malformed rule
never silently passes (or silently fails) a measured task.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

LEAF_TYPES = frozenset(
    {"contains", "not_contains", "equals", "regex", "nonempty", "json_valid"}
)
COMPOSITE_TYPES = frozenset({"all", "any"})
RULE_TYPES = LEAF_TYPES | COMPOSITE_TYPES


class ValidationSpecError(ValueError):
    """A ``validation`` block is malformed, subjective, or uses an unknown type."""


def validate_rule(rule: Any, *, _depth: int = 0) -> None:
    """Raise :class:`ValidationSpecError` unless ``rule`` is a well-formed spec.

    Call this when a workload is authored/loaded so a bad rule fails loudly
    before any (paid) measured run rather than during grading.
    """

    if _depth > 8:
        raise ValidationSpecError("validation rule nested too deeply (max 8)")
    if not isinstance(rule, Mapping):
        raise ValidationSpecError(f"validation rule must be a mapping, got {type(rule).__name__}")
    rtype = rule.get("type")
    if rtype not in RULE_TYPES:
        raise ValidationSpecError(
            f"unknown validation type {rtype!r}; expected one of {sorted(RULE_TYPES)}"
        )
    if rtype in COMPOSITE_TYPES:
        children = rule.get("rules")
        if not isinstance(children, (list, tuple)) or not children:
            raise ValidationSpecError(f"{rtype!r} rule needs a non-empty 'rules' list")
        for child in children:
            validate_rule(child, _depth=_depth + 1)
        return
    if rtype in {"contains", "not_contains", "equals"}:
        if not isinstance(rule.get("value"), str):
            raise ValidationSpecError(f"{rtype!r} rule needs a string 'value'")
    elif rtype == "regex":
        pattern = rule.get("pattern")
        if not isinstance(pattern, str):
            raise ValidationSpecError("regex rule needs a string 'pattern'")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValidationSpecError(f"invalid regex pattern: {exc}") from exc


def evaluate_validation(rule: Mapping[str, Any], output: str) -> bool:
    """Return whether ``output`` satisfies ``rule``. Pure; never raises on input.

    ``rule`` is assumed well-formed (see :func:`validate_rule`). ``output`` is the
    model's raw completion text.
    """

    rtype = rule.get("type")
    text = output if isinstance(output, str) else ""

    if rtype == "nonempty":
        return bool(text.strip())
    if rtype == "json_valid":
        try:
            json.loads(text)
            return True
        except (ValueError, TypeError):
            return False
    if rtype in {"contains", "not_contains", "equals"}:
        value = str(rule.get("value", ""))
        hay, needle = text, value
        if not rule.get("case_sensitive", False):
            hay, needle = hay.lower(), needle.lower()
        if rtype == "contains":
            return needle in hay
        if rtype == "not_contains":
            return needle not in hay
        left = text.strip() if rule.get("trim", True) else text
        right = value.strip() if rule.get("trim", True) else value
        if not rule.get("case_sensitive", False):
            left, right = left.lower(), right.lower()
        return left == right
    if rtype == "regex":
        flags = 0 if rule.get("case_sensitive", False) else re.IGNORECASE
        try:
            return re.search(str(rule.get("pattern", "")), text, flags) is not None
        except re.error:
            return False
    if rtype == "all":
        return all(evaluate_validation(child, text) for child in rule.get("rules", []))
    if rtype == "any":
        return any(evaluate_validation(child, text) for child in rule.get("rules", []))
    return False


def describe_rule(rule: Mapping[str, Any]) -> str:
    """One-line human summary of a rule, for the pre-run prompt catalog (B4)."""

    rtype = rule.get("type")
    if rtype in COMPOSITE_TYPES:
        joiner = " AND " if rtype == "all" else " OR "
        return "(" + joiner.join(describe_rule(c) for c in rule.get("rules", [])) + ")"
    if rtype == "nonempty":
        return "output is non-empty"
    if rtype == "json_valid":
        return "output parses as JSON"
    if rtype == "regex":
        return f"output matches /{rule.get('pattern', '')}/"
    if rtype == "contains":
        return f"output contains {rule.get('value', '')!r}"
    if rtype == "not_contains":
        return f"output does not contain {rule.get('value', '')!r}"
    if rtype == "equals":
        return f"output equals {rule.get('value', '')!r}"
    return f"<unknown rule {rtype!r}>"
