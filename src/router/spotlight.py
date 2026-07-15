"""Spotlight selection: the single task where routing most visibly beats naive.

A *spotlight* is one task from a replay where cost-aware routing (cheapest
capable model first, escalate only on failure) lands far below the naive arm
that would bill the most expensive candidate for every task. It is the "aha"
moment that makes an aggregate before/after concrete: one row, two numbers, and
the ratio between them.

This lives in its own module (depending only on :mod:`pricing`) so both the
experiment runner and the replay/dashboard path can reuse it without importing
each other.

Every number here is an offline projection over synthetic data
(``labels.measured = false``) — not a measured saving.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .pricing import PricingTable

SPOTLIGHT_OFF = {"", "none", "off", "false", "no"}


@dataclass(frozen=True)
class Spotlight:
    """One task where cost-aware routing visibly beats the naive premium arm."""

    task_id: str
    task_class: str
    chosen_model: str | None
    naive_model: str
    routed_usd: float
    naive_usd: float
    ratio: float
    accepted: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "class": self.task_class,
            "chosen_model": self.chosen_model,
            "naive_model": self.naive_model,
            "routed_usd": self.routed_usd,
            "naive_usd": self.naive_usd,
            "ratio": self.ratio,
            "accepted": self.accepted,
            "reason": self.reason,
        }


def select_spotlight(
    traces: Iterable[Mapping[str, Any]],
    pricing: PricingTable,
    spec: str = "auto",
) -> Spotlight | None:
    """Pick a spotlight task from ``traces``.

    ``spec`` selects the strategy:

    * ``"auto"`` (default) — the accepted task with the largest naive/routed
      cost ratio (the most dramatic honest win).
    * ``"none"``/``"off"``/empty — no spotlight.
    * any other value — the task whose ``task_id`` matches ``spec`` exactly;
      raises :class:`ValueError` if no such task exists.
    """

    key = (spec or "auto").strip().lower()
    if key in SPOTLIGHT_OFF:
        return None
    if key == "auto":
        best: Spotlight | None = None
        for trace in traces:
            candidate = spotlight_for(trace, pricing, require_accepted=True)
            if candidate is not None and (best is None or candidate.ratio > best.ratio):
                best = candidate
        return best
    for trace in traces:
        if str(trace.get("task_id")) == spec:
            return spotlight_for(trace, pricing, require_accepted=False)
    raise ValueError(f"spotlight task {spec!r} not found in experiment traces")


def spotlight_for(
    trace: Mapping[str, Any],
    pricing: PricingTable,
    *,
    require_accepted: bool,
) -> Spotlight | None:
    """Build a :class:`Spotlight` for one ``trace`` (or ``None`` if unusable).

    The naive arm is the most expensive candidate for the task
    (``candidates[-1]``, since candidates are ordered cheapest first); its cost
    is re-derived from ``pricing`` and the task's token counts. When
    ``require_accepted`` is true the trace is skipped unless its chosen model
    actually passed its checks and billed a positive routed cost.
    """

    chosen = trace.get("chosen")
    accepted = any(
        attempt.get("model") == chosen and bool(attempt.get("accepted"))
        for attempt in trace.get("attempts", [])
    )
    if require_accepted and not accepted:
        return None
    candidates = trace.get("candidates") or []
    if not candidates:
        return None
    routed = float(trace.get("cost_usd") or 0.0)
    if require_accepted and routed <= 0.0:
        return None
    naive_model = str(candidates[-1]["model"])
    naive = pricing.cost_usd(naive_model, trace.get("tokens", {}))
    ratio = round(naive / routed, 4) if routed else 0.0
    return Spotlight(
        task_id=str(trace.get("task_id")),
        task_class=str(trace.get("class")),
        chosen_model=str(chosen) if chosen is not None else None,
        naive_model=naive_model,
        routed_usd=round(routed, 6),
        naive_usd=round(naive, 6),
        ratio=ratio,
        accepted=accepted,
        reason=str(trace.get("reason")),
    )
