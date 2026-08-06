"""Canonical :class:`ResolvedRunPlan` — the single source of truth for a run.

Everything that decides *what a run costs, how good it is, and how it executes*
is resolved **once** into one immutable object here, and preview, human
approval, live dispatch, the sealed manifest, replay, and the Cockpit all read
that same object. The plan carries a deterministic ``plan_hash`` computed over
the execution-affecting fields only: change anything that moves cost/quality/
execution and the hash moves with it; change a purely presentational field
(the reserved ``display.locale``) and the hash stays put. Approval binds to that
hash, so a stale or mismatched approval is rejected *before* any wire request.

This module is pure data plus validation: it performs **no** egress and holds no
SDK object or secret. Relative paths resolve from the config file's directory,
not the caller's working directory, and a credential-key denylist keeps secrets
out of the run YAML. The live adapters live elsewhere (:mod:`router.measure`,
:mod:`router.foundry_live`); this only shapes and seals the plan they consume.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .benchmark_grader import ExecSignalsGrader
from .measure import (
    MeasureCandidate,
    MeasureRunResult,
    RetryPolicy,
    evaluate_prereg,
    load_prompt_workload,
    run_measure,
    workload_fingerprint,
)
from .pricing import PricingTable
from .pricing_engine import V2PricingEngine
from .rate_card import RateCardError, RateCardV2

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

#: The schema version this resolver understands.
SCHEMA_VERSION = 1

#: Run modes. ``smoke`` is a wiring-only one-call check; ``benchmark`` is a
#: full, preregistered, rate-card-pinned measured sweep.
RUN_MODES: tuple[str, ...] = ("smoke", "benchmark")

#: Endpoint dialects the golden path supports in v1. Only the Azure OpenAI
#: resource data-plane is wired; a Foundry *project* endpoint is not implied.
ENDPOINT_DIALECTS: tuple[str, ...] = ("azure_openai",)

#: Arm kinds. ``model_router`` is the Foundry Model Router (per-prompt choice);
#: ``direct`` names a single fixed deployment.
ARM_KINDS: tuple[str, ...] = ("model_router", "direct")

#: Presentation locales reserved here; full catalogs/behaviour arrive with i18n.
SUPPORTED_LOCALES: tuple[str, ...] = ("en", "ko")
DEFAULT_LOCALE = "en"

#: Presentation-locale environment override (behaviour deferred to i18n).
LOCALE_ENV_VAR = "COST_ROUTER_LOCALE"

#: Named smoke authorization bases (§4). Exactly one is resolved and hashed.
AUTHORIZATION_BASES: tuple[str, ...] = (
    "ceiling_only",
    "rate_card",
    "rate_card_with_ceiling",
)

#: Default data-plane API version when neither YAML nor legacy env pins one.
DEFAULT_API_VERSION = "2024-10-21"

#: Legacy environment variables folded into the plan when the YAML leaves a
#: field unset (``CLI > YAML > legacy env > default``). Mirrors
#: :data:`router.foundry_live.FOUNDRY_LIVE_ENV_VARS` without importing it, so the
#: run-plan resolver stays import-light and free of the live bridge.
LEGACY_ENV_VARS: dict[str, tuple[str, ...]] = {
    "endpoint": ("AZURE_AI_FOUNDRY_ENDPOINT", "AZURE_OPENAI_ENDPOINT"),
    "inference_endpoint": (
        "AZURE_AI_FOUNDRY_INFERENCE_ENDPOINT",
        "AZURE_AI_INFERENCE_ENDPOINT",
    ),
    "deployment": ("AZURE_AI_FOUNDRY_MODEL_ROUTER", "AZURE_MODEL_ROUTER_DEPLOYMENT"),
    "api_version": ("AZURE_AI_FOUNDRY_API_VERSION", "AZURE_OPENAI_API_VERSION"),
    "auth_mode": ("AZURE_AI_FOUNDRY_AUTH",),
}

#: Credential keys forbidden anywhere in the run YAML, compared as *normalized*
#: names (lowercase, alphanumerics only) so ``api_key``/``api-key``/``apiKey``
#: are all rejected while legitimate fields such as ``max_output_tokens`` are
#: not. This is an exact normalized-key match, never a raw substring rule.
_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "apikey",
        "accesstoken",
        "bearertoken",
        "clientsecret",
        "password",
        "connectionstring",
        "sastoken",
        "secretkey",
    }
)

_PLACEHOLDER_RE = re.compile(r"<[^>]+>")


class PlanError(ValueError):
    """A run YAML is invalid, unsafe, or not run-ready."""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


def _norm_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _canonical_json(obj: Any) -> str:
    """Stable JSON for hashing: sorted keys, tight separators, unicode kept.

    ``default=str`` coerces stray YAML scalars (e.g. a ``date`` parsed from an
    unquoted ``effective_date``) to a deterministic ISO string so the plan hash
    never depends on a non-JSON-native type slipping through.
    """

    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and bool(_PLACEHOLDER_RE.search(value))


def _iso_or_none(value: Any) -> str | None:
    """Coerce a YAML date/datetime (or any scalar) to a stable string, or None."""

    if value is None:
        return None
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return str(value)


def _has_userinfo(url: str) -> bool:
    """True if a URL embeds ``user[:pass]@host`` credentials."""

    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return bool(parts.username or parts.password)


def redact_endpoint(endpoint: str | None) -> str | None:
    """Reduce an endpoint to the minimum useful host representation.

    Strips any path, query, and (defensively) userinfo, keeping only
    ``scheme://host`` so the resolved plan can be printed without leaking a
    tenant path or an embedded credential.
    """

    if not endpoint:
        return None
    from urllib.parse import urlsplit

    parts = urlsplit(str(endpoint))
    host = parts.hostname or ""
    if not host:
        return "set"
    scheme = parts.scheme or "https"
    port = f":{parts.port}" if parts.port else ""
    return f"{scheme}://{host}{port}"


def _scan_for_secrets(node: Any, path: str = "") -> None:
    """Raise :class:`PlanError` if a credential key or URL userinfo appears."""

    if isinstance(node, Mapping):
        for key, value in node.items():
            if _norm_key(key) in _SECRET_KEYS:
                where = f"{path}.{key}" if path else str(key)
                raise PlanError(
                    f"run YAML must not contain a credential field ({where}); "
                    "sign in with Microsoft Entra ID (az login) instead"
                )
            _scan_for_secrets(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, (list, tuple)):
        for index, item in enumerate(node):
            _scan_for_secrets(item, f"{path}[{index}]")
    elif isinstance(node, str) and "://" in node and _has_userinfo(node):
        raise PlanError(
            f"run YAML endpoint at {path or 'endpoint'} embeds credentials in the "
            "URL; remove the userinfo and authenticate with Microsoft Entra ID"
        )


def _require_positive_finite(value: Any, what: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PlanError(f"{what} must be a number") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise PlanError(f"{what} must be finite")
    if number <= 0:
        raise PlanError(f"{what} must be > 0")
    return number


# --------------------------------------------------------------------------- #
# Parsed local config
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LocalRunConfig:
    """The parsed ``.foundry.local.yaml`` mapping plus its source directory.

    A thin, validated view of the raw YAML. It records where it was loaded from
    so relative artifact paths resolve against the config file's directory (not
    the caller's arbitrary working directory), and it runs the credential-key
    denylist at load time so a secret never survives parsing.
    """

    data: Mapping[str, Any]
    base_dir: Path
    source: str

    @classmethod
    def from_mapping(
        cls, data: Mapping[str, Any], *, base_dir: Path | str = ".", source: str = "mapping"
    ) -> LocalRunConfig:
        if not isinstance(data, Mapping):
            raise PlanError("run YAML must be a mapping at the top level")
        _scan_for_secrets(data)
        return cls(data=dict(data), base_dir=Path(base_dir), source=source)

    @classmethod
    def from_yaml(cls, path: Path | str) -> LocalRunConfig:
        config_path = Path(path)
        if not config_path.is_file():
            raise PlanError(f"config file not found: {config_path}")
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if loaded is None:
            raise PlanError(f"config file is empty: {config_path}")
        return cls.from_mapping(
            loaded, base_dir=config_path.resolve().parent, source=str(config_path)
        )

    @property
    def is_template(self) -> bool:
        return bool(self.data.get("template", False))

    def resolve_path(self, value: str) -> Path:
        """Resolve a config-relative path against the config file's directory."""

        candidate = Path(value)
        if candidate.is_absolute():
            return candidate
        return (self.base_dir / candidate).resolve()


