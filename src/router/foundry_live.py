"""Live Azure AI Foundry Model Router bridge — *measured* spend, opt-in and gated.

Everything else in this repo is an offline projection over synthetic telemetry
(``measured = false``). This module is the single, isolated seam where a real
Azure AI Foundry **Model Router** deployment turns those projections into
**measured** numbers: it sends real prompts, reads the router's real per-prompt
model choice *and* the real token ``usage`` it billed, and prices that actual
usage. That is the only thing here that egresses, and it only does so when you
explicitly opt in with credentials.

Honesty boundary (kept deliberately strict):

* **Spend can be measured; quality cannot — not by this repo.** A live call
  returns real tokens, so ``total_cost_usd`` is genuine measured spend. Whether
  each answer was *good* still needs a grader you supply; without one, coverage
  falls back to the offline signal projection and is labelled
  ``coverage_measured = false``.
* **``measured = true`` is reserved for a fresh live call.** Replaying a recorded
  usage snapshot exercises the exact same scoring path but is labelled
  ``provenance = recorded`` and ``measured = false`` — a captured measurement,
  not a new one.
* **The default path never egresses.** The Azure SDK is an optional dependency,
  imported lazily only when you build :class:`AzureModelRouterClient`; the client
  is otherwise an injected seam (like :class:`router.metrics.FoundryMetricsEmitter`),
  so tests and CI stay pure-stdlib and deterministic.

The bundled workload is synthetic telemetry with **no prompt text**, so it cannot
be sent to a live endpoint. A real measured run needs a workload whose tasks
carry a ``prompt`` (or ``messages``). CI proves the scoring path with a recorded
usage fixture instead — see :func:`load_recorded_usage`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from policy import PolicyTable

from .pricing import PricingTable
from .select import is_clean

# Default Azure OpenAI data-plane API version used when the environment does not
# pin one. Model Router is reached through the standard chat-completions surface.
DEFAULT_API_VERSION = "2024-10-21"

# Environment variables read for the live bridge. The first present value in each
# tuple wins, so both the Foundry-specific and the generic Azure OpenAI names work.
FOUNDRY_LIVE_ENV_VARS: dict[str, tuple[str, ...]] = {
    "endpoint": ("AZURE_AI_FOUNDRY_ENDPOINT", "AZURE_OPENAI_ENDPOINT"),
    "deployment": ("AZURE_AI_FOUNDRY_MODEL_ROUTER", "AZURE_MODEL_ROUTER_DEPLOYMENT"),
    "api_key": ("AZURE_AI_FOUNDRY_API_KEY", "AZURE_OPENAI_API_KEY"),
    "api_version": ("AZURE_AI_FOUNDRY_API_VERSION", "AZURE_OPENAI_API_VERSION"),
    "connection_string": (
        "AZURE_AI_FOUNDRY_CONNECTION_STRING",
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
    ),
    "pricing_path": ("FOUNDRY_PRICING_PATH", "COST_ROUTER_PRICING"),
}

# Task fields tried, in order, to find the prompt text to send to a live router.
PROMPT_FIELDS: tuple[str, ...] = ("prompt", "text", "input", "question")


@dataclass(frozen=True)
class FoundryConfig:
    """Aggregated, redaction-aware view of the Azure AI Foundry configuration.

    Collects every environment variable the live bridge and the metrics emitter
    read, and exposes a :meth:`status` summary that is safe to print — secrets
    are never returned in the clear. Holds no SDK objects and performs no I/O.
    """

    endpoint: str | None = None
    deployment: str | None = None
    api_key: str | None = None
    api_version: str | None = None
    connection_string: str | None = None
    pricing_path: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> FoundryConfig:
        """Build a config snapshot from environment variables (no I/O, no egress)."""

        environ = env if env is not None else os.environ
        return cls(
            endpoint=_first_env(environ, FOUNDRY_LIVE_ENV_VARS["endpoint"]),
            deployment=_first_env(environ, FOUNDRY_LIVE_ENV_VARS["deployment"]),
            api_key=_first_env(environ, FOUNDRY_LIVE_ENV_VARS["api_key"]),
            api_version=_first_env(environ, FOUNDRY_LIVE_ENV_VARS["api_version"]),
            connection_string=_first_env(environ, FOUNDRY_LIVE_ENV_VARS["connection_string"]),
            pricing_path=_first_env(environ, FOUNDRY_LIVE_ENV_VARS["pricing_path"]),
        )

    @property
    def resolved_api_version(self) -> str:
        return self.api_version or DEFAULT_API_VERSION

    @property
    def router_configured(self) -> bool:
        """True when an endpoint and a router deployment are both set."""

        return bool(self.endpoint and self.deployment)

    @property
    def credentialed(self) -> bool:
        """True when the router is configured *and* an API key is present."""

        return bool(self.router_configured and self.api_key)

    @property
    def observability_configured(self) -> bool:
        """True when a Foundry / Application Insights connection string is set."""

        return bool(self.connection_string)

    def missing(self) -> list[str]:
        """Return the human-readable names of the still-missing required settings."""

        gaps: list[str] = []
        if not self.endpoint:
            gaps.append(FOUNDRY_LIVE_ENV_VARS["endpoint"][0])
        if not self.deployment:
            gaps.append(FOUNDRY_LIVE_ENV_VARS["deployment"][0])
        if not self.api_key:
            gaps.append(FOUNDRY_LIVE_ENV_VARS["api_key"][0])
        return gaps

    def status(self) -> dict[str, Any]:
        """Return a **redacted** status dict safe to print or serve.

        Endpoints are host-only, keys and connection strings are masked to their
        last four characters, and deployment/API-version (not secrets) are shown
        verbatim so an operator can confirm what is wired without leaking secrets.
        """

        return {
            "router_configured": self.router_configured,
            "credentialed": self.credentialed,
            "observability_configured": self.observability_configured,
            "endpoint": _redact_endpoint(self.endpoint),
            "deployment": self.deployment or None,
            "api_key": _mask_secret(self.api_key),
            "api_version": self.resolved_api_version,
            "connection_string": _mask_secret(self.connection_string),
            "pricing_path": self.pricing_path or "(bundled illustrative — measured=false)",
            "missing": self.missing(),
            "measured": False,
        }


@dataclass(frozen=True)
class RouterOutcome:
    """One task's real router result: the chosen model and the tokens it billed.

    ``usage`` is normalized to the pricing table's token kinds
    (``input``/``cached``/``output``/``reasoning``). ``provenance`` records how
    the outcome was obtained: ``live`` (a fresh call — the only value that lets a
    summary claim ``measured = true``), ``recorded`` (replayed snapshot), or
    ``illustrative``.
    """

    model: str
    usage: dict[str, float]
    provenance: str = "live"

    def cost_usd(
        self, pricing: PricingTable, *, model_aliases: Mapping[str, str] | None = None
    ) -> float:
        key = (model_aliases or {}).get(self.model, self.model)
        return pricing.cost_usd(key, self.usage)


@runtime_checkable
class MeasuringRouterClient(Protocol):
    """Anything that turns one task into a :class:`RouterOutcome`."""

    def complete(self, task: Mapping[str, Any]) -> RouterOutcome:  # pragma: no cover - protocol
        ...


@dataclass
class RecordedRouterClient:
    """Replay recorded per-task outcomes — no network, fully deterministic.

    Used by CI and demos to exercise the measured scoring path without a live
    call. Every outcome it returns carries ``provenance = recorded`` (unless the
    fixture said otherwise), so summaries built from it are honestly *not*
    ``measured = true``.
    """

    outcomes: Mapping[str, RouterOutcome]
    key_field: str = "task_id"

    def complete(self, task: Mapping[str, Any]) -> RouterOutcome:
        task_id = str(task.get(self.key_field, task.get("id", "")))
        outcome = self.outcomes.get(task_id)
        if outcome is None:
            raise KeyError(f"no recorded outcome for task {task_id!r}")
        return outcome


@dataclass
class AzureModelRouterClient:
    """Live client for an Azure AI Foundry Model Router deployment.

    Calls the deployment through the standard chat-completions surface, then
    reads the response's ``model`` (the underlying model the router picked) and
    its real ``usage`` (the tokens Azure billed). The Azure SDK is imported
    lazily in :meth:`_sdk_client`, so importing this module never requires it and
    the default path never egresses. Inject ``sdk_client`` to test without a
    network or an SDK.
    """

    config: FoundryConfig
    sdk_client: Any = None
    max_output_tokens: int = 512
    temperature: float = 0.0

    def complete(self, task: Mapping[str, Any]) -> RouterOutcome:
        if not self.config.credentialed:
            raise RuntimeError(
                "AzureModelRouterClient is not credentialed: set "
                f"{FOUNDRY_LIVE_ENV_VARS['endpoint'][0]}, "
                f"{FOUNDRY_LIVE_ENV_VARS['deployment'][0]} and "
                f"{FOUNDRY_LIVE_ENV_VARS['api_key'][0]} first."
            )
        messages = _messages_for(task)
        client = self._sdk_client()
        response = client.chat.completions.create(
            model=self.config.deployment,
            messages=messages,
            max_tokens=self.max_output_tokens,
            temperature=self.temperature,
        )
        return RouterOutcome(
            model=_response_model(response) or str(self.config.deployment),
            usage=_usage_from_response(response),
            provenance="live",
        )

    def _sdk_client(self) -> Any:
        if self.sdk_client is not None:
            return self.sdk_client
        try:
            from openai import AzureOpenAI
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "The Azure OpenAI SDK is not installed. Install the live extra "
                "with `pip install foundry-cost-router[foundry]` (or `pip install "
                "openai`) to make live measured calls."
            ) from exc
        self.sdk_client = AzureOpenAI(
            azure_endpoint=str(self.config.endpoint),
            api_key=str(self.config.api_key),
            api_version=self.config.resolved_api_version,
        )
        return self.sdk_client


def measured_router_summary(
    workload: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Mapping[str, Mapping[str, Any]]],
    policy: PolicyTable,
    pricing: PricingTable,
    *,
    client: MeasuringRouterClient,
    grader: Callable[[str, Mapping[str, Any], RouterOutcome], bool] | None = None,
    model_aliases: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Score a live/recorded Model Router run on **real** token usage.

    For each task the ``client`` returns a :class:`RouterOutcome`; cost is that
    outcome's real usage priced by ``pricing`` (not the synthetic ``task[tokens]``
    the offline arms use). Coverage is measured only when a ``grader`` is
    supplied; otherwise it is the offline signal projection for the chosen model
    and ``labels.coverage_measured`` is ``false``.

    ``labels.measured`` is ``true`` only when every outcome's provenance is
    ``live`` — a fresh measurement. ``model_aliases`` maps a provider model name
    (e.g. ``gpt-4o``) onto a pricing/signals key when they differ.
    """

    total = 0.0
    counted = 0
    graded = 0
    accepted = 0
    coverable = 0
    model_counts: dict[str, int] = {}
    provenances: set[str] = set()
    for task_id, task in workload.items():
        outcome = client.complete(task)
        provenances.add(outcome.provenance)
        counted += 1
        total += outcome.cost_usd(pricing, model_aliases=model_aliases)
        key = (model_aliases or {}).get(outcome.model, outcome.model)
        model_counts[key] = model_counts.get(key, 0) + 1
        if grader is not None:
            graded += 1
            if grader(str(task_id), task, outcome):
                accepted += 1
        else:
            row = signals.get(str(task_id), {}).get(key)
            if row is not None:
                coverable += 1
                if is_clean(row):
                    accepted += 1
    coverage_measured = grader is not None
    denom = counted if coverage_measured else coverable
    provenance = _combine_provenance(provenances)
    measured = counted > 0 and provenance == "live"
    return {
        "total_cost_usd": round(total, 6),
        "coverage": (accepted / denom) if denom else 0.0,
        "tasks": counted,
        "accepted": accepted,
        "graded": graded,
        "coverable": coverable,
        "avg_usd_per_task": round(total / counted, 6) if counted else 0.0,
        "model_counts": model_counts,
        "selection": "azure-model-router",
        "labels": {
            "measured": measured,
            "spend_source": "provider-usage",
            "provenance": provenance,
            "coverage_measured": coverage_measured,
        },
    }


