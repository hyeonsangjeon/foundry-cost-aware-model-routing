"""Pricing-engine seam that bridges the v1 and v2 rate cards (BOLT-03B-2).

Two rate-card systems coexist in this repo and must never be conflated:

* **v1 :class:`~router.pricing.PricingTable`** — a flat per-model table with a
  ``default`` fall-back rate. It is *fail-open*: an unknown model is silently
  priced at ``default`` and there is no router markup. This is fine for the
  **offline illustrative experiments (01–08)**, whose sample cards are v1 and
  whose numbers are explicitly illustrative.

* **v2 :class:`~router.rate_card.RateCardV2`** — the authoritative composite
  card. It is *fail-closed*: an unpriced backend withholds the amount itself
  (03Z-b stance), and a Model-Router request is billed with the composite
  formula (router input-token markup + underlying input/output/cached/reasoning).
  This is the only card allowed on the **benchmark / paid measured path**.

This module lets the shared measured executor (:mod:`router.measure`) price
through *either* card via one small interface, so:

* every existing caller that passes a ``PricingTable`` keeps **byte-identical**
  snapshots, traces and summaries (the v1 engine reproduces the legacy path
  exactly and emits no extra trace columns); and
* the benchmark path — and only the benchmark path — selects the v2 engine (see
  :func:`router.run_plan.execute_benchmark`), so the five §8 surfaces (dry-run
  estimate, reservation ceiling, per-attempt trace, summary, replay) all compute
  the *identical* composite number.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import yaml

from .pricing import PricingTable
from .rate_card import RateCardV2

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .measure import MeasureCandidate

# Marker written into ``pricing.snapshot.yaml`` so credential-free replay can
# rebuild the exact engine that priced the run. v1 snapshots carry no marker, so
# their bytes are unchanged from before this seam existed.
V2_SNAPSHOT_MARKER = "rate_card_v2"


@dataclass(frozen=True)
class PricedAttempt:
    """One attempt's price, decomposed and honest about being unpriced.

    ``cost_usd`` is ``None`` — never ``0.0`` — when the attempt is *unpriced*, so
    a fail-closed backend withholds the amount itself instead of fabricating a
    zero. ``engine`` selects how the row is embedded: the v1 engine emits no
    extra columns (legacy rows stay byte-identical), the v2 engine records the
    composite breakdown so replay recomputes the identical number.
    """

    priced: bool
    cost_usd: float | None
    engine: str = "v1"
    pricing_key: str | None = None
    resolved_model: str | None = None
    router_arm: bool = False
    router_markup_usd: float = 0.0
    input_usd: float = 0.0
    output_usd: float = 0.0
    cached_usd: float = 0.0
    reasoning_usd: float = 0.0
    reason: str | None = None

    def trace_fields(self) -> dict[str, Any]:
        """Extra trace columns so replay recomputes identically.

        v1 emits nothing so legacy trace rows are byte-for-byte unchanged.
        """

        if self.engine != V2_SNAPSHOT_MARKER:
            return {}
        return {
            "pricing": {
                "engine": V2_SNAPSHOT_MARKER,
                "priced": self.priced,
                "pricing_key": self.pricing_key,
                "resolved_model": self.resolved_model,
                "router_arm": self.router_arm,
                "router_markup_usd": round(self.router_markup_usd, 6),
                "input_usd": round(self.input_usd, 6),
                "output_usd": round(self.output_usd, 6),
                "cached_usd": round(self.cached_usd, 6),
                "reasoning_usd": round(self.reasoning_usd, 6),
                "reason": self.reason,
            }
        }


@runtime_checkable
class PricingEngine(Protocol):
    """The seam the measured executor prices through (v1 or v2 behind it)."""

    version: int
    currency: str

    def price(
        self,
        candidate: MeasureCandidate,
        *,
        resolved_model: str | None,
        usage: Mapping[str, Any],
    ) -> PricedAttempt:
        """Price one *returned* attempt from its usage (and resolved model)."""

    def price_estimate(
        self, candidate: MeasureCandidate, usage: Mapping[str, Any]
    ) -> PricedAttempt:
        """Price a pre-run dry-run cell (no resolved model yet)."""

    def recompute(self, row: Mapping[str, Any]) -> PricedAttempt:
        """Re-derive a recorded row's cost for the summary/replay integrity check."""

    def snapshot_yaml(self) -> str:
        """Serialize the pinned card into ``pricing.snapshot.yaml``."""

    def cost_basis_label(self) -> str:
        """The ``labels.cost_basis`` string for the summary."""


def _row_model(row: Mapping[str, Any]) -> str:
    return str(row.get("candidate_model", ""))


class V1PricingEngine:
    """Wraps the legacy :class:`PricingTable`; reproduces its bytes exactly."""

    def __init__(self, table: PricingTable) -> None:
        self.table = table
        self.version = int(table.version)
        self.currency = str(table.currency)

    def price(
        self,
        candidate: MeasureCandidate,
        *,
        resolved_model: str | None,
        usage: Mapping[str, Any],
    ) -> PricedAttempt:
        # Legacy behaviour: price by the arm's declared model, no markup, never
        # unpriced. ``resolved_model`` is ignored so bytes match pre-seam runs.
        return PricedAttempt(
            priced=True, cost_usd=self.table.cost_usd(candidate.model, usage), engine="v1"
        )

    def price_estimate(
        self, candidate: MeasureCandidate, usage: Mapping[str, Any]
    ) -> PricedAttempt:
        return PricedAttempt(
            priced=True, cost_usd=self.table.cost_usd(candidate.model, usage), engine="v1"
        )

    def recompute(self, row: Mapping[str, Any]) -> PricedAttempt:
        tokens = row.get("tokens") or {}
        return PricedAttempt(
            priced=True, cost_usd=self.table.cost_usd(_row_model(row), tokens), engine="v1"
        )

    def snapshot_yaml(self) -> str:
        from .measure import pricing_snapshot_yaml

        return pricing_snapshot_yaml(self.table)

    def cost_basis_label(self) -> str:
        return "list-price"


