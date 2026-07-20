"""Live Azure AI Foundry arena — one problem, four ways, measured on real calls.

This is the *measured* twin of the offline arena in :mod:`router.arena`. Where
the offline arena projects cost/latency/accuracy over synthetic signals
(``labels.measured = false``), this module dispatches each strategy to **real
Azure AI Foundry deployments** over a keyless Microsoft Entra ID connection and
records the tokens Azure actually billed, the wall-clock latency, and the
underlying model the Model Router picked (``labels.measured = true``).

Four strategies, each a real deployment call on this resource:

======== ==================== ============================================
arm      deployment           what it demonstrates
======== ==================== ============================================
cheapest ``gpt-5.4-nano``     one small model, always — the cheap floor
premium  ``gpt-5.4``          one frontier model, always — the naive ceiling
ensemble fan-out slate        call several models, keep the best (pay the tax)
router   ``model-router``     Foundry picks one model per prompt (the hero)
======== ==================== ============================================

Design goals (readable-first):

* **One tiny transport.** :class:`FoundryFleet` builds the keyless client once
  and calls any deployment by name, always returning a :class:`LiveCall` with
  the underlying model, real usage, and measured latency.
* **Strategies are pure functions** of ``(fleet, task, slate, pricing)`` — no
  globals, no hidden state, trivially testable with an injected fake client.
* **Honest labels.** ``measured = true`` only when every call's provenance is
  ``live``; the dollar figure is real usage priced by an injected rate card.
* **Clear ledger.** :class:`MeasuredArenaLedger` appends one honest JSONL row
  per task — separate from the strict offline audit ledger (which is, by
  contract, always ``measured = false``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

from .foundry_live import AzureModelRouterClient, FoundryConfig, RouterOutcome
from .pricing import PricingTable

# A dated model id like ``gpt-5.4-2026-03-05`` prices/display against its base
# ``gpt-5.4``; the vendor/tier is preserved, only the version date is stripped.
_VERSION_SUFFIX = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def normalize_model_name(model: str | None) -> str:
    """Strip a trailing ``-YYYY-MM-DD`` version suffix from a model id."""

    if not model:
        return ""
    return _VERSION_SUFFIX.sub("", model.strip())


@dataclass(frozen=True)
class ArenaTask:
    """One self-contained problem to send to every arm.

    ``system`` is an optional per-experiment system prompt; ``title`` is a short
    human label used in reports.
    """

    task_id: str
    prompt: str
    title: str = ""
    system: str | None = None

    def payload(self) -> dict[str, Any]:
        """Shape the task for the live client (``prompt`` + optional ``system``)."""

        body: dict[str, Any] = {"task_id": self.task_id, "prompt": self.prompt}
        if self.system:
            body["system"] = self.system
        return body


@dataclass(frozen=True)
class FleetSlate:
    """Which deployment backs each arm (all on one Foundry resource).

    ``ensemble`` is the fan-out slate — the models called in parallel, cheapest
    to strongest; the strongest tier's answer is the one kept.
    """

    router: str = "model-router"
    cheapest: str = "gpt-5.4-nano"
    premium: str = "gpt-5.4"
    ensemble: tuple[str, ...] = ("gpt-5.4-nano", "gpt-5.4-mini", "gpt-5.4")

    def deployments(self) -> tuple[str, ...]:
        """Every distinct deployment this slate touches (for status/preflight)."""

        seen: list[str] = []
        for name in (self.router, self.cheapest, self.premium, *self.ensemble):
            if name not in seen:
                seen.append(name)
        return tuple(seen)


@dataclass(frozen=True)
class LiveCall:
    """One real deployment call: the model that answered and the tokens billed."""

    deployment: str
    model: str
    usage: dict[str, float]
    latency_ms: float
    provenance: str = "live"

    def cost_usd(self, pricing: PricingTable) -> float:
        """Price this call's real usage against the injected rate card."""

        return pricing.cost_usd(self.model, self.usage)

    def to_dict(self, pricing: PricingTable) -> dict[str, Any]:
        return {
            "deployment": self.deployment,
            "model": self.model,
            "usage": self.usage,
            "latency_ms": round(self.latency_ms, 1),
            "cost_usd": self.cost_usd(pricing),
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class ArmResult:
    """One strategy's measured result for a single task."""

    arm: str
    strategy: str
    deployment: str
    chosen_model: str
    fanout: int
    billing: str
    cost_usd: float
    latency_ms: float
    calls: tuple[LiveCall, ...]

    @property
    def measured(self) -> bool:
        return bool(self.calls) and all(c.provenance == "live" for c in self.calls)

    def to_dict(self, pricing: PricingTable) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "strategy": self.strategy,
            "deployment": self.deployment,
            "chosen_model": self.chosen_model,
            "fanout": self.fanout,
            "billing": self.billing,
            "cost_usd": self.cost_usd,
            "latency_ms": round(self.latency_ms, 1),
            "calls": [c.to_dict(pricing) for c in self.calls],
        }