def load_recorded_usage(path: Path | str) -> dict[str, RouterOutcome]:
    """Load a recorded ``task_id -> {model, usage}`` snapshot as outcomes.

    Accepts ``{"outcomes": {...}}`` or a bare mapping. Each entry becomes a
    :class:`RouterOutcome`; provenance defaults to ``recorded`` (per entry or the
    file's top-level ``labels.provenance``) so replays never masquerade as fresh
    measurements.
    """

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("recorded usage file must be a JSON object")
    default_prov = "recorded"
    labels = data.get("labels")
    if isinstance(labels, Mapping) and labels.get("provenance"):
        default_prov = str(labels["provenance"])
    raw = data.get("outcomes", data)
    if not isinstance(raw, Mapping):
        raise ValueError("recorded usage 'outcomes' must be a mapping")
    outcomes: dict[str, RouterOutcome] = {}
    for task_id, entry in raw.items():
        if task_id in {"labels", "outcomes", "version", "_note"}:
            continue
        if not isinstance(entry, Mapping) or "model" not in entry:
            continue
        usage = entry.get("usage") or {}
        outcomes[str(task_id)] = RouterOutcome(
            model=str(entry["model"]),
            usage={k: float(v) for k, v in usage.items()},
            provenance=str(entry.get("provenance", default_prov)),
        )
    return outcomes


