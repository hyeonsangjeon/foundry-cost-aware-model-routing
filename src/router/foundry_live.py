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
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from policy import PolicyTable

from .pricing import PricingTable
from .select import is_clean

# Default Azure OpenAI data-plane API version used when the environment does not
# pin one. Model Router is reached through the standard chat-completions surface.
DEFAULT_API_VERSION = "2024-10-21"

# Default AAD scope for data-plane calls to Azure AI / Cognitive Services.
DEFAULT_TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"

# Environment variables read for the live bridge. The first present value in each
# tuple wins, so both the Foundry-specific and the generic Azure OpenAI names work.
FOUNDRY_LIVE_ENV_VARS: dict[str, tuple[str, ...]] = {
    "endpoint": ("AZURE_AI_FOUNDRY_ENDPOINT", "AZURE_OPENAI_ENDPOINT"),
    "deployment": ("AZURE_AI_FOUNDRY_MODEL_ROUTER", "AZURE_MODEL_ROUTER_DEPLOYMENT"),
    "api_key": ("AZURE_AI_FOUNDRY_API_KEY", "AZURE_OPENAI_API_KEY"),
    "api_version": ("AZURE_AI_FOUNDRY_API_VERSION", "AZURE_OPENAI_API_VERSION"),
    "auth_mode": ("AZURE_AI_FOUNDRY_AUTH",),
    "token_scope": ("AZURE_AI_FOUNDRY_TOKEN_SCOPE",),
    "connection_string": (
        "AZURE_AI_FOUNDRY_CONNECTION_STRING",
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
    ),
    "pricing_path": ("FOUNDRY_PRICING_PATH", "COST_ROUTER_PRICING"),
}

# Accepted spellings of AZURE_AI_FOUNDRY_AUTH that select Microsoft Entra ID
# (Azure AD) token auth instead of an API key.
ENTRA_AUTH_ALIASES: frozenset[str] = frozenset(
    {"entra", "entra-id", "entraid", "aad", "azuread", "azure_ad", "azure-ad", "identity"}
)
KEY_AUTH_ALIASES: frozenset[str] = frozenset({"key", "apikey", "api_key", "api-key"})

# Task fields tried, in order, to find the prompt text to send to a live router.
PROMPT_FIELDS: tuple[str, ...] = ("prompt", "text", "input", "question")