# --------------------------------------------------------------------------- #
# Resolved plan
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ResolvedRunPlan:
    """An immutable, hash-sealed resolved run plan.

    ``execution`` holds every cost/quality/execution-affecting field in a
    canonical, redacted shape; :attr:`plan_hash` is its SHA-256. ``presentation``
    carries the reserved locale, which is deliberately *excluded* from the hash.
    ``sources`` records where each resolved field came from (CLI, YAML, legacy
    env, or default) without ever recording a secret.
    """

    execution: Mapping[str, Any]
    presentation: Mapping[str, Any]
    sources: Mapping[str, str]
    live_ready: bool
    template: bool
    config_source: str
    warnings: tuple[str, ...] = field(default_factory=tuple)

    # -- identity ---------------------------------------------------------

    @property
    def plan_hash(self) -> str:
        """Deterministic hash over execution-affecting fields (locale excluded)."""

        return _sha256_text(_canonical_json(self.execution))

    # -- typed accessors the callers need --------------------------------

    @property
    def run_mode(self) -> str:
        return str(self.execution["run_mode"])

    @property
    def arms(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.execution["arms"])

    @property
    def planned_cells(self) -> int:
        return int(self.execution["execution_shape"]["planned_cells"])

    @property
    def base_transport_attempts(self) -> int:
        return int(self.execution["execution_shape"]["base_transport_attempts"])

    @property
    def max_transport_attempts(self) -> int:
        return int(self.execution["execution_shape"]["max_transport_attempts"])

    @property
    def repetitions(self) -> int:
        return int(self.execution["execution_shape"]["repetitions"])

    @property
    def budget_usd(self) -> float:
        return float(self.execution["budget"]["budget_usd"])

    @property
    def authorization_basis(self) -> str:
        return str(self.execution["budget"]["authorization_basis"])

    @property
    def locale(self) -> str:
        return str(self.presentation["locale"])

    @property
    def workload_path(self) -> str:
        return str(self.execution["workload"]["path"])

    @property
    def rate_card_path(self) -> str | None:
        value = self.execution["pricing"].get("rate_card_path")
        return str(value) if value else None

    # -- serialisation ----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Full redacted plan (execution + presentation + sources + hash)."""

        return {
            "plan_hash": self.plan_hash,
            "live_ready": self.live_ready,
            "template": self.template,
            "config_source": self.config_source,
            "execution": json.loads(_canonical_json(self.execution)),
            "presentation": dict(self.presentation),
            "sources": dict(self.sources),
            "warnings": list(self.warnings),
        }

    def approval_view(self) -> dict[str, Any]:
        """The human-approval summary.

        Shows *planned cells* and the *base* and *maximum transport attempts* per
        cell. It never collapses retry-dependent outbound attempts into a single
        exact call count: a throttled cell may legitimately dispatch anywhere
        from ``base`` to ``max`` wire requests.
        """

        shape = self.execution["execution_shape"]
        return {
            "plan_hash": self.plan_hash,
            "run_mode": self.run_mode,
            "planned_cells": int(shape["planned_cells"]),
            "base_transport_attempts": int(shape["base_transport_attempts"]),
            "max_transport_attempts": int(shape["max_transport_attempts"]),
            "arms": [dict(arm) for arm in self.arms],
            "budget_usd": self.budget_usd,
            "authorization_basis": self.authorization_basis,
            "worst_case_reservation_usd": self.execution["budget"][
                "worst_case_reservation_usd"
            ],
        }

    def candidates(self) -> list[MeasureCandidate]:
        """One :class:`MeasureCandidate` per resolved arm, in plan order.

        Built from the explicit ``arms`` list, so a Model Router arm is always
        present and can never be dropped because only an ``ensemble`` fleet role
        was read.
        """

        return [
            MeasureCandidate(
                model=str(arm["requested_model"]),
                deployment=str(arm["deployment"]),
                provider=str(arm["provider"]),
                router=str(arm.get("kind")) == "model_router",
            )
            for arm in self.arms
        ]


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


