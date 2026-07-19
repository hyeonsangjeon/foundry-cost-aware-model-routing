"""Tests for the head-to-head arena (:mod:`router.arena`).

Pins the "one problem, four ways" numbers for the curated demo task and the
honesty-critical cost conventions (router bills the winner only; the ensemble
bills every candidate), plus the illustrative latency projection's shape.
"""

from __future__ import annotations

import pytest

from router import load_signal_fixture, load_task_prompts, load_workload
from router.arena import (
    APPROACH_ORDER,
    bundled_head_to_head,
    head_to_head,
    project_latency_ms,
)
from router.pipeline import (
    DEFAULT_PRICING,
    DEFAULT_PROMPTS,
    DEFAULT_SIGNALS,
    DEFAULT_WORKLOAD,
    bundled_compare,
    find_samples_root,
    load_policy,
)
from router.pricing import PricingTable


@pytest.fixture()
def arena() -> dict:
    return bundled_compare()["arenas"]["t-0003"]


def _by_approach(arena: dict) -> dict:
    return {a["approach"]: a for a in arena["approaches"]}


def test_bundled_compare_shape_and_default() -> None:
    payload = bundled_compare()
    assert payload["labels"]["measured"] is False
    assert payload["default"] == "t-0003"
    task_ids = {t["task_id"] for t in payload["tasks"]}
    assert task_ids == {"t-0001", "t-0003", "t-0004", "t-0005", "t-0006"}
    assert set(payload["arenas"]) == task_ids
    # every arena carries the four approaches in the canonical order
    for arena in payload["arenas"].values():
        assert [a["approach"] for a in arena["approaches"]] == list(APPROACH_ORDER)


def test_curated_task_numbers_are_pinned(arena: dict) -> None:
    by = _by_approach(arena)
    assert arena["class"] == "repo_patch"
    assert arena["candidates"] == ["swift-coder", "balanced-pro", "deep-reasoner", "premium-max"]

    assert by["cheapest"]["chosen_model"] == "swift-coder"
    assert by["cheapest"]["cost_usd"] == pytest.approx(0.006680, abs=1e-6)
    assert by["cheapest"]["passed"] is False  # cheap but wrong

    assert by["premium"]["chosen_model"] == "premium-max"
    assert by["premium"]["cost_usd"] == pytest.approx(0.081981, abs=1e-6)
    assert by["premium"]["passed"] is True

    assert by["ensemble"]["cost_usd"] == pytest.approx(0.179844, abs=1e-6)
    assert by["ensemble"]["passed"] is True

    assert by["router"]["chosen_model"] == "balanced-pro"
    assert by["router"]["cost_usd"] == pytest.approx(0.032793, abs=1e-6)
    assert by["router"]["passed"] is True


def test_router_bills_winner_only_and_ensemble_bills_every_candidate(arena: dict) -> None:
    by = _by_approach(arena)
    singles = {
        "swift-coder": by["cheapest"]["cost_usd"],
        "premium-max": by["premium"]["cost_usd"],
        "balanced-pro": by["router"]["cost_usd"],
    }
    # The ensemble pays the sum of *all* candidates (the fan-out tax); the router
    # pays only for the winning attempt (matching the trace / spotlight cost).
    ensemble = by["ensemble"]
    assert ensemble["chosen_model"] is None
    assert ensemble["cost_usd"] > by["router"]["cost_usd"]
    assert ensemble["cost_usd"] == pytest.approx(0.179844, abs=1e-6)
    # winner-only router cost equals the single-call cost of its chosen model
    assert by["router"]["cost_usd"] == pytest.approx(singles["balanced-pro"], abs=1e-9)


def test_winners_and_no_free_lunch(arena: dict) -> None:
    winners = arena["winners"]
    # the router is the cheapest passing approach...
    assert winners["cost"] == "router"
    # ...but it is NOT the fastest: sequential escalation trades latency for cost.
    assert winners["latency"] == "premium"
    # accuracy is binary: every passing approach wins it equally (the cheap one
    # fails), so it is a list, not a single crowned winner.
    assert set(winners["accuracy"]) == {"premium", "ensemble", "router"}
    by = _by_approach(arena)
    assert by["router"]["latency_ms"] > by["premium"]["latency_ms"]


def test_easy_task_cheapest_sweeps_every_axis() -> None:
    arena = bundled_compare()["arenas"]["t-0001"]
    by = _by_approach(arena)
    # On an easy task the cheapest single already passes, so it wins cost + latency
    # and the router simply picks it (routing adds no value here — and says so).
    assert by["cheapest"]["passed"] is True
    assert arena["winners"]["cost"] == "cheapest"
    assert arena["winners"]["latency"] == "cheapest"
    # every approach passes an easy task, so all four win the accuracy axis
    assert set(arena["winners"]["accuracy"]) == {"cheapest", "premium", "ensemble", "router"}
    assert by["router"]["chosen_model"] == by["cheapest"]["chosen_model"]


