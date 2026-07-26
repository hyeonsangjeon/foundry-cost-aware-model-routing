from __future__ import annotations

import pytest

from router.validation import (
    ValidationSpecError,
    describe_rule,
    evaluate_validation,
    validate_rule,
)


def test_contains_is_case_insensitive_by_default():
    rule = {"type": "contains", "value": "def solve"}
    assert evaluate_validation(rule, "DEF SOLVE(x):") is True
    assert evaluate_validation(rule, "no function here") is False


def test_contains_case_sensitive_flag():
    rule = {"type": "contains", "value": "Solve", "case_sensitive": True}
    assert evaluate_validation(rule, "Solve") is True
    assert evaluate_validation(rule, "solve") is False


def test_not_contains():
    rule = {"type": "not_contains", "value": "TODO"}
    assert evaluate_validation(rule, "finished code") is True
    assert evaluate_validation(rule, "# TODO: finish") is False


def test_equals_trims_by_default():
    rule = {"type": "equals", "value": "42"}
    assert evaluate_validation(rule, "  42\n") is True
    assert evaluate_validation(rule, "421") is False


def test_regex_and_nonempty_and_json():
    assert evaluate_validation({"type": "regex", "pattern": r"^\s*def\s+\w+"}, "def foo():") is True
    assert evaluate_validation({"type": "regex", "pattern": r"^\d+$"}, "abc") is False
    assert evaluate_validation({"type": "nonempty"}, "   ") is False
    assert evaluate_validation({"type": "nonempty"}, " x ") is True
    assert evaluate_validation({"type": "json_valid"}, '{"a": 1}') is True
    assert evaluate_validation({"type": "json_valid"}, "{not json}") is False


def test_all_and_any_composites():
    rule = {
        "type": "all",
        "rules": [
            {"type": "contains", "value": "def "},
            {"type": "not_contains", "value": "TODO"},
        ],
    }
    assert evaluate_validation(rule, "def solve(): return 1") is True
    assert evaluate_validation(rule, "def solve(): # TODO") is False

    any_rule = {"type": "any", "rules": [
        {"type": "contains", "value": "pass"},
        {"type": "contains", "value": "return"},
    ]}
    assert evaluate_validation(any_rule, "return 1") is True
    assert evaluate_validation(any_rule, "raise X") is False


def test_evaluate_never_raises_on_bad_output():
    # non-str output degrades to a fail, not an exception
    assert evaluate_validation({"type": "nonempty"}, None) is False  # type: ignore[arg-type]


def test_validate_rule_rejects_unknown_and_malformed():
    with pytest.raises(ValidationSpecError):
        validate_rule({"type": "vibes"})  # subjective/unknown
    with pytest.raises(ValidationSpecError):
        validate_rule({"type": "contains"})  # missing value
    with pytest.raises(ValidationSpecError):
        validate_rule({"type": "regex", "pattern": "("})  # invalid regex
    with pytest.raises(ValidationSpecError):
        validate_rule({"type": "all", "rules": []})  # empty composite
    with pytest.raises(ValidationSpecError):
        validate_rule("nope")  # not a mapping


def test_validate_rule_accepts_wellformed_nested():
    validate_rule({"type": "all", "rules": [
        {"type": "contains", "value": "x"},
        {"type": "any", "rules": [{"type": "nonempty"}, {"type": "json_valid"}]},
    ]})


def test_describe_rule_is_human_readable():
    assert "contains" in describe_rule({"type": "contains", "value": "def"})
    desc = describe_rule({"type": "all", "rules": [
        {"type": "contains", "value": "a"}, {"type": "not_contains", "value": "b"},
    ]})
    assert " AND " in desc