def _first_env(env: Mapping[str, str], names: Sequence[str]) -> str | None:
    for name in names:
        value = env.get(name)
        if value:
            return value
    return None


def _resolve_locale(
    *,
    cli_locale: str | None,
    env: Mapping[str, str],
    yaml_locale: Any,
) -> tuple[str, str]:
    """Presentation-locale precedence (§12): CLI > env > YAML > ``en``.

    Returns ``(locale, source)``. The behaviour of the locale is deferred to
    i18n; here it is only reserved and validated, and it never enters the hash.
    """

    for value, source in (
        (cli_locale, "cli"),
        (env.get(LOCALE_ENV_VAR), "env"),
        (yaml_locale, "yaml"),
    ):
        if value:
            locale = str(value).strip().lower()
            if locale not in SUPPORTED_LOCALES:
                raise PlanError(
                    f"locale {value!r} is not supported (choose one of "
                    f"{', '.join(SUPPORTED_LOCALES)})"
                )
            return locale, source
    return DEFAULT_LOCALE, "default"


def _resolve_endpoint(
    foundry: Mapping[str, Any],
    env: Mapping[str, str],
    *,
    require_run_ready: bool,
    sources: dict[str, str],
) -> tuple[str | None, str | None, str]:
    """Resolve the data-plane endpoint (dialect fixed to Azure OpenAI in v1)."""

    dialect = str(foundry.get("endpoint_kind") or "azure_openai").strip().lower()
    if dialect not in ENDPOINT_DIALECTS:
        raise PlanError(
            f"endpoint_kind {dialect!r} is not supported in v1 "
            f"(only {', '.join(ENDPOINT_DIALECTS)})"
        )

    raw = foundry.get("azure_openai_endpoint")
    source = "yaml"
    if not raw or _is_placeholder(raw):
        env_endpoint = _first_env(env, LEGACY_ENV_VARS["endpoint"])
        if env_endpoint:
            raw, source = env_endpoint, "env"
        else:
            raw, source = None, "unset"

    if raw:
        raw = str(raw).strip()
        scheme = raw.split("://", 1)[0].lower() if "://" in raw else ""
        if scheme == "http":
            raise PlanError(
                "http:// endpoints are rejected; use https (custom/insecure hosts "
                "require an explicit development override that examples never use)"
            )
        if scheme and scheme != "https":
            raise PlanError(f"unsupported endpoint scheme {scheme!r}; use https")
        if _has_userinfo(raw):
            raise PlanError("endpoint must not embed credentials in the URL")

    if require_run_ready and not raw:
        raise PlanError(
            "run-ready config needs foundry.azure_openai_endpoint (or a legacy "
            "AZURE_AI_FOUNDRY_ENDPOINT); the template placeholder is not run-ready"
        )
    sources["endpoint"] = source
    return raw, dialect, source


