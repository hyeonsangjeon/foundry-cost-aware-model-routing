"""Baseline cost helpers (no routing) for local eval summaries.

The baseline always spends on the most expensive candidate for a task class,
so it is the natural ceiling that routing is compared against.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from policy import Candidate, PolicyTable

from .classify import classify_task
from .pricing import PricingTable
from .select import is_clean

BaselineArm = Literal["cost", "balanced", "quality"]


def baseline_model_for_task(task: Mapping[str, Any], policy: PolicyTable) -> str:
    """Return the most expensive candidate model for the task's class."""

    task_class = classify_task(task)
    candidates = policy.candidates_for(task_class)
    return max(candidates, key=lambda candidate: candidate.prior_usd_resolved).model


def baseline_cost_usd(
    workload: Mapping[str, Mapping[str, Any]],
    policy: PolicyTable,
    pricing: PricingTable,
) -> float:
    """Total USD if every task always used its most expensive candidate."""

    total = 0.0
    for task in workload.values():
        model = baseline_model_for_task(task, policy)
        total += pricing.cost_usd(model, task.get("tokens", {}))
    return round(total, 6)


def single_tier_summary(
    workload: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Mapping[str, Any]]],
    policy: PolicyTable,
    pricing: PricingTable,
    *,
    cheapest: bool,
) -> dict[str, Any]:
    """Cost and coverage if every task used one fixed tier for its class.

    ``cheapest=True`` models the "all-mini" strategy (route everything to the
    cheapest candidate); ``cheapest=False`` models "all-premium" (the priciest,
    matching :func:`baseline_cost_usd`). Coverage reuses the router's own
    :func:`is_clean` predicate on the same offline signals, so a task counts as
    covered only when that single tier passes every check for it. Deterministic
    and offline — the whole point is to expose the cheap-tier coverage drop.
    """

    total = 0.0
    accepted = 0
    counted = 0
    for task_id, task in workload.items():
        task_signals = signals.get(str(task_id))
        if task_signals is None:
            continue
        candidates = policy.candidates_for(classify_task(task))
        if not candidates:
            continue
        counted += 1
        if cheapest:
            pick = min(candidates, key=lambda candidate: candidate.prior_usd_resolved)
        else:
            pick = max(candidates, key=lambda candidate: candidate.prior_usd_resolved)
        total += pricing.cost_usd(pick.model, task.get("tokens", {}))
        row = task_signals.get(pick.model)
        if row is not None and is_clean(row):
            accepted += 1
    coverage = (accepted / counted) if counted else 0.0
    return {
        "total_cost_usd": round(total, 6),
        "coverage": coverage,
        "tasks": counted,
        "accepted": accepted,
    }


def ensemble_all_summary(
    workload: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Mapping[str, Any]]],
    policy: PolicyTable,
    pricing: PricingTable,
) -> dict[str, Any]:
    """Cost and coverage for the naive "fan out to every model" strategy.

    Runs *all* candidates on *every* task and keeps the best — so it pays the
    full fan-out bill (the sum of all candidate costs) on each task while
    covering a task whenever any candidate passes the offline checks. This is the
    ceiling the cost-aware mix beats: same (or better) coverage as premium-only,
    but the highest cost of any strategy because it never stops early.
    Deterministic and offline — it isolates the ensemble fan-out tax.
    """

    total = 0.0
    accepted = 0
    counted = 0
    for task_id, task in workload.items():
        task_signals = signals.get(str(task_id))
        if task_signals is None:
            continue
        candidates = policy.candidates_for(classify_task(task))
        if not candidates:
            continue
        counted += 1
        tokens = task.get("tokens", {})
        total += sum(pricing.cost_usd(candidate.model, tokens) for candidate in candidates)
        if any(
            (row := task_signals.get(candidate.model)) is not None and is_clean(row)
            for candidate in candidates
        ):
            accepted += 1
    coverage = (accepted / counted) if counted else 0.0
    return {
        "total_cost_usd": round(total, 6),
        "coverage": coverage,
        "tasks": counted,
        "accepted": accepted,
    }


def single_call_baseline_arms(
    workload: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Mapping[str, Any]]],
    policy: PolicyTable,
    pricing: PricingTable,
) -> dict[str, dict[str, Any]]:
    """Score deterministic Cost/Balanced/Quality-equivalent single-call arms.

    These are transparent placeholder baselines, not claims about a managed
    router's internal implementation: ``cost`` picks the cheapest candidate for
    each class, ``balanced`` picks the middle candidate, and ``quality`` picks
    the most expensive candidate.
    """

    return {
        arm: _single_call_arm(workload, signals, policy, pricing, arm=arm)
        for arm in ("cost", "balanced", "quality")
    }


def _single_call_arm(
    workload: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Mapping[str, Any]]],
    policy: PolicyTable,
    pricing: PricingTable,
    *,
    arm: BaselineArm,
) -> dict[str, Any]:
    total = 0.0
    accepted = 0
    counted = 0
    model_counts: dict[str, int] = {}
    for task_id, task in workload.items():
        task_signals = signals.get(str(task_id))
        if task_signals is None:
            continue
        candidates = policy.candidates_for(classify_task(task))
        pick = _arm_candidate(candidates, arm)
        counted += 1
        model_counts[pick.model] = model_counts.get(pick.model, 0) + 1
        total += pricing.cost_usd(pick.model, task.get("tokens", {}))
        row = task_signals.get(pick.model)
        if row is not None and is_clean(row):
            accepted += 1
    return {
        "selection": {
            "cost": "cheapest-candidate",
            "balanced": "middle-candidate",
            "quality": "most-expensive-candidate",
        }[arm],
        "tasks": counted,
        "accepted": accepted,
        "coverage": (accepted / counted) if counted else 0.0,
        "total_cost_usd": round(total, 6),
        "model_counts": model_counts,
        "labels": {"measured": False, "equivalent": "illustrative"},
    }


def _arm_candidate(
    candidates: tuple[Candidate, ...],
    arm: BaselineArm,
) -> Candidate:
    if arm == "cost":
        return candidates[0]
    if arm == "balanced":
        return candidates[len(candidates) // 2]
    return candidates[-1]
