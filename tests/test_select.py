"""Router classification, selection, and trace tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from policy import Candidate, TaskClass, load_default_policy
from router.classify import classify_task
from router.select import compare_select, ordered_select
from router.trace import build_trace

ROOT = Path(__file__).resolve().parents[1]
SIGNALS_PATH = ROOT / "samples" / "responses" / "routing-signals.sample.json"
WORKLOAD_PATH = ROOT / "samples" / "telemetry" / "mixed-coding-workload.sample.jsonl"


def test_classifier_prefers_explicit_class() -> None:
    task = {"class": "repo-patch", "text": "write unit tests"}
    assert classify_task(task) == TaskClass.REPO_PATCH


def test_classifier_uses_diff_size_when_class_is_absent() -> None:
    task = {"prompt": "make a small change", "diff_size_lines": 80}
    assert classify_task(task) == TaskClass.REPO_PATCH


def test_classifier_uses_keywords_when_metadata_is_absent() -> None:
    assert classify_task({"prompt": "please add pytest coverage"}) == TaskClass.TEST
    assert classify_task({"prompt": "verify this output and lint it"}) == TaskClass.VALIDATE
    assert classify_task({"prompt": "design the implementation plan"}) == TaskClass.PLAN
    assert classify_task({"prompt": "write a helper function"}) == TaskClass.GENERATE


def test_ordered_select_accepts_first_clean_candidate() -> None:
    candidates = (
        Candidate("a", 0.5, 0.1),
        Candidate("b", 0.8, 0.2),
    )
    result = ordered_select(
        candidates,
        {
            "a": {"applies": True, "compiles": True, "tests_pass": True},
            "b": {"applies": True, "compiles": True, "tests_pass": True},
        },
    )
    assert result.chosen_model == "a"
    assert result.reason == "clean-first"
    assert len(result.attempts) == 1


def test_ordered_select_escalates_after_failed_candidate() -> None:
    candidates = (
        Candidate("a", 0.5, 0.1),
        Candidate("b", 0.8, 0.2),
    )
    result = ordered_select(
        candidates,
        {
            "a": {"applies": True, "compiles": False, "tests_pass": False},
            "b": {"applies": True, "compiles": True, "tests_pass": True},
        },
    )
    assert result.chosen_model == "b"
    assert result.reason == "escalated"
    assert [attempt.model for attempt in result.attempts] == ["a", "b"]


def test_compare_select_is_deterministic_for_ties() -> None:
    candidates = (
        Candidate("a", 0.5, 0.1),
        Candidate("b", 0.8, 0.2),
    )
    result = compare_select(
        candidates,
        {
            "a": {"applies": True, "compiles": False},
            "b": {"applies": True, "compiles": False},
        },
    )
    assert result.chosen_model == "a"
    assert result.reason == "tie-broken"


def test_compare_select_accepts_custom_tie_breaker() -> None:
    candidates = (
        Candidate("a", 0.5, 0.1),
        Candidate("b", 0.8, 0.2),
    )
    result = compare_select(
        candidates,
        {
            "a": {"applies": True, "compiles": False},
            "b": {"applies": True, "compiles": False},
        },
        tie_breaker=lambda tied: tied[-1],
    )
    assert result.chosen_model == "b"


def test_build_trace_has_expected_shape() -> None:
    task = {"task_id": "t-x", "class": "generate", "tokens": {"input": 100}}
    candidates = (Candidate("a", 0.5, 0.1),)
    result = ordered_select(candidates, {"a": {"applies": True, "cost_usd": 0.01}})
    trace = build_trace(
        task=task,
        task_class=TaskClass.GENERATE,
        candidates=candidates,
        selection=result,
    )
    assert trace["task_id"] == "t-x"
    assert trace["class"] == "generate"
    assert trace["chosen"] == "a"
    assert trace["cost_usd"] == 0.01
    assert trace["labels"] == {"measured": False}


def test_sample_signal_fixture_produces_deterministic_traces() -> None:
    policy = load_default_policy()
    workload = _load_workload()
    signals = _load_signals()
    traces = []

    for task_id, signals_by_model in signals["tasks"].items():
        task = workload[task_id]
        task_class = classify_task(task)
        candidates = policy.candidates_for(task_class)
        selection = ordered_select(candidates, signals_by_model)
        traces.append(
            build_trace(
                task=task,
                task_class=task_class,
                candidates=candidates,
                selection=selection,
            )
        )

    assert [trace["task_id"] for trace in traces] == [
        "t-0001",
        "t-0003",
        "t-0004",
        "t-0005",
        "t-0006",
    ]
    assert [trace["reason"] for trace in traces] == [
        "clean-first",
        "escalated",
        "escalated",
        "clean-first",
        "escalated",
    ]
    assert all(trace["labels"]["measured"] is False for trace in traces)


def _load_workload() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with open(WORKLOAD_PATH, encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            rows[row["task_id"]] = row
    return rows


def _load_signals() -> dict[str, Any]:
    with open(SIGNALS_PATH, encoding="utf-8") as handle:
        return json.load(handle)