class V2PricingEngine:
    """Wraps the authoritative :class:`RateCardV2` composite card (fail-closed).

    Router arms (``candidate.router``) are billed with the router input-token
    markup plus the resolved underlying model's rates; direct arms omit the
    markup. Any backend whose exact ``pricing_key`` (or a needed cached/reasoning
    rate) is not pinned yields an *unpriced* attempt that withholds the amount.
    """

    def __init__(self, card: RateCardV2) -> None:
        self.card = card
        self.version = int(card.schema_version)
        self.currency = str(card.currency)

    # -- shared core ------------------------------------------------------- #

    def _price(
        self, *, resolved_model: str | None, router_arm: bool, usage: Mapping[str, Any]
    ) -> PricedAttempt:
        key = self.card.resolve_pricing_key(resolved_model)
        breakdown = self.card.composite_cost(
            usage, pricing_key=key, include_router_markup=router_arm
        )
        if not breakdown.priced:
            return PricedAttempt(
                priced=False,
                cost_usd=None,
                engine=V2_SNAPSHOT_MARKER,
                pricing_key=key,
                resolved_model=resolved_model,
                router_arm=router_arm,
                reason=breakdown.reason,
            )
        return PricedAttempt(
            priced=True,
            cost_usd=float(breakdown.total_usd),
            engine=V2_SNAPSHOT_MARKER,
            pricing_key=key,
            resolved_model=resolved_model,
            router_arm=router_arm,
            router_markup_usd=float(breakdown.router_markup_usd),
            input_usd=float(breakdown.input_usd),
            output_usd=float(breakdown.output_usd),
            cached_usd=float(breakdown.cached_usd),
            reasoning_usd=float(breakdown.reasoning_usd),
        )

    # -- interface --------------------------------------------------------- #

    def price(
        self,
        candidate: MeasureCandidate,
        *,
        resolved_model: str | None,
        usage: Mapping[str, Any],
    ) -> PricedAttempt:
        # The provider's ``model`` (what the Router actually billed) is the
        # pricing input; fall back to the requested model only when the response
        # omitted it (a direct arm names itself).
        resolved = resolved_model or candidate.model
        return self._price(
            resolved_model=resolved, router_arm=bool(candidate.router), usage=usage
        )

    def price_estimate(
        self, candidate: MeasureCandidate, usage: Mapping[str, Any]
    ) -> PricedAttempt:
        # A router arm's pick is unknown before the run, so its dry-run cell is
        # honestly unpriced (the reservation ceiling falls back to the budget);
        # a direct arm names its own model and can be estimated.
        if candidate.router:
            return PricedAttempt(
                priced=False,
                cost_usd=None,
                engine=V2_SNAPSHOT_MARKER,
                resolved_model=None,
                router_arm=True,
                reason="router arm pick is unknown before the run (estimate is indeterminate)",
            )
        return self._price(
            resolved_model=candidate.model, router_arm=False, usage=usage
        )

    def recompute(self, row: Mapping[str, Any]) -> PricedAttempt:
        block = row.get("pricing")
        if isinstance(block, Mapping):
            resolved = block.get("resolved_model")
            router_arm = bool(block.get("router_arm", False))
        else:  # a v1-shaped row recomputed under v2 (defensive; not expected)
            resolved = _row_model(row)
            router_arm = False
        return self._price(
            resolved_model=resolved, router_arm=router_arm, usage=row.get("tokens") or {}
        )

    def snapshot_yaml(self) -> str:
        payload = {"pricing_engine": V2_SNAPSHOT_MARKER, "rate_card": self.card.to_canonical()}
        return yaml.safe_dump(payload, sort_keys=True, allow_unicode=True)

    def cost_basis_label(self) -> str:
        return "composite-rate-card-v2"


def as_engine(pricing: PricingEngine | PricingTable) -> PricingEngine:
    """Adapt a bare ``PricingTable`` to the seam; pass an engine through."""

    if isinstance(pricing, PricingTable):
        return V1PricingEngine(pricing)
    return pricing


def engine_from_snapshot(text: str) -> PricingEngine:
    """Rebuild the engine that priced a run from its ``pricing.snapshot.yaml``.

    A v2 snapshot carries the ``pricing_engine: rate_card_v2`` marker; anything
    else is a legacy v1 snapshot and rebuilds the :class:`PricingTable` exactly.
    """

    data = yaml.safe_load(text) or {}
    if isinstance(data, Mapping) and data.get("pricing_engine") == V2_SNAPSHOT_MARKER:
        return V2PricingEngine(RateCardV2.from_dict(data["rate_card"]))
    from .measure import pricing_from_snapshot_yaml

    return V1PricingEngine(pricing_from_snapshot_yaml(text))
