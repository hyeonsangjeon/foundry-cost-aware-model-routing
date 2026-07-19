"""Head-to-head arena: one problem, four ways — cost × latency × accuracy.

The rest of the dashboard compares strategies *in aggregate* over a whole
workload. This module answers the more visceral question a newcomer actually
asks first: **for this one task, what does each approach cost, how slow is it,
and does it even get the right answer?** It is the "pick a problem, press go,
watch four columns fill in" surface — the five-minute wow.

Four approaches are scored on a single task, reusing the exact offline
machinery the aggregate panels use so the numbers line up by construction:

* ``cheapest`` — always the cheapest candidate for the task's class. Fast and
  cheap, but may fail the checks.
* ``premium`` — always the most expensive candidate. The naive "just use the
  best model" ceiling.
* ``ensemble`` — fan out to *every* candidate and keep the best answer. Highest
  coverage, but pays the full fan-out bill (the sum of all candidates) — the
  ensemble tax, on one task.
* ``router`` — cheapest-capable-first with escalation on failure
  (:func:`router.select.ordered_select`). The repo's hero: it bills only the
  winning attempt, so it reaches premium-grade accuracy at close to cheap cost.

Honesty (kept consistent with the rest of the repo):

* **Cost** is the illustrative pricing over the task's token counts, identical to
  the aggregate arms. The router bills the *winner only* (matching the trace's
  ``cost_usd`` and the spotlight), while the ensemble bills *all* candidates.
* **Accuracy** is the router's own :func:`router.select.is_clean` predicate — a
  task is "passed" when every offline check is clean. It is a projection over
  synthetic signals, not a graded live answer.
* **Latency is an illustrative projection**, not a measurement. There is no
  timing in the bundled telemetry, so a deterministic per-tier throughput model
  turns token counts into milliseconds purely to give the third axis a shape.
  It is labelled ``measured = false`` everywhere and must not be read as real
  wall-clock. A live run (the measured bridge) is where real latency would come
  from.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from policy import Candidate, PolicyTable

from .classify import classify_task
from .pricing import PricingTable
from .select import is_clean, ordered_select

# Illustrative latency model (measured = false). A single call's wall-clock is
# modelled as a fixed per-tier overhead plus a token-streaming term, where the
# cheapest tier streams fastest. These constants only shape the third axis; they
# are not derived from any measurement and must not be read as real timings.
_BASE_OVERHEAD_MS = 150.0
_TIER_OVERHEAD_MS = 90.0
_BASE_THROUGHPUT_TPS = 200.0
_TIER_THROUGHPUT_PENALTY_TPS = 28.0
_MIN_THROUGHPUT_TPS = 40.0

APPROACH_ORDER = ("cheapest", "premium", "ensemble", "router")


def project_latency_ms(tier_index: int, tokens: Mapping[str, Any]) -> float:
    """Return an *illustrative* single-call latency in ms (``measured = false``).

    ``tier_index`` is the candidate's 0-based position in the cheapest→priciest
    ladder for its class, so cheaper tiers stream faster and start sooner. The
    streamed token count is ``output + reasoning`` (cached/input prompt tokens do
    not add generation time). Deterministic; purely a presentation shape.
    """

    streamed = _to_float(tokens.get("output")) + _to_float(tokens.get("reasoning"))
    throughput = max(
        _MIN_THROUGHPUT_TPS,
        _BASE_THROUGHPUT_TPS - _TIER_THROUGHPUT_PENALTY_TPS * max(0, tier_index),
    )
    overhead = _BASE_OVERHEAD_MS + _TIER_OVERHEAD_MS * max(0, tier_index)
    return round(overhead + 1000.0 * streamed / throughput, 1)


@dataclass(frozen=True)
class ApproachResult:
    """One approach's outcome on a single task (all numbers ``measured = false``)."""

    approach: str
    label: str
    models: tuple[str, ...]
    chosen_model: str | None
    cost_usd: float
    latency_ms: float
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "approach": self.approach,
            "label": self.label,
            "models": list(self.models),
            "chosen_model": self.chosen_model,
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms": round(self.latency_ms, 1),
            "passed": self.passed,
            "detail": self.detail,
        }