@dataclass(frozen=True)
class ArenaOutcome:
    """All four arms for one task, plus the per-axis winners and honest labels."""

    task: ArenaTask
    arms: dict[str, ArmResult]
    winners: dict[str, str]
    labels: dict[str, Any]

    def to_dict(self, pricing: PricingTable) -> dict[str, Any]:
        return {
            "task_id": self.task.task_id,
            "title": self.task.title,
            "prompt": self.task.prompt,
            "arms": {name: arm.to_dict(pricing) for name, arm in self.arms.items()},
            "winners": self.winners,
            "labels": self.labels,
        }


# --------------------------------------------------------------------------- #
# Transport: build the keyless client once, call any deployment by name.
# --------------------------------------------------------------------------- #


@dataclass
class FoundryFleet:
    """Thin keyless transport over one Foundry resource.

    Wraps a single :class:`AzureModelRouterClient` (the shared SDK client +
    Entra token provider) and calls any deployment by name, timing each request
    so latency is measured, not projected.
    """

    client: AzureModelRouterClient

    @classmethod
    def from_config(
        cls,
        config: FoundryConfig,
        *,
        sdk_client: Any = None,
        token_provider: Any = None,
        max_output_tokens: int = 2048,
    ) -> FoundryFleet:
        return cls(
            AzureModelRouterClient(
                config=config,
                sdk_client=sdk_client,
                token_provider=token_provider,
                max_output_tokens=max_output_tokens,
            )
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, **kwargs: Any) -> FoundryFleet:
        return cls.from_config(FoundryConfig.from_env(env), **kwargs)

    @property
    def credentialed(self) -> bool:
        return self.client.config.credentialed

    def call(self, deployment: str, task: ArenaTask) -> LiveCall:
        """Run one task through ``deployment`` and capture usage + latency."""

        started = perf_counter()
        outcome: RouterOutcome = self.client.complete(task.payload(), deployment=deployment)
        latency_ms = (perf_counter() - started) * 1000.0
        return LiveCall(
            deployment=deployment,
            model=normalize_model_name(outcome.model) or deployment,
            usage=dict(outcome.usage),
            latency_ms=latency_ms,
            provenance=outcome.provenance,
        )

    def fan_out(self, deployments: Sequence[str], task: ArenaTask) -> tuple[LiveCall, ...]:
        """Call several deployments in parallel; measured latency is the slowest."""

        if len(deployments) == 1:
            return (self.call(deployments[0], task),)
        with ThreadPoolExecutor(max_workers=len(deployments)) as pool:
            return tuple(pool.map(lambda dep: self.call(dep, task), deployments))


# --------------------------------------------------------------------------- #
# Strategies: pure functions of (fleet, task, slate, pricing) -> ArmResult.
# --------------------------------------------------------------------------- #


def cheapest_arm(fleet: FoundryFleet, task: ArenaTask, slate: FleetSlate, pricing: PricingTable):
    call = fleet.call(slate.cheapest, task)
    return _single(
        call, pricing, arm="cheapest", strategy="Cheapest single model (always the small tier)"
    )


def premium_arm(fleet: FoundryFleet, task: ArenaTask, slate: FleetSlate, pricing: PricingTable):
    call = fleet.call(slate.premium, task)
    return _single(
        call, pricing, arm="premium", strategy="Premium single model (always the frontier tier)"
    )


def router_arm(fleet: FoundryFleet, task: ArenaTask, slate: FleetSlate, pricing: PricingTable):
    call = fleet.call(slate.router, task)
    return ArmResult(
        arm="router",
        strategy="Foundry Model Router — one model chosen per prompt",
        deployment=slate.router,
        chosen_model=call.model,
        fanout=1,
        billing="winner-only",
        cost_usd=call.cost_usd(pricing),
        latency_ms=call.latency_ms,
        calls=(call,),
    )


def ensemble_arm(fleet: FoundryFleet, task: ArenaTask, slate: FleetSlate, pricing: PricingTable):
    calls = fleet.fan_out(slate.ensemble, task)
    # Fan-out tax: you pay for every model, not just the one you keep.
    total = round(sum(c.cost_usd(pricing) for c in calls), 6)
    # Parallel fan-out: the wall-clock is the slowest call, not the sum.
    latency = max(c.latency_ms for c in calls)
    kept = calls[-1]  # keep the strongest tier's answer (no live grader to score)
    return ArmResult(
        arm="ensemble",
        strategy=f"Fan-out x{len(calls)} then keep the best (pay the tax)",
        deployment=" + ".join(slate.ensemble),
        chosen_model=kept.model,
        fanout=len(calls),
        billing="sum-all-fanout",
        cost_usd=total,
        latency_ms=latency,
        calls=calls,
    )