def _resolve_arms(arms_raw: Any, *, require_run_ready: bool) -> list[dict[str, Any]]:
    if not isinstance(arms_raw, Sequence) or isinstance(arms_raw, (str, bytes)):
        raise PlanError("arms must be a non-empty list")
    arms: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(arms_raw):
        if not isinstance(entry, Mapping):
            raise PlanError(f"arm #{index + 1} must be a mapping")
        arm_id = str(entry.get("id") or "").strip()
        if not arm_id:
            raise PlanError(f"arm #{index + 1} needs a non-empty id")
        if arm_id in seen:
            raise PlanError(f"duplicate arm id {arm_id!r}")
        seen.add(arm_id)
        kind = str(entry.get("kind") or "").strip().lower()
        if kind not in ARM_KINDS:
            raise PlanError(
                f"arm {arm_id!r} has unknown kind {kind!r} (use one of "
                f"{', '.join(ARM_KINDS)})"
            )
        deployment = str(entry.get("deployment") or "").strip()
        requested_model = str(entry.get("requested_model") or deployment).strip()
        if not deployment:
            raise PlanError(f"arm {arm_id!r} needs a deployment")
        expected = entry.get("expected")
        if require_run_ready and _is_placeholder(deployment):
            raise PlanError(f"arm {arm_id!r} deployment is still a placeholder")
        arms.append(
            {
                "id": arm_id,
                "kind": kind,
                "provider": str(entry.get("provider") or "openai").strip().lower(),
                "requested_model": requested_model,
                "deployment": deployment,
                "expected": _normalise_expected(expected),
                "direct_model_evidence": entry.get("direct_model_evidence"),
            }
        )
    if not arms:
        raise PlanError("arms must not be empty")
    return arms


def _normalise_expected(expected: Any) -> Any:
    """Coerce an ``expected`` block to ordered (format, name, version) tuples."""

    if expected is None:
        return None
    if isinstance(expected, Mapping):
        normalised = {
            "format": expected.get("format"),
            "name": expected.get("name"),
            "version": expected.get("version"),
            "payload_hash_or_etag": expected.get("payload_hash_or_etag"),
        }
        # A router arm's approved routing mode is expected evidence: keep it so
        # it is frozen into the plan (and plan_hash) and the doctor deployment
        # probe can verify the live deployment against the approved mode.
        if "routing_mode" in expected:
            normalised["routing_mode"] = expected.get("routing_mode")
        return normalised
    return expected


