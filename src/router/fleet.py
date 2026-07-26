"""Fleet registry — register your deployed models, pick which plays each arm.

Everything measured in this repo runs through the live arena
(:mod:`router.foundry_arena`), and the arena needs to know *which real Azure AI
Foundry deployment* backs each strategy arm: the single **router** (main) model,
the **cheapest** floor, the **premium** ceiling, and the **ensemble** fan-out
slate. Until now that mapping lived hard-coded in
:class:`~router.foundry_arena.FleetSlate`.

This module promotes it to a small, declarative **config file** an operator
owns — the "환경파일에 사용할 모델 등록" step:

* a **catalog** of the models you actually have deployed (a logical ``name``
  used for pricing/display, the Azure ``deployment`` name, and a ``tier``), and
* a **role assignment** (the *slate*) saying which catalog model fills each arm.

Load it from YAML (or ``FOUNDRY_FLEET_PATH``), edit it from the terminal
(``cost-router models select``) or the dashboard, then hand the resulting
:class:`~router.foundry_arena.FleetSlate` to the live arena for real,
*measured* processing. Nothing here egresses or holds a secret — it is pure
data plus validation, so it stays import-light and deterministic.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .foundry_arena import FleetSlate

# The four arms a slate must fill. ``ensemble`` is a list of models (the fan-out
# slate); the others each name one model.
SINGLE_ROLES: tuple[str, ...] = ("router", "cheapest", "premium")
ROLES: tuple[str, ...] = (*SINGLE_ROLES, "ensemble")

# Human labels for the role menu (terminal + dashboard).
ROLE_LABELS: dict[str, str] = {
    "router": "router (main)",
    "cheapest": "cheapest",
    "premium": "premium",
    "ensemble": "ensemble / fan-out",
}

# Environment variables that point at a fleet config file (first present wins).
FLEET_ENV_VARS: tuple[str, ...] = ("FOUNDRY_FLEET_PATH", "COST_ROUTER_FLEET")

# How the live client reaches a model. ``openai`` = the Azure OpenAI
# chat-completions surface (``*.openai.azure.com`` — OpenAI-format deployments:
# gpt-5.x, the Model Router). ``foundry`` = the Azure AI Model Inference surface
# (``*.services.ai.azure.com/models`` — partner/OSS deployments: DeepSeek,
# Mistral, xAI, Cohere, Llama, Phi, …) on the SAME Foundry resource.
PROVIDERS: tuple[str, ...] = ("openai", "foundry")
_PROVIDER_ALIASES: dict[str, str] = {
    "": "openai",
    "openai": "openai",
    "azure": "openai",
    "aoai": "openai",
    "azure-openai": "openai",
    "azureopenai": "openai",
    "foundry": "foundry",
    "inference": "foundry",
    "ai-inference": "foundry",
    "model-inference": "foundry",
    "maas": "foundry",
}


def normalize_provider(value: Any) -> str:
    """Fold a free-form provider label to one of :data:`PROVIDERS` (else as-is)."""

    key = str(value or "").strip().lower()
    return _PROVIDER_ALIASES.get(key, key)

# Bundled sample fleet, repo-relative (matches DEFAULT_FLEET_PRICING convention).
BUNDLED_FLEET_PATH = Path("samples/fleet/foundry-5series.fleet.yaml")

# Where `models select` persists a chosen slate by default. Gitignored
# (`*.local.yaml`) so a tenant's real deployment names never get committed.
LOCAL_FLEET_PATH = Path(".foundry-fleet.local.yaml")


@dataclass(frozen=True)
class FleetModel:
    """One registered model: a pricing/display name and its Azure deployment.

    ``name`` is the logical key looked up in the pricing table and shown in
    reports (e.g. ``gpt-5.4``); ``deployment`` is the Azure AI Foundry deployment
    name the live client calls (often identical, but decoupled on purpose so one
    logical model can point at a differently-named deployment). ``tier`` is a
    free-form ordering/label hint (``small``/``mid``/``frontier``/``router``).
    ``provider`` selects the call surface on the resource: ``openai`` (the
    Azure OpenAI chat-completions route) or ``foundry`` (the Azure AI Model
    Inference route used by partner/OSS models like DeepSeek or Cohere).
    """

    name: str
    deployment: str
    tier: str = ""
    label: str = ""
    provider: str = "openai"

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"name": self.name, "deployment": self.deployment}
        if self.tier:
            data["tier"] = self.tier
        if self.provider and self.provider != "openai":
            data["provider"] = self.provider
        if self.label:
            data["label"] = self.label
        return data

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> FleetModel:
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("fleet model needs a non-empty 'name'")
        deployment = str(data.get("deployment") or name).strip()
        return cls(
            name=name,
            deployment=deployment,
            tier=str(data.get("tier") or "").strip(),
            label=str(data.get("label") or "").strip(),
            provider=normalize_provider(data.get("provider")),
        )


@dataclass(frozen=True)
class FleetRegistry:
    """A catalog of deployed models plus the role slate that picks each arm.

    Immutable: :meth:`with_roles` returns a new registry with changed
    assignments, so the CLI/dashboard selection flows never mutate shared state.
    """

    models: tuple[FleetModel, ...]
    router: str
    cheapest: str
    premium: str
    ensemble: tuple[str, ...]
    source: str = "bundled default"

    # -- lookups ----------------------------------------------------------

    def model_names(self) -> tuple[str, ...]:
        return tuple(m.name for m in self.models)

    def get(self, name: str) -> FleetModel:
        for model in self.models:
            if model.name == name:
                return model
        raise KeyError(f"model {name!r} is not in the fleet catalog")

    def deployment_for(self, name: str) -> str:
        return self.get(name).deployment

    def provider_for(self, name: str) -> str:
        return self.get(name).provider

    def role_assignments(self) -> dict[str, Any]:
        """Role -> assigned model name(s), for display and serialization."""

        return {
            "router": self.router,
            "cheapest": self.cheapest,
            "premium": self.premium,
            "ensemble": list(self.ensemble),
        }

    def roles_for(self, name: str) -> list[str]:
        """Which role(s) a catalog model currently fills (for the menu)."""

        roles: list[str] = []
        for role in SINGLE_ROLES:
            if getattr(self, role) == name:
                roles.append(ROLE_LABELS[role])
        if name in self.ensemble:
            roles.append(ROLE_LABELS["ensemble"])
        return roles

    # -- validation -------------------------------------------------------

    def validation_errors(self) -> list[str]:
        """Return human-readable problems; an empty list means the slate is valid."""

        errors: list[str] = []
        if not self.models:
            errors.append("catalog is empty — register at least one model")
        names = self.model_names()
        if len(set(names)) != len(names):
            errors.append("duplicate model names in the catalog")
        for model in self.models:
            if model.provider not in PROVIDERS:
                errors.append(
                    f"model {model.name!r} has unknown provider {model.provider!r} "
                    f"(use one of: {', '.join(PROVIDERS)})"
                )
        for role in SINGLE_ROLES:
            assigned = getattr(self, role)
            if not assigned:
                errors.append(f"role {role!r} is unassigned")
            elif assigned not in names:
                errors.append(f"role {role!r} -> {assigned!r} is not in the catalog")
        if not self.ensemble:
            errors.append("ensemble slate is empty — assign at least one model")
        for member in self.ensemble:
            if member not in names:
                errors.append(f"ensemble member {member!r} is not in the catalog")
        return errors

    def validate(self) -> FleetRegistry:
        """Return self if valid, else raise :class:`ValueError` listing every gap."""

        errors = self.validation_errors()
        if errors:
            raise ValueError("invalid fleet: " + "; ".join(errors))
        return self

    # -- the slate the live arena consumes --------------------------------

    def slate(self) -> FleetSlate:
        """Build the deployment-keyed :class:`FleetSlate` the live arena calls."""

        self.validate()
        providers: dict[str, str] = {}
        for name in (self.router, self.cheapest, self.premium, *self.ensemble):
            model = self.get(name)
            providers[model.deployment] = model.provider
        return FleetSlate(
            router=self.deployment_for(self.router),
            cheapest=self.deployment_for(self.cheapest),
            premium=self.deployment_for(self.premium),
            ensemble=tuple(self.deployment_for(name) for name in self.ensemble),
            providers=providers,
        )

    # -- selection --------------------------------------------------------

    def with_roles(
        self,
        *,
        router: str | None = None,
        cheapest: str | None = None,
        premium: str | None = None,
        ensemble: Sequence[str] | None = None,
        source: str | None = None,
    ) -> FleetRegistry:
        """Return a copy with the given role assignments replaced (then validated)."""

        return FleetRegistry(
            models=self.models,
            router=router if router is not None else self.router,
            cheapest=cheapest if cheapest is not None else self.cheapest,
            premium=premium if premium is not None else self.premium,
            ensemble=tuple(ensemble) if ensemble is not None else self.ensemble,
            source=source if source is not None else self.source,
        ).validate()

    # -- serialization ----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "models": [m.to_dict() for m in self.models],
            "roles": self.role_assignments(),
        }

    def to_yaml(self) -> str:
        import yaml

        return yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True)

    def catalog_view(self) -> list[dict[str, Any]]:
        """Catalog rows annotated with the roles each model fills (for UIs).

        ``provider`` is always present here (unlike :meth:`FleetModel.to_dict`,
        which omits the default) so dashboards can render the call surface for
        every row without inferring the default.
        """

        return [
            {**m.to_dict(), "provider": m.provider, "roles": self.roles_for(m.name)}
            for m in self.models
        ]

    # -- construction -----------------------------------------------------

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, source: str = "mapping") -> FleetRegistry:
        raw_models = data.get("models") or []
        models = tuple(_coerce_models(raw_models))
        roles = dict(data.get("roles") or {})
        ensemble = roles.get("ensemble") or []
        if isinstance(ensemble, str):
            ensemble = [part.strip() for part in ensemble.split(",") if part.strip()]
        return cls(
            models=models,
            router=str(roles.get("router") or "").strip(),
            cheapest=str(roles.get("cheapest") or "").strip(),
            premium=str(roles.get("premium") or "").strip(),
            ensemble=tuple(str(m).strip() for m in ensemble if str(m).strip()),
            source=source,
        )

    @classmethod
    def from_yaml(cls, path: Path | str) -> FleetRegistry:
        import yaml

        text = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        if not isinstance(data, Mapping):
            raise ValueError(f"fleet config {path} must be a mapping at the top level")
        return cls.from_mapping(data, source=str(path))

    @classmethod
    def default(cls) -> FleetRegistry:
        """The in-code default fleet (matches the pre-config hard-coded slate).

        Kept authoritative in code so the registry works even when the bundled
        sample file is absent (e.g. an installed wheel). The sample YAML mirrors
        this exactly for editing.
        """

        models = (
            FleetModel("gpt-5.4-nano", "gpt-5.4-nano", "small", "GPT-5.4 nano — cheap floor"),
            FleetModel("gpt-5.4-mini", "gpt-5.4-mini", "mid", "GPT-5.4 mini — mid tier"),
            FleetModel("gpt-5.4", "gpt-5.4", "frontier", "GPT-5.4 — frontier ceiling"),
            FleetModel(
                "model-router",
                "model-router",
                "router",
                "Foundry Model Router — picks one model per prompt",
            ),
        )
        return cls(
            models=models,
            router="model-router",
            cheapest="gpt-5.4-nano",
            premium="gpt-5.4",
            ensemble=("gpt-5.4-nano", "gpt-5.4-mini", "gpt-5.4"),
            source="bundled default",
        )

    @classmethod
    def resolve(
        cls,
        path: Path | str | None = None,
        *,
        env: Mapping[str, str] | None = None,
    ) -> FleetRegistry:
        """Load a fleet: explicit ``path`` > ``FOUNDRY_FLEET_PATH`` > bundled file > default.

        Missing files are not an error unless an explicit ``path`` was given —
        the in-code :meth:`default` is the always-available fallback, so the
        offline/deterministic default is never disturbed.
        """

        if path is not None:
            return cls.from_yaml(path)
        environ = env if env is not None else os.environ
        for var in FLEET_ENV_VARS:
            value = environ.get(var)
            if value:
                return cls.from_yaml(value)
        if BUNDLED_FLEET_PATH.is_file():
            return cls.from_yaml(BUNDLED_FLEET_PATH)
        return cls.default()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _coerce_models(raw: Any) -> Iterable[FleetModel]:
    """Accept a list of ``{name, deployment, ...}`` or a ``name: deployment`` map."""

    if isinstance(raw, Mapping):
        for name, deployment in raw.items():
            if isinstance(deployment, Mapping):
                yield FleetModel.from_mapping({"name": name, **deployment})
            else:
                yield FleetModel(name=str(name), deployment=str(deployment or name))
        return
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for entry in raw:
            if isinstance(entry, Mapping):
                yield FleetModel.from_mapping(entry)
            elif isinstance(entry, str):
                yield FleetModel(name=entry, deployment=entry)
        return
    raise ValueError(
        "fleet 'models' must be a list of {name, deployment} or a name->deployment map"
    )


def save_fleet(registry: FleetRegistry, path: Path | str = LOCAL_FLEET_PATH) -> Path:
    """Write a registry's catalog + selected slate to ``path`` as YAML."""

    out = Path(path)
    if out.parent and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# cost-router fleet — which deployed model plays each arm.\n"
        "# Edit here or with `cost-router models select`. Point live runs at it\n"
        "# with `--fleet` or FOUNDRY_FLEET_PATH. 'deployment' is the Azure name.\n"
    )
    out.write_text(header + registry.validate().to_yaml(), encoding="utf-8")
    return out