def load_dotenv_file(
    path: Path | str = ".env",
    *,
    environ: MutableMapping[str, str] | None = None,
    override: bool = False,
) -> list[str]:
    """Populate ``environ`` from a ``.env`` file; return the names actually set.

    The live bridge and metrics emitter read :data:`os.environ`, and the manual
    tells users to put their Foundry settings in ``.env`` — this is the small,
    dependency-free loader that makes that promise real. It is deliberately
    conservative so the offline/deterministic default is never disturbed:

    * A missing file is a no-op (returns ``[]``); CI and default runs carry no
      ``.env`` and are unaffected.
    * With ``override=False`` (the default) an existing, non-empty environment
      value **wins**, so explicit exports and CI settings are never replaced.
    * Only ``KEY=VALUE`` lines are honoured. Blank lines, ``#`` comments and a
      leading ``export`` are ignored; surrounding single/double quotes are
      stripped. There is no shell expansion and no command execution — values
      are taken literally.

    Never prints or logs values; secrets live only in ``environ``.
    """

    target = os.environ if environ is None else environ
    env_path = Path(path)
    if not env_path.is_file():
        return []
    applied: list[str] = []
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key.isidentifier():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not override and target.get(key):
            continue
        target[key] = value
        applied.append(key)
    return applied


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
    auth_mode: str | None = None
    token_scope: str | None = None
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
            auth_mode=_first_env(environ, FOUNDRY_LIVE_ENV_VARS["auth_mode"]),
            token_scope=_first_env(environ, FOUNDRY_LIVE_ENV_VARS["token_scope"]),
            connection_string=_first_env(environ, FOUNDRY_LIVE_ENV_VARS["connection_string"]),
            pricing_path=_first_env(environ, FOUNDRY_LIVE_ENV_VARS["pricing_path"]),
        )

    @property
    def resolved_api_version(self) -> str:
        return self.api_version or DEFAULT_API_VERSION

    @property
    def resolved_token_scope(self) -> str:
        """AAD scope requested for Entra ID tokens (data-plane default)."""

        return self.token_scope or DEFAULT_TOKEN_SCOPE

    @property
    def router_configured(self) -> bool:
        """True when an endpoint and a router deployment are both set."""

        return bool(self.endpoint and self.deployment)

    @property
    def auth_method(self) -> str:
        """How the live client will authenticate: ``"key"``, ``"entra"`` or ``"none"``.

        ``AZURE_AI_FOUNDRY_AUTH`` forces the choice when set (``entra``/``aad`` →
        Microsoft Entra ID, ``key`` → API key). Otherwise the method is inferred:
        an API key selects key auth; a configured router with **no** key falls back
        to Entra ID (a bearer token minted from your Azure identity at call time),
        which is the only path when the resource has local/key auth disabled.
        """

        mode = (self.auth_mode or "").strip().lower()
        if mode in ENTRA_AUTH_ALIASES:
            return "entra" if self.router_configured else "none"
        if mode in KEY_AUTH_ALIASES:
            return "key" if self.api_key else "none"
        if self.api_key:
            return "key"
        if self.router_configured:
            return "entra"
        return "none"

    @property
    def credentialed(self) -> bool:
        """True when the router is configured *and* an auth method is available.

        Key auth requires an API key; Microsoft Entra ID auth requires only a
        configured router — the bearer token is fetched from your Azure identity
        (``az login`` / managed identity) when the first live call is made.
        """

        if not self.router_configured:
            return False
        method = self.auth_method
        if method == "key":
            return bool(self.api_key)
        return method == "entra"

    @property
    def observability_configured(self) -> bool:
        """True when a Foundry / Application Insights connection string is set."""

        return bool(self.connection_string)

    def missing(self) -> list[str]:
        """Return the human-readable names of the still-missing required settings.

        Under Microsoft Entra ID auth the API key is **not** required, so it is
        omitted from the gap list once the router is configured for Entra.
        """

        gaps: list[str] = []
        if not self.endpoint:
            gaps.append(FOUNDRY_LIVE_ENV_VARS["endpoint"][0])
        if not self.deployment:
            gaps.append(FOUNDRY_LIVE_ENV_VARS["deployment"][0])
        if self.auth_method != "entra" and not self.api_key:
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
            "auth_method": self.auth_method,
            "token_scope": self.resolved_token_scope if self.auth_method == "entra" else None,
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
    the default path never egresses.

    Authentication follows ``config.auth_method``: an API key when one is set,
    otherwise a Microsoft Entra ID (Azure AD) bearer token — the keyless path for
    resources with local auth disabled. Inject ``sdk_client`` to test without a
    network or an SDK, or inject ``token_provider`` to exercise the Entra branch
    without ``azure-identity`` or a real identity.
    """

    config: FoundryConfig
    sdk_client: Any = None
    token_provider: Callable[[], str] | None = None
    max_output_tokens: int = 512
    temperature: float = 0.0

    def complete(self, task: Mapping[str, Any]) -> RouterOutcome:
        if not self.config.credentialed:
            raise RuntimeError(
                "AzureModelRouterClient is not credentialed: set "
                f"{FOUNDRY_LIVE_ENV_VARS['endpoint'][0]} and "
                f"{FOUNDRY_LIVE_ENV_VARS['deployment'][0]}, then either "
                f"{FOUNDRY_LIVE_ENV_VARS['api_key'][0]} (key auth) or sign in with "
                "Microsoft Entra ID (az login / managed identity, "
                f"{FOUNDRY_LIVE_ENV_VARS['auth_mode'][0]}=entra)."
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
        common = {
            "azure_endpoint": str(self.config.endpoint),
            "api_version": self.config.resolved_api_version,
        }
        if self.config.auth_method == "entra":
            provider = self.token_provider or self._entra_token_provider()
            self.sdk_client = AzureOpenAI(azure_ad_token_provider=provider, **common)
        else:
            self.sdk_client = AzureOpenAI(api_key=str(self.config.api_key), **common)
        return self.sdk_client

    def _entra_token_provider(self) -> Callable[[], str]:
        """Build a bearer-token provider from the ambient Azure identity.

        Uses ``DefaultAzureCredential`` (``az login``, managed identity,
        environment credentials, …) scoped to ``config.resolved_token_scope``.
        Imported lazily so the default offline path never needs ``azure-identity``.
        """

        try:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "Microsoft Entra ID auth needs the azure-identity package. Install "
                "the live extra with `pip install foundry-cost-router[foundry]` "
                "(or `pip install azure-identity`), then run `az login`."
            ) from exc
        return get_bearer_token_provider(
            DefaultAzureCredential(), self.config.resolved_token_scope
        )


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