def _resolve_pricing(
    benchmark: Mapping[str, Any],
    config: LocalRunConfig,
    *,
    run_mode: str,
    cli_rate_card: str | None,
    sources: dict[str, str],
) -> tuple[dict[str, Any], str]:
    """Resolve the rate card / smoke-ceiling authorization basis (§4)."""

    rate_card_ref = cli_rate_card or benchmark.get("rate_card")
    sources["rate_card"] = "cli" if cli_rate_card else "yaml"
    ceiling_raw = benchmark.get("smoke_authorization_ceiling_usd")

    rate_card: dict[str, Any] | None = None
    if rate_card_ref and not _is_placeholder(str(rate_card_ref)):
        card_path = config.resolve_path(str(rate_card_ref))
        if not card_path.is_file():
            raise PlanError(f"rate card not found: {card_path}")
        text = card_path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text) or {}
        # A v2 card is identified ONLY by an explicit ``schema_version``; a v1
        # card's ``version`` is a free revision integer (not a schema version),
        # so it must never be mistaken for one.
        raw_schema = raw.get("schema_version")
        is_v2 = raw_schema is not None and int(raw_schema) >= 2
        if is_v2:
            # Authoritative composite card (fail-closed). Validate its structure
            # via RateCardV2 — a v1 PricingTable would KeyError on the missing
            # ``default`` and there is deliberately no default rate here.
            try:
                card_v2 = RateCardV2.from_yaml(card_path)
            except RateCardError as exc:
                raise PlanError(f"invalid rate card {card_path}: {exc}") from exc
            schema_version = int(raw_schema)
            currency = str(card_v2.currency).upper()
            effective = _iso_or_none(card_v2.effective_date) or card_v2.effective_date or None
            pricing_basis = card_v2.unit_basis or raw.get("pricing_basis") or raw.get("basis")
        else:
            table = PricingTable.from_yaml(card_path)  # validates v1 structure
            schema_version = int(raw.get("version", table.version))
            currency = str(raw.get("currency", table.currency)).upper()
            effective = _iso_or_none(raw.get("effective_date") or raw.get("effective"))
            pricing_basis = raw.get("pricing_basis") or raw.get("basis")
        if currency not in ("USD",):
            raise PlanError(f"unsupported rate-card currency {currency!r}")
        rate_card = {
            "path": str(rate_card_ref),
            "schema_version": schema_version,
            "currency": currency,
            "source": raw.get("source"),
            "effective_date": effective,
            "pricing_basis": pricing_basis,
            "fingerprint": _sha256_text(text),
        }

    ceiling: float | None = None
    if ceiling_raw is not None:
        ceiling = _require_positive_finite(ceiling_raw, "smoke_authorization_ceiling_usd")

    if run_mode == "benchmark":
        if rate_card is None:
            raise PlanError("benchmark mode requires a pinned rate_card")
        if ceiling is not None:
            raise PlanError(
                "benchmark mode requires smoke_authorization_ceiling_usd: null"
            )
        basis = "rate_card"
    else:  # smoke
        if rate_card is not None and ceiling is not None:
            basis = "rate_card_with_ceiling"
        elif rate_card is not None:
            basis = "rate_card"
        elif ceiling is not None:
            basis = "ceiling_only"
        else:
            raise PlanError(
                "smoke mode needs a complete rate_card, a positive "
                "smoke_authorization_ceiling_usd, or both"
            )

    return {
        "authorization_basis": basis,
        "rate_card_path": rate_card["path"] if rate_card else None,
        "schema_version": rate_card["schema_version"] if rate_card else None,
        "currency": rate_card["currency"] if rate_card else None,
        "source": rate_card["source"] if rate_card else None,
        "effective_date": rate_card["effective_date"] if rate_card else None,
        "pricing_basis": rate_card["pricing_basis"] if rate_card else None,
        "fingerprint": rate_card["fingerprint"] if rate_card else None,
        "smoke_authorization_ceiling_usd": ceiling,
    }, basis