def test_default_task_prefers_cheap_fails_router_recovers() -> None:
    # The opening task is the most instructive: cheapest fails, router recovers,
    # with the widest premium->router saving.
    payload = bundled_compare()
    default = payload["arenas"][payload["default"]]
    by = _by_approach(default)
    assert by["cheapest"]["passed"] is False
    assert by["router"]["passed"] is True


def test_task_override_selects_requested_default() -> None:
    payload = bundled_compare(task_id="t-0006")
    assert payload["default"] == "t-0006"
    # unknown ids fall back to the auto-picked default rather than crashing
    assert bundled_compare(task_id="does-not-exist")["default"] == "t-0003"


def test_latency_projection_is_deterministic_and_ordered() -> None:
    tokens = {"output": 400, "reasoning": 120}
    # deterministic
    assert project_latency_ms(1, tokens) == project_latency_ms(1, tokens)
    # a pricier tier is slower for the same tokens (higher overhead + lower tps)
    assert project_latency_ms(0, tokens) < project_latency_ms(1, tokens)
    assert project_latency_ms(1, tokens) < project_latency_ms(2, tokens)
    # more streamed tokens => more time
    assert project_latency_ms(0, {"output": 800, "reasoning": 0}) > project_latency_ms(
        0, {"output": 100, "reasoning": 0}
    )
    # negative tiers clamp to the base overhead (no negative or exploding time)
    assert project_latency_ms(-3, {"output": 0, "reasoning": 0}) == pytest.approx(150.0)


def test_ensemble_is_parallel_router_is_sequential(arena: dict) -> None:
    by = _by_approach(arena)
    # Fan-out runs candidates in parallel => wall-clock is the slowest single.
    slowest_single = max(
        by["cheapest"]["latency_ms"], by["premium"]["latency_ms"]
    )
    assert by["ensemble"]["latency_ms"] == pytest.approx(slowest_single, abs=0.1)
    # Router escalates sequentially => its latency is the SUM of attempts, so a
    # two-step escalation is slower than either single call it made.
    assert by["router"]["latency_ms"] > by["cheapest"]["latency_ms"]
    assert by["router"]["latency_ms"] > by["premium"]["latency_ms"]


def test_head_to_head_rejects_unknown_task() -> None:
    # A task id absent from the workload raises KeyError before any scoring.
    with pytest.raises(KeyError):
        head_to_head("nope", {}, {"nope": {"m": {}}}, None, None)  # type: ignore[arg-type]


# -- readable problem statements (the authored input test data) --------------


def _arena_inputs():
    base = find_samples_root()
    workload = load_workload(base / DEFAULT_WORKLOAD)
    signals = load_signal_fixture(base / DEFAULT_SIGNALS)
    pricing = PricingTable.from_yaml(base / DEFAULT_PRICING)
    policy = load_policy(None)
    prompts = load_task_prompts(base / DEFAULT_PROMPTS)
    return workload, signals, policy, pricing, prompts


def test_load_task_prompts_reads_fixture() -> None:
    prompts = load_task_prompts(find_samples_root() / DEFAULT_PROMPTS)
    assert set(prompts) == {"t-0001", "t-0003", "t-0004", "t-0005", "t-0006"}
    t3 = prompts["t-0003"]
    assert t3["title"] == "Patch parse_duration to accept combined units"
    assert "parse_duration" in t3["prompt"]
    assert t3["acceptance"]


def test_bundled_compare_carries_readable_problem() -> None:
    payload = bundled_compare()
    # every curated arena exposes an authored, self-contained problem statement
    for tid, arena in payload["arenas"].items():
        problem = arena["problem"]
        assert problem is not None, tid
        assert problem["title"] and problem["prompt"]
        assert arena["labels"]["problem_basis"] == "authored-synthetic"
    # the task menu carries the short title for the chips
    titles = {t["task_id"]: t["title"] for t in payload["tasks"]}
    assert titles["t-0001"] == "slugify(title)"
    assert all(titles.values())


def test_problem_is_optional_and_does_not_change_numbers() -> None:
    workload, signals, policy, pricing, prompts = _arena_inputs()
    without = head_to_head("t-0003", workload, signals, policy, pricing)
    with_prompt = head_to_head("t-0003", workload, signals, policy, pricing, prompts)
    # absent prompts => no problem block, present => the authored statement
    assert without["problem"] is None
    assert with_prompt["problem"]["title"] == "Patch parse_duration to accept combined units"
    # the readable prompt is presentation only — classification, candidates and
    # every cost/latency/pass number are identical with or without it.
    assert without["class"] == with_prompt["class"] == "repo_patch"
    assert without["candidates"] == with_prompt["candidates"]
    assert without["approaches"] == with_prompt["approaches"]
    assert without["winners"] == with_prompt["winners"]


def test_bundled_head_to_head_without_prompts_has_no_problem() -> None:
    workload, signals, policy, pricing, _ = _arena_inputs()
    payload = bundled_head_to_head(workload, signals, policy, pricing)
    for arena in payload["arenas"].values():
        assert arena["problem"] is None
    assert all(t["title"] == "" for t in payload["tasks"])