def _messages_for(task: Mapping[str, Any]) -> list[dict[str, str]]:
    existing = task.get("messages")
    if isinstance(existing, list) and existing:
        return [dict(message) for message in existing]
    prompt = _extract_prompt(task)
    if not prompt:
        raise ValueError(
            "task has no prompt to send: add a 'prompt' or 'messages' field. The "
            "bundled synthetic telemetry has none, so it cannot be measured live."
        )
    return [{"role": "user", "content": prompt}]


def _extract_prompt(task: Mapping[str, Any]) -> str | None:
    for field_name in PROMPT_FIELDS:
        value = task.get(field_name)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _usage_from_response(response: Any) -> dict[str, float]:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, Mapping):
        usage = response.get("usage")
    prompt_tokens = _usage_field(usage, "prompt_tokens")
    completion_tokens = _usage_field(usage, "completion_tokens")
    cached = _nested_usage_field(usage, "prompt_tokens_details", "cached_tokens")
    reasoning = _nested_usage_field(usage, "completion_tokens_details", "reasoning_tokens")
    return {
        "input": prompt_tokens,
        "cached": min(cached, prompt_tokens),
        "output": max(completion_tokens - reasoning, 0.0),
        "reasoning": reasoning,
    }


def _response_model(response: Any) -> str | None:
    model = getattr(response, "model", None)
    if model is None and isinstance(response, Mapping):
        model = response.get("model")
    return str(model) if model else None


def _usage_field(usage: Any, name: str) -> float:
    if usage is None:
        return 0.0
    value = getattr(usage, name, None)
    if value is None and isinstance(usage, Mapping):
        value = usage.get(name)
    return _to_float(value)


def _nested_usage_field(usage: Any, group: str, name: str) -> float:
    if usage is None:
        return 0.0
    details = getattr(usage, group, None)
    if details is None and isinstance(usage, Mapping):
        details = usage.get(group)
    return _usage_field(details, name)


def _combine_provenance(provenances: set[str]) -> str:
    if not provenances:
        return "none"
    if provenances == {"live"}:
        return "live"
    if len(provenances) == 1:
        return next(iter(provenances))
    return "mixed"


def _mask_secret(value: str | None) -> str:
    if not value:
        return "missing"
    tail = value[-4:] if len(value) >= 4 else value
    return f"set (****{tail})"


def _redact_endpoint(value: str | None) -> str | None:
    if not value:
        return None
    from urllib.parse import urlsplit

    parts = urlsplit(value)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return "set"


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _first_env(env: Mapping[str, str], names: Sequence[str]) -> str | None:
    for name in names:
        value = env.get(name)
        if value:
            return value
    return None