def head_to_head(
    task_id: str,
    workload: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Mapping[str, Any]]],
    policy: PolicyTable,
    pricing: PricingTable,
) -> dict[str, Any]:
    """Score the four approaches on one task and mark the per-axis winners.

    Returns a JSON-ready dict: the task profile, one entry per approach (cost,
    latency, pass), and the winning approach on each of cost / latency /
    accuracy. Raises :class:`KeyError` / :class:`ValueError` when the task is
    unknown or has no candidates/signals.
    """

    task = workload.get(task_id)
    if task is None:
        raise KeyError(f"task {task_id!r} not found in workload")
    task_signals = signals.get(task_id)
    if not task_signals:
        raise ValueError(f"task {task_id!r} has no offline signals")
    candidates = policy.candidates_for(classify_task(task))
    if not candidates:
        raise ValueError(f"task {task_id!r} has no policy candidates")

    tokens = task.get("tokens", {})
    approaches = [
        _cheapest(candidates, task_signals, tokens, pricing),
        _premium(candidates, task_signals, tokens, pricing),
        _ensemble(candidates, task_signals, tokens, pricing),
        _router(candidates, task_signals, tokens, pricing),
    ]

    winners = _winners(approaches)
    return {
        "task_id": task_id,
        "class": classify_task(task).value,
        "difficulty": str(task.get("difficulty") or "unspecified"),
        "tokens": dict(tokens),
        "candidates": [c.model for c in candidates],
        "approaches": [a.to_dict() for a in approaches],
        "winners": winners,
        "labels": {
            "measured": False,
            "cost_basis": "illustrative-pricing",
            "latency_basis": "illustrative-projection",
            "accuracy_basis": "offline-signal-projection",
        },
    }


