"""Baseline cost helpers (no routing) for local eval summaries.

The baseline always spends on the most expensive candidate for a task class,
so it is the natural ceiling that routing is compared against.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from policy import PolicyTable

from .classify import classify_task
from .pricing import PricingTable
from .select import is_clean


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
