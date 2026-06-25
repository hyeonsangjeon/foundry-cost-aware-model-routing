"""Baseline cost helpers for local eval summaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from policy import PolicyTable
from router.classify import classify_task
from router.pricing import PricingTable


def baseline_model_for_task(task: Mapping[str, Any], policy: PolicyTable) -> str:
    task_class = classify_task(task)
    candidates = policy.candidates_for(task_class)
    return max(candidates, key=lambda candidate: candidate.prior_usd_resolved).model


def baseline_cost_usd(
    workload: Mapping[str, Mapping[str, Any]],
    policy: PolicyTable,
    pricing: PricingTable,
) -> float:
    total = 0.0
    for task in workload.values():
        model = baseline_model_for_task(task, policy)
        total += pricing.cost_usd(model, task.get("tokens", {}))
    return round(total, 6)