def _int_field(value: Any, what: str, *, minimum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise PlanError(f"{what} must be an integer") from exc
    if number < minimum:
        raise PlanError(f"{what} must be >= {minimum}")
    return number


def resolve_run_plan(
    config: LocalRunConfig,
    *,
    cli_overrides: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    cli_locale: str | None = None,
    require_run_ready: bool = False,
) -> ResolvedRunPlan:
    """Resolve one immutable :class:`ResolvedRunPlan` from a local config.

    Execution-affecting precedence is ``CLI override > run YAML > legacy env >
    safe default``; the presentation locale follows the §12 exception. This is
    pure and offline: the only I/O is reading the (local) workload and rate-card
    files referenced by the config to fingerprint them and count planned cells.
    """

    overrides = dict(cli_overrides or {})
    environ = env if env is not None else os.environ
    data = config.data
    sources: dict[str, str] = {}
    warnings: list[str] = []

    schema_version = _int_field(
        data.get("schema_version", SCHEMA_VERSION), "schema_version", minimum=1
    )
    if schema_version != SCHEMA_VERSION:
        raise PlanError(
            f"unsupported schema_version {schema_version} (this build resolves "
            f"schema_version {SCHEMA_VERSION})"
        )

    template = bool(data.get("template", False))
    if require_run_ready and template:
        raise PlanError(
            "config is still a template (template: true); run `config init`, fill "
            "it in, and set template: false before a live run"
        )

    run_mode = str(overrides.get("run_mode") or data.get("run_mode") or "smoke").strip().lower()
    sources["run_mode"] = "cli" if overrides.get("run_mode") else "yaml"
    if run_mode not in RUN_MODES:
        raise PlanError(f"run_mode {run_mode!r} must be one of {', '.join(RUN_MODES)}")

    foundry = data.get("foundry") or {}
    if not isinstance(foundry, Mapping):
        raise PlanError("foundry section must be a mapping")
    endpoint, dialect, _ = _resolve_endpoint(
        foundry, environ, require_run_ready=require_run_ready, sources=sources
    )

    auth_mode = (
        str(foundry.get("auth") or _first_env(environ, LEGACY_ENV_VARS["auth_mode"]) or "entra")
        .strip()
        .lower()
    )
    sources["auth"] = "yaml" if foundry.get("auth") else (
        "env" if _first_env(environ, LEGACY_ENV_VARS["auth_mode"]) else "default"
    )
    api_version = str(
        foundry.get("api_version")
        or _first_env(environ, LEGACY_ENV_VARS["api_version"])
        or DEFAULT_API_VERSION
    ).strip()
    sources["api_version"] = "yaml" if foundry.get("api_version") else (
        "env" if _first_env(environ, LEGACY_ENV_VARS["api_version"]) else "default"
    )

    evidence_raw = foundry.get("deployment_evidence") or {}
    deployment_evidence = {
        "management_resource_id": evidence_raw.get("management_resource_id"),
        "exported_arm_payload": evidence_raw.get("exported_arm_payload"),
        "management_api_version": evidence_raw.get("management_api_version"),
        "captured_at": evidence_raw.get("captured_at"),
        "payload_hash_or_etag": evidence_raw.get("payload_hash_or_etag"),
    }

    arms = _resolve_arms(data.get("arms"), require_run_ready=require_run_ready)
    if require_run_ready and run_mode == "benchmark":
        for arm in arms:
            if arm["kind"] == "model_router" and not arm["expected"]:
                raise PlanError(
                    f"benchmark arm {arm['id']!r} (model_router) needs fixed "
                    "expected mode/version/subset evidence"
                )

    benchmark = data.get("benchmark") or {}
    if not isinstance(benchmark, Mapping):
        raise PlanError("benchmark section must be a mapping")

    workload_ref = overrides.get("workload") or benchmark.get("workload")
    sources["workload"] = "cli" if overrides.get("workload") else "yaml"
    if not workload_ref:
        raise PlanError("benchmark.workload is required")
    workload_path = config.resolve_path(str(workload_ref))
    if not workload_path.is_file():
        raise PlanError(f"workload not found: {workload_path}")
    workload = load_prompt_workload(workload_path)
    if not workload:
        raise PlanError(f"workload has no prompt-bearing tasks: {workload_path}")
    workload_fp = workload_fingerprint(workload)

    pricing, _basis = _resolve_pricing(
        benchmark, config, run_mode=run_mode,
        cli_rate_card=overrides.get("rate_card"), sources=sources,
    )

    repetitions = _int_field(
        overrides.get("repetitions", benchmark.get("repetitions", 1)),
        "repetitions", minimum=1,
    )
    sources["repetitions"] = "cli" if "repetitions" in overrides else "yaml"

    retry_raw = benchmark.get("retry") or {}
    max_retries = _int_field(retry_raw.get("max_retries", 0), "retry.max_retries", minimum=0)
    retry = {
        "max_retries": max_retries,
        "provider_internal_retries_disabled": True,
        "connect_timeout_seconds": retry_raw.get("connect_timeout_seconds", 10),
        "read_timeout_seconds": retry_raw.get("read_timeout_seconds", 90),
        "write_timeout_seconds": retry_raw.get("write_timeout_seconds", 30),
        "pool_timeout_seconds": retry_raw.get("pool_timeout_seconds", 10),
        "overall_timeout_seconds": retry_raw.get("overall_timeout_seconds", 120),
    }

    base_attempts = 1
    max_attempts = 1 + max_retries
    planned_cells = len(workload) * repetitions * len(arms)
    execution_shape = {
        "repetitions": repetitions,
        "planned_cells": planned_cells,
        "base_transport_attempts": base_attempts,
        "max_transport_attempts": max_attempts,
    }

    max_output_tokens = _int_field(
        overrides.get("max_output_tokens", benchmark.get("max_output_tokens", 256)),
        "max_output_tokens", minimum=1,
    )
    sources["max_output_tokens"] = "cli" if "max_output_tokens" in overrides else "yaml"

    budget_usd = _require_positive_finite(
        overrides.get("budget_usd", benchmark.get("budget_usd", 0.0) or 0.0),
        "budget_usd",
    )
    sources["budget"] = "cli" if "budget_usd" in overrides else "yaml"

    ceiling = pricing["smoke_authorization_ceiling_usd"]
    if ceiling is not None and ceiling > budget_usd:
        raise PlanError(
            "smoke_authorization_ceiling_usd must be <= budget_usd "
            f"({ceiling} > {budget_usd})"
        )
    if pricing["authorization_basis"] == "ceiling_only":
        worst_case = ceiling
        reservation_basis = "whole ceiling reserved before dispatch"
    else:
        worst_case = budget_usd
        reservation_basis = "rate-derived reservation bounded by budget_usd"
    budget = {
        "budget_usd": budget_usd,
        "authorization_basis": pricing["authorization_basis"],
        "smoke_ceiling_usd": ceiling,
        "worst_case_reservation_usd": worst_case,
        "reservation_basis": reservation_basis,
    }

    grader_raw = benchmark.get("grader") or {}
    grader = {
        "kind": str(grader_raw.get("kind") or "exec-signals"),
        "version": grader_raw.get("version", 1),
        "fingerprint": grader_raw.get("fingerprint"),
    }

    estimand_raw = benchmark.get("estimand")
    estimand = dict(estimand_raw) if isinstance(estimand_raw, Mapping) else None
    if run_mode == "benchmark" and require_run_ready and not estimand:
        raise PlanError("benchmark mode requires an estimand block")

    privacy_raw = data.get("privacy") or {}
    privacy = {
        "retain_raw_prompts": bool(privacy_raw.get("retain_raw_prompts", False)),
        "retain_raw_outputs": bool(privacy_raw.get("retain_raw_outputs", False)),
        "retain_raw_response_ids": bool(privacy_raw.get("retain_raw_response_ids", False)),
    }
    artifacts_raw = data.get("artifacts") or {}
    artifacts = {
        "local_root": str(artifacts_raw.get("local_root") or "results/local"),
        "publish_sanitized": bool(artifacts_raw.get("publish_sanitized", False)),
    }

    prereg_raw = benchmark.get("preregistration")
    preregistration = None
    if prereg_raw:
        preregistration = {
            "path": prereg_raw if isinstance(prereg_raw, str) else prereg_raw.get("path"),
            "blob": prereg_raw.get("blob") if isinstance(prereg_raw, Mapping) else None,
            "commit": prereg_raw.get("commit") if isinstance(prereg_raw, Mapping) else None,
        }

    display_raw = data.get("display") or {}
    locale, locale_source = _resolve_locale(
        cli_locale=cli_locale, env=environ, yaml_locale=display_raw.get("locale")
    )

    execution: dict[str, Any] = {
        "schema_version": schema_version,
        "run_mode": run_mode,
        "endpoint": {
            "dialect": dialect,
            "data_plane": redact_endpoint(endpoint),
            "inference": redact_endpoint(foundry.get("model_inference_endpoint")),
            "auth_mode": auth_mode,
            "api_version": api_version,
        },
        "deployment_evidence": deployment_evidence,
        "arms": arms,
        "workload": {"path": str(workload_ref), "fingerprint": workload_fp},
        "pricing": pricing,
        "execution_shape": execution_shape,
        "request": {"max_output_tokens": max_output_tokens},
        "retry": retry,
        "budget": budget,
        "grader": grader,
        "estimand": estimand,
        "preregistration": preregistration,
        "privacy": privacy,
        "artifacts": artifacts,
        "seed": {
            "random_seed": _int_field(
                benchmark.get("random_seed", 0), "random_seed", minimum=0
            ),
            "order_policy": "task-major, then repeat, then arm; deterministic",
        },
    }

    presentation = {"locale": locale, "locale_source": locale_source}
    sources["locale"] = locale_source

    # Template configs are never live-ready even when otherwise well-formed.
    live_ready = (not template) and endpoint is not None
    if template and not require_run_ready:
        warnings.append(
            "template config: live_ready=false — fill in .foundry.local.yaml and "
            "set template: false to run"
        )

    return ResolvedRunPlan(
        execution=execution,
        presentation=presentation,
        sources=sources,
        live_ready=live_ready,
        template=template,
        config_source=config.source,
        warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------- #
# Approval + config-init helpers
# --------------------------------------------------------------------------- #


class ApprovalError(PlanError):
    """A supplied ``--approve-plan`` hash does not match the resolved plan."""


def check_approval(plan: ResolvedRunPlan, approved_hash: str | None) -> None:
    """Raise :class:`ApprovalError` unless ``approved_hash`` matches the plan.

    A stale or mismatched approval is rejected here, *before* any dispatch: the
    caller resolves the plan fresh, then this binds the human's approval to the
    exact ``plan_hash`` they reviewed.
    """

    if not approved_hash:
        raise ApprovalError(
            "a live run requires --approve-plan <plan_hash>; resolve it first with "
            "`benchmark plan`"
        )
    supplied = approved_hash.strip()
    expected = plan.plan_hash
    # Accept the bare hex or the sha256: prefixed form the plan prints.
    normalized = supplied if supplied.startswith("sha256:") else f"sha256:{supplied}"
    if normalized != expected:
        raise ApprovalError(
            "approval rejected: --approve-plan does not match the current plan_hash "
            f"(approved {supplied}, resolved {expected}); re-review `benchmark plan`"
        )


TEMPLATE_FILENAME = "foundry.example.yaml"
DEFAULT_LOCAL_CONFIG = ".foundry.local.yaml"


def _find_template(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / TEMPLATE_FILENAME
        if candidate.is_file():
            return candidate
    raise PlanError(f"{TEMPLATE_FILENAME} not found (run from the repository root)")


def write_local_config(
    output: Path | str = DEFAULT_LOCAL_CONFIG,
    *,
    force: bool = False,
    template_path: Path | str | None = None,
) -> Path:
    """Write a local config from the committed placeholder template.

    Copies ``foundry.example.yaml`` verbatim (placeholders intact, no secret
    field) so ``config init`` produces a valid, run-ready-after-editing local
    file. Refuses to clobber an existing file unless ``force`` is set.
    """

    out = Path(output)
    if out.exists() and not force:
        raise PlanError(f"{out} already exists (pass --force to overwrite)")
    source = Path(template_path) if template_path else _find_template()
    text = source.read_text(encoding="utf-8")
    # Guard: the committed template must never carry a credential field.
    _scan_for_secrets(yaml.safe_load(text) or {})
    if out.parent and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out


# --------------------------------------------------------------------------- #
# Execution seam — the plan is the single input the runner consumes
# --------------------------------------------------------------------------- #


def execute_benchmark(
    config: LocalRunConfig,
    plan: ResolvedRunPlan,
    *,
    client: Any,
    run_dir: Path | str,
    exp_id: str = "benchmark",
    grader: Any = None,
    prereg: Any = None,
    git_commit: str | None = None,
    region: str | None = None,
    now: Any = None,
    sleeper: Any = None,
    clock: Any = None,
    resume: bool = False,
) -> MeasureRunResult:
    """Run the plan through the measured sweep, sealing ``plan_hash`` into the manifest.

    The candidates come straight from :meth:`ResolvedRunPlan.candidates` (so a
    Model Router arm is always dispatched, never dropped), the sweep shape and
    budget come from the plan, and the sealed manifest carries the identical
    ``plan_hash`` the operator approved — the same value preview, approval, and
    replay all read. The ``client`` is an injected seam, so tests drive this with
    a scripted fake and CI never egresses.
    """

    workload = load_prompt_workload(config.resolve_path(plan.workload_path))
    if not workload:
        raise PlanError(f"workload has no prompt-bearing tasks: {plan.workload_path}")
    card = plan.rate_card_path
    if not card:
        raise PlanError(
            "execute_benchmark needs a pinned rate card to price usage; a "
            "ceiling-only smoke reserves spend but derives no cost (see 03B)"
        )
    card_path = config.resolve_path(card)
    # The benchmark / paid path prices through the authoritative v2 composite
    # card (fail-closed, router markup); a legacy v1 card still works for older
    # fixtures. Detect the format exactly as ``_resolve_pricing`` did: only an
    # explicit ``schema_version`` marks a v2 card.
    raw_card = yaml.safe_load(card_path.read_text(encoding="utf-8")) or {}
    raw_schema = raw_card.get("schema_version")
    if raw_schema is not None and int(raw_schema) >= 2:
        pricing: Any = V2PricingEngine(RateCardV2.from_yaml(card_path))
    else:
        pricing = PricingTable.from_yaml(card_path)
    retry = RetryPolicy(max_retries=int(plan.execution["retry"]["max_retries"]))

    # Auto-wire the exec-signals grading bridge for a benchmark sweep so the
    # (paid) run captures each arm's code and grades it in memory (spec §10).
    # Tests still inject a fake grader; a smoke run stays ungraded. The grader
    # no-ops on cells with no captured content, so this never egresses here.
    if grader is None and plan.run_mode == "benchmark":
        grader_kind = str((plan.execution.get("grader") or {}).get("kind") or "")
        if grader_kind == "exec-signals":
            benchmark_root = config.resolve_path(plan.workload_path).parent
            if (benchmark_root / "harness" / "grade.py").is_file():
                grader = ExecSignalsGrader(benchmark_root)

    # Record the prereg the plan pins (its {path, blob, commit} are already bound
    # into plan_hash) into the sealed manifest, unless a decision was injected.
    if prereg is None:
        prereg_block = plan.execution.get("preregistration") or {}
        prereg_ref = prereg_block.get("path")
        if prereg_ref:
            prereg = evaluate_prereg(
                config.resolve_path(prereg_ref),
                run_started_at=(
                    now
                    if isinstance(now, datetime.datetime)
                    else datetime.datetime.now(datetime.UTC)
                ),
            )

    extra: dict[str, Any] = {}
    if sleeper is not None:
        extra["sleeper"] = sleeper
    if clock is not None:
        extra["clock"] = clock
    if now is not None:
        extra["now"] = now

    return run_measure(
        workload,
        plan.candidates(),
        client=client,
        pricing=pricing,
        exp_id=exp_id,
        run_dir=run_dir,
        n=plan.repetitions,
        budget_usd=plan.budget_usd,
        retry=retry,
        grader=grader,
        prereg=prereg,
        git_commit=git_commit,
        endpoint=plan.execution["endpoint"]["data_plane"],
        region=region,
        pricing_path=card,
        plan_hash=plan.plan_hash,
        resume=resume,
        **extra,
    )