ARMS = (cheapest_arm, premium_arm, ensemble_arm, router_arm)


def _single(call: LiveCall, pricing: PricingTable, *, arm: str, strategy: str) -> ArmResult:
    return ArmResult(
        arm=arm,
        strategy=strategy,
        deployment=call.deployment,
        chosen_model=call.model,
        fanout=1,
        billing="single-call",
        cost_usd=call.cost_usd(pricing),
        latency_ms=call.latency_ms,
        calls=(call,),
    )


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def run_arena_task(
    fleet: FoundryFleet,
    task: ArenaTask,
    slate: FleetSlate,
    pricing: PricingTable,
) -> ArenaOutcome:
    """Run all four arms for one task and pick the per-axis winners."""

    arms = {
        "cheapest": cheapest_arm(fleet, task, slate, pricing),
        "premium": premium_arm(fleet, task, slate, pricing),
        "ensemble": ensemble_arm(fleet, task, slate, pricing),
        "router": router_arm(fleet, task, slate, pricing),
    }
    winners = {
        "cost": min(arms.values(), key=lambda a: a.cost_usd).arm,
        "latency": min(arms.values(), key=lambda a: a.latency_ms).arm,
    }
    measured = all(arm.measured for arm in arms.values())
    labels = {
        "measured": measured,
        "provenance": "live" if measured else "mixed",
        "spend_source": "provider-usage",
        "cost_basis": "list-price",
        "accuracy": "ungraded",  # cost + latency are measured; correctness needs a grader
    }
    return ArenaOutcome(task=task, arms=arms, winners=winners, labels=labels)


def run_live_arena(
    fleet: FoundryFleet,
    tasks: Iterable[ArenaTask],
    slate: FleetSlate,
    pricing: PricingTable,
) -> list[ArenaOutcome]:
    """Run the arena for every task in order."""

    return [run_arena_task(fleet, task, slate, pricing) for task in tasks]


def arena_report(outcomes: Sequence[ArenaOutcome], pricing: PricingTable) -> dict[str, Any]:
    """Build a JSON-ready measured report with per-arm aggregates and labels."""

    per_task = [o.to_dict(pricing) for o in outcomes]
    arm_names = ("cheapest", "premium", "ensemble", "router")
    totals = {
        name: {
            "total_cost_usd": round(sum(o.arms[name].cost_usd for o in outcomes), 6),
            "avg_latency_ms": round(
                sum(o.arms[name].latency_ms for o in outcomes) / len(outcomes), 1
            )
            if outcomes
            else 0.0,
        }
        for name in arm_names
    }
    router_models: dict[str, int] = {}
    for o in outcomes:
        picked = o.arms["router"].chosen_model
        router_models[picked] = router_models.get(picked, 0) + 1
    measured = bool(outcomes) and all(o.labels["measured"] for o in outcomes)
    premium_total = totals["premium"]["total_cost_usd"]
    router_total = totals["router"]["total_cost_usd"]
    savings_pct = (
        round((premium_total - router_total) / premium_total * 100, 1) if premium_total else 0.0
    )
    return {
        "version": 1,
        "selection": "foundry-live-arena",
        "tasks": len(outcomes),
        "arm_totals": totals,
        "router_model_mix": router_models,
        "router_vs_premium_savings_pct": savings_pct,
        "labels": {
            "measured": measured,
            "provenance": "live" if measured else "mixed",
            "spend_source": "provider-usage",
            "cost_basis": "list-price",
            "accuracy": "ungraded",
        },
        "results": per_task,
    }


# --------------------------------------------------------------------------- #
# Inputs & ledger
# --------------------------------------------------------------------------- #


def load_arena_tasks(path: Path | str, *, system: str | None = None) -> list[ArenaTask]:
    """Load prompt-bearing tasks from a JSONL workload (one object per line)."""

    tasks: list[ArenaTask] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        prompt = row.get("prompt") or row.get("text") or row.get("input")
        if not prompt:
            continue
        tasks.append(
            ArenaTask(
                task_id=str(row.get("task_id") or row.get("id") or f"task-{len(tasks) + 1}"),
                prompt=str(prompt),
                title=str(row.get("title", "")),
                system=row.get("system", system),
            )
        )
    return tasks


@dataclass
class MeasuredArenaLedger:
    """Append-only JSONL ledger of measured arena rows (honest labels).

    Separate from :mod:`router.ledger` (the offline audit trail, which is by
    contract ``measured = false``): this ledger only ever holds rows from real
    live calls, so it is the home for ``measured = true`` provenance.
    """

    path: Path
    pricing: PricingTable
    _entries: list[dict[str, Any]] = field(default_factory=list)

    def record(self, outcome: ArenaOutcome) -> None:
        self._entries.append(outcome.to_dict(self.pricing))

    def flush(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            for entry in self._entries:
                handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        written = len(self._entries)
        self._entries.clear()
        return written