def bundled_head_to_head(
    workload: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Mapping[str, Any]]],
    policy: PolicyTable,
    pricing: PricingTable,
    *,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Build the full compare payload: a task menu plus every task's arena.

    Pre-computes the head-to-head for every task that has signals so the static
    export and the live endpoint are identical and the web app can switch tasks
    with no round-trip. ``default`` is the most instructive task (the biggest
    honest premium→router saving where the cheapest single actually fails).
    """

    task_ids = [tid for tid in workload if tid in signals and signals.get(tid)]
    arenas: dict[str, dict[str, Any]] = {}
    menu: list[dict[str, Any]] = []
    for tid in task_ids:
        try:
            arena = head_to_head(tid, workload, signals, policy, pricing)
        except (KeyError, ValueError):
            continue
        arenas[tid] = arena
        menu.append(
            {
                "task_id": tid,
                "class": arena["class"],
                "difficulty": arena["difficulty"],
                "teaches": _teaches(arena),
            }
        )

    if not arenas:
        raise ValueError("no tasks with signals to compare")
    default = task_id if task_id in arenas else _default_task(arenas)
    return {
        "tasks": menu,
        "default": default,
        "arenas": arenas,
        "labels": {"measured": False},
    }


# -- approaches --------------------------------------------------------------


def _cheapest(
    candidates: tuple[Candidate, ...],
    task_signals: Mapping[str, Mapping[str, Any]],
    tokens: Mapping[str, Any],
    pricing: PricingTable,
) -> ApproachResult:
    model = candidates[0].model
    passed = _passed(task_signals, model)
    return ApproachResult(
        approach="cheapest",
        label="Cheapest model",
        models=(model,),
        chosen_model=model,
        cost_usd=pricing.cost_usd(model, tokens),
        latency_ms=project_latency_ms(0, tokens),
        passed=passed,
        detail=(
            f"One call to the cheapest tier ({model})."
            + ("" if passed else " Fails the checks here — cheap but wrong.")
        ),
    )


def _premium(
    candidates: tuple[Candidate, ...],
    task_signals: Mapping[str, Mapping[str, Any]],
    tokens: Mapping[str, Any],
    pricing: PricingTable,
) -> ApproachResult:
    index = len(candidates) - 1
    model = candidates[index].model
    passed = _passed(task_signals, model)
    return ApproachResult(
        approach="premium",
        label="Premium model",
        models=(model,),
        chosen_model=model,
        cost_usd=pricing.cost_usd(model, tokens),
        latency_ms=project_latency_ms(index, tokens),
        passed=passed,
        detail=f"One call to the most expensive tier ({model}) — the naive ceiling.",
    )


def _ensemble(
    candidates: tuple[Candidate, ...],
    task_signals: Mapping[str, Mapping[str, Any]],
    tokens: Mapping[str, Any],
    pricing: PricingTable,
) -> ApproachResult:
    models = tuple(c.model for c in candidates)
    cost = sum(pricing.cost_usd(model, tokens) for model in models)
    # Fan-out runs candidates in parallel, so wall-clock is the slowest one.
    latency = max(project_latency_ms(i, tokens) for i in range(len(candidates)))
    passed = any(_passed(task_signals, model) for model in models)
    return ApproachResult(
        approach="ensemble",
        label="Ensemble (fan-out)",
        models=models,
        chosen_model=None,
        cost_usd=cost,
        latency_ms=latency,
        passed=passed,
        detail=(
            f"Fans out to all {len(models)} candidates and keeps the best — "
            "highest coverage, but pays for every model (the fan-out tax)."
        ),
    )


def _router(
    candidates: tuple[Candidate, ...],
    task_signals: Mapping[str, Mapping[str, Any]],
    tokens: Mapping[str, Any],
    pricing: PricingTable,
) -> ApproachResult:
    result = ordered_select(candidates, task_signals)
    tier_by_model = {c.model: i for i, c in enumerate(candidates)}
    attempted = [attempt.model for attempt in result.attempts]
    # Sequential escalation: each attempted call adds its own latency.
    latency = sum(project_latency_ms(tier_by_model.get(m, 0), tokens) for m in attempted)
    chosen = result.chosen_model
    # Cost bills the winning attempt only (matching the trace cost_usd / spotlight).
    cost = pricing.cost_usd(chosen, tokens) if chosen is not None else 0.0
    steps = " → ".join(attempted) if attempted else "—"
    escalated = len(attempted) > 1
    return ApproachResult(
        approach="router",
        label="Cost-aware router",
        models=tuple(attempted),
        chosen_model=chosen,
        cost_usd=cost,
        latency_ms=latency,
        passed=result.accepted,
        detail=(
            f"Escalates cheapest-first: {steps}. "
            + (
                f"Landed on {chosen} — premium-grade accuracy near cheap cost."
                if escalated and result.accepted
                else (
                    f"Cheapest tier {chosen} passed on the first try."
                    if result.accepted
                    else "No candidate passed."
                )
            )
        ),
    )


# -- winners & default selection --------------------------------------------


def _winners(approaches: list[ApproachResult]) -> dict[str, Any]:
    passing = [a for a in approaches if a.passed]
    # Cost/latency winners are judged among approaches that actually pass (the
    # cheapest / fastest *correct* answer); if none pass, fall back to the whole
    # field so a winner is still shown. Accuracy is a binary axis, so *every*
    # passing approach wins it equally — crowning only one would falsely imply it
    # is "more correct" than the others that also pass.
    cost_pool = passing or approaches
    latency_pool = passing or approaches
    cheapest = min(cost_pool, key=lambda a: a.cost_usd)
    fastest = min(latency_pool, key=lambda a: a.latency_ms)
    return {
        "cost": cheapest.approach,
        "latency": fastest.approach,
        "accuracy": [a.approach for a in passing],
    }


def _default_task(arenas: Mapping[str, dict[str, Any]]) -> str:
    """Pick the most instructive task for the opening view.

    Prefers a task where the cheapest single call *fails* but the router still
    passes, and ranks those by how much cheaper the router is than the premium
    single call (the clearest "smart-routing wins" story). Falls back to the
    first task id when nothing escalates.
    """

    best_id: str | None = None
    best_saving = -1.0
    for tid, arena in arenas.items():
        by = {a["approach"]: a for a in arena["approaches"]}
        cheapest, premium, router = by.get("cheapest"), by.get("premium"), by.get("router")
        if not (cheapest and premium and router):
            continue
        if cheapest["passed"] or not router["passed"]:
            continue
        premium_cost = float(premium["cost_usd"])
        saving = premium_cost - float(router["cost_usd"])
        if saving > best_saving:
            best_saving = saving
            best_id = tid
    return best_id or next(iter(arenas))


# -- helpers -----------------------------------------------------------------


def _passed(task_signals: Mapping[str, Mapping[str, Any]], model: str) -> bool:
    row = task_signals.get(model)
    return bool(row is not None and is_clean(row))


def _teaches(arena: Mapping[str, Any]) -> str:
    by = {a["approach"]: a for a in arena["approaches"]}
    cheapest, router = by.get("cheapest"), by.get("router")
    if cheapest and router and not cheapest["passed"] and router["passed"]:
        return "cheap fails · router recovers"
    if cheapest and cheapest["passed"]:
        return "easy · cheapest already passes"
    return "mixed"


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
