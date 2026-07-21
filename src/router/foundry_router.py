"""Gated adapter for Azure AI Foundry Model Router (offline by default).

Azure AI Foundry Model Router is the *single-call* routing layer: it picks one
model per prompt, up front. This adapter is a thin, dependency-free seam that
lets a real deployment's routing **decisions** replace the offline
difficulty-tiered proxy in :func:`router.baseline.model_router_summary` — while
scoring cost and coverage on the exact same offline signals so the two are
comparable on one frontier.

Honesty boundary (important): swapping in *live decisions* does not by itself
make the numbers measured. The cost/coverage here are still offline projections
over synthetic signals and illustrative pricing (``measured = false``); only the
model *choice* may be live. Turning the projection into measured spend needs
real token usage and a real eval, which this offline repo does not ship. The
``labels`` record provenance (``live`` / ``recorded`` / ``illustrative``) so the
distinction is never lost.

Like :class:`router.metrics.FoundryMetricsEmitter`, the network call is an
**injected** ``client`` callable: this module never imports an SDK and the
default path never egresses, so it stays test-safe and fully deterministic. The
real-Azure implementation of that callable is :func:`azure_router_choice_client`,
which adapts the live :class:`router.foundry_live.AzureModelRouterClient` (the
keyless SDK bridge) into a ``(deployment, task) -> model`` choice function.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from policy import Candidate, PolicyTable

from .baseline import model_router_pick, score_single_call_arm
from .foundry_live import AzureModelRouterClient, normalize_model_name
from .pricing import PricingTable

# Environment variables that point at an Azure AI Foundry Model Router
# deployment. When an endpoint + deployment are present the adapter reports
# ``configured``; it is only ``available`` once a ``client`` callable is also
# injected, because this module never performs the HTTP call itself.
FOUNDRY_ROUTER_ENV_VARS: dict[str, tuple[str, ...]] = {
    "endpoint": ("AZURE_AI_FOUNDRY_ENDPOINT", "AZURE_OPENAI_ENDPOINT"),
    "deployment": ("AZURE_AI_FOUNDRY_MODEL_ROUTER", "AZURE_MODEL_ROUTER_DEPLOYMENT"),
    "api_key": ("AZURE_AI_FOUNDRY_API_KEY", "AZURE_OPENAI_API_KEY"),
}

# Injected client: (deployment, task) -> chosen model name. Kept SDK-agnostic so
# callers can wrap azure-ai-inference / openai / a mock without this module
# depending on any of them.
RouterClient = Callable[[str, Mapping[str, Any]], str]


@dataclass
class FoundryModelRouter:
    """Env-gated seam to an Azure AI Foundry Model Router deployment.

    Holds connection details and an injected ``client`` callable. With no client
    the adapter is inert and callers fall back to the offline ``model_router``
    arm (``measured = false``). With a client it returns the deployment's real
    per-prompt model choice via :meth:`choose`.
    """

    endpoint: str | None = None
    deployment: str | None = None
    api_key: str | None = None
    client: RouterClient | None = None

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        client: RouterClient | None = None,
    ) -> FoundryModelRouter:
        """Build an adapter from environment variables, with an optional client."""

        environ = env if env is not None else os.environ
        return cls(
            endpoint=_first_env(environ, FOUNDRY_ROUTER_ENV_VARS["endpoint"]),
            deployment=_first_env(environ, FOUNDRY_ROUTER_ENV_VARS["deployment"]),
            api_key=_first_env(environ, FOUNDRY_ROUTER_ENV_VARS["api_key"]),
            client=client,
        )

    @property
    def configured(self) -> bool:
        """True when an endpoint and a router deployment are both set."""

        return bool(self.endpoint and self.deployment)

    @property
    def available(self) -> bool:
        """True when configured *and* a client callable is injected to call it."""

        return bool(self.configured and self.client is not None)

    def choose(self, task: Mapping[str, Any]) -> str:
        """Return the deployment's chosen model for one task (live, measured decision).

        Raises :class:`RuntimeError` when the adapter is not available so callers
        never silently pretend a live decision was made.
        """

        if not self.available:
            raise RuntimeError(
                "FoundryModelRouter is not available: set the endpoint/deployment "
                "environment variables and inject a `client` callable. Until then "
                "the offline model_router arm (measured=false) stands in."
            )
        assert self.client is not None and self.deployment is not None  # for type-checkers
        return str(self.client(self.deployment, task))


def summary_from_choices(
    workload: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Mapping[str, Any]]],
    policy: PolicyTable,
    pricing: PricingTable,
    choices: Mapping[str, str],
    *,
    provenance: str = "recorded",
) -> dict[str, Any]:
    """Score a set of per-task model choices as a single-call router arm.

    ``choices`` maps ``task_id -> model name`` (from a live deployment or a
    recorded fixture). Unknown or missing choices fall back to the offline
    difficulty-tiered pick so the arm is always fully scored. Cost and coverage
    are offline projections (``measured = false``); ``labels.decisions`` records
    whether the choices were ``live`` / ``recorded`` / ``illustrative``.
    """

    def pick(task_id: str, task: Mapping[str, Any], candidates: tuple[Candidate, ...]) -> Candidate:
        name = choices.get(task_id)
        match = _candidate_by_model(candidates, name) if name else None
        return match or model_router_pick(task, candidates)

    result = score_single_call_arm(workload, signals, policy, pricing, pick=pick)
    result["selection"] = "foundry-model-router"
    result["labels"] = {"measured": False, "decisions": provenance}
    return result


def live_router_summary(
    workload: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Mapping[str, Any]]],
    policy: PolicyTable,
    pricing: PricingTable,
    router: FoundryModelRouter,
) -> dict[str, Any]:
    """Query a live Model Router for each task and score its decisions.

    Requires ``router.available``. The returned arm reflects the deployment's
    real per-prompt choices, scored on the same offline signals (still
    ``measured = false``) so it lands comparably on the frontier.
    """

    choices = {str(task_id): router.choose(task) for task_id, task in workload.items()}
    return summary_from_choices(
        workload, signals, policy, pricing, choices, provenance="live"
    )


def load_recorded_choices(path: Path | str) -> dict[str, str]:
    """Load a recorded ``task_id -> model`` choice map from a JSON fixture.

    Accepts either a bare mapping or ``{"choices": {...}}``. Illustrative and
    offline — a captured snapshot of what a router picked, not measured spend.
    """

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = data.get("choices", data) if isinstance(data, Mapping) else data
    if not isinstance(raw, Mapping):
        raise ValueError("recorded choices file must be a mapping or {'choices': {...}}")
    return {str(task_id): str(model) for task_id, model in raw.items()}


def azure_router_choice_client(
    client: AzureModelRouterClient,
    *,
    normalize: bool = True,
) -> RouterClient:
    """Adapt the live :class:`AzureModelRouterClient` into a choice callable.

    This is the **real-Azure** implementation of the injected :data:`RouterClient`
    seam: it calls the deployment through the keyless SDK bridge shipped for the
    measured path (item 1) and returns just the model the router picked — the
    single-call *decision*. Model ids are normalized to a stable pricing/candidate
    name by default (``gpt-5.4-2026-03-05`` → ``gpt-5.4``). Inject the result as
    ``FoundryModelRouter(client=…)`` to run :meth:`FoundryModelRouter.choose` /
    :func:`live_router_summary` against a live deployment.
    """

    def choose(deployment: str, task: Mapping[str, Any]) -> str:
        outcome = client.complete(task, deployment=deployment)
        return normalize_model_name(outcome.model) if normalize else outcome.model

    return choose


_CHOICE_CAPTURE_NOTE = (
    "CAPTURED LIVE from an Azure AI Foundry Model Router: each entry is the model "
    "the router actually picked for that prompt (the single-call decision). "
    "Replaying these choices is honestly labelled decisions=recorded / "
    "measured=false — only the DECISIONS are a snapshot; scoring them on the "
    "offline signals stays an offline projection. Re-capture with "
    "`cost-router foundry router --live --capture <path>`."
)


def capture_recorded_choices(
    workload: Mapping[str, Mapping[str, Any]],
    router: FoundryModelRouter,
    *,
    resource: Mapping[str, Any] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Capture genuine per-task router choices from a live deployment.

    The inverse of :func:`load_recorded_choices`: runs a real-client ``router``
    over prompt-bearing tasks and records the genuine ``task_id -> chosen model``.
    Each snapshot is honestly labelled ``decisions = recorded`` / ``measured =
    false`` (a replay of choices is not a fresh measurement); the top-level
    ``captured_from = live`` records that its source was a real Azure call. Cost
    and coverage remain offline projections when these choices are later scored.
    """

    choices = {str(task_id): router.choose(workload[task_id]) for task_id in sorted(workload)}
    snapshot: dict[str, Any] = {
        "version": 1,
        "_note": note or _CHOICE_CAPTURE_NOTE,
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "labels": {"measured": False, "decisions": "recorded", "captured_from": "live"},
    }
    if resource:
        snapshot["resource"] = dict(resource)
    snapshot["choices"] = choices
    return snapshot


def _candidate_by_model(
    candidates: tuple[Candidate, ...],
    name: str | None,
) -> Candidate | None:
    if not name:
        return None
    for candidate in candidates:
        if candidate.model == name:
            return candidate
    return None


def _first_env(env: Mapping[str, str], names: Sequence[str]) -> str | None:
    for name in names:
        value = env.get(name)
        if value:
            return value
    return None
