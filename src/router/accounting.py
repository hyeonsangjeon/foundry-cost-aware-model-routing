"""Per-attempt accounting record with separated concerns (BOLT-03B, step 2).

Every dispatched attempt — success, retry, or failure — becomes one
:class:`AttemptAccounting` row that keeps *distinct concepts distinct* so an
honest cost/quality label can be derived later without conflation:

* ``resolved_model_raw`` is the provider's unmodified ``model`` value; the
  ``pricing_key`` is produced only by the versioned exact alias map. A hashed
  response id is diagnostic and is NEVER a resolved-model source or a pricing
  input.
* ``transport_state`` and ``billability_state`` are tracked independently, so a
  timeout/unknown attempt keeps its reservation as unreconciled exposure and
  sets ``cost_complete=false`` instead of being dropped or silently priced.
* Known rate-card-derived cost, unreconciled reserved exposure, and the
  authorized upper bound are stored separately; the sum is never labelled "total
  paid cost" before reconciliation.
* The many status booleans (``configured`` … ``savings_claim_allowed``) are
  independent fields, not one collapsed flag.

This generalizes the 03Z-b fail-closed stance: an unpriced/unknown attempt
withholds the *amount itself* (``known_rate_card_derived_cost_usd=None``), not
just a savings claim.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .foundry_live import FOUNDRY_PROVIDER_ALIASES
from .rate_card import CostBreakdown, RateCardV2

_ZERO = Decimal(0)

# transport_state
RESERVED = "reserved"
IN_FLIGHT = "in_flight"
RETURNED = "returned"
CANCELLED = "cancelled"
UNKNOWN = "unknown"
TRANSPORT_STATES = frozenset({RESERVED, IN_FLIGHT, RETURNED, CANCELLED, UNKNOWN})

# billability_state
KNOWN_BILLED = "known_billed"
KNOWN_NOT_BILLED = "known_not_billed"
BILLABILITY_UNKNOWN = "unknown"
BILLABILITY_STATES = frozenset({KNOWN_BILLED, KNOWN_NOT_BILLED, BILLABILITY_UNKNOWN})

# resolved_model_source
PROVIDER_REPORTED = "provider_reported"
UNAVAILABLE = "unavailable"


def hash_secret(text: str | None) -> str | None:
    """SHA-256 hex of a raw string (response id / output), or ``None``.

    Used for ``response_id_hash`` and ``output_hash`` so the raw value never
    leaves the local process while integrity/diagnostics remain verifiable.
    """

    if text is None:
        return None
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AttemptAccounting:
    """One dispatched attempt's fully separated accounting concepts."""

    arm: str
    requested_model: str
    deployment: str
    provider: str
    resolved_model_raw: str | None
    resolved_model_source: str
    pricing_key: str | None
    response_id_hash: str | None
    output_hash: str | None
    usage: dict[str, float]
    transport_state: str
    billability_state: str

    # pricing components (Decimal; None where unpriced)
    rate_card_hash: str | None
    router_input_markup_usd: Decimal | None
    underlying_input_usd: Decimal | None
    underlying_output_usd: Decimal | None
    cached_usd: Decimal | None
    reasoning_usd: Decimal | None
    known_rate_card_derived_cost_usd: Decimal | None
    unreconciled_reserved_exposure_usd: Decimal
    authorized_upper_bound_usd: Decimal
    cost_complete: bool

    # grading
    grader_rule: str | None
    grader_version: str | None
    grader_hash: str | None
    passed: bool | None

    # independent status fields
    configured: bool
    token_acquired: bool
    data_plane_rbac_verified: bool | None
    deployment_config_verified: bool | None
    usage_measured: bool
    cost_derived: bool
    pricing_complete: bool
    quality_graded: bool
    wiring_only: bool
    benchmark_eligible: bool
    publishable: bool
    savings_claim_allowed: bool

    unpriced_reason: str | None = None
    reconciliation_required: bool = False
    notes: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """A JSON-ready record; Decimal money serialized as strings (full precision)."""

        def money(value: Decimal | None) -> str | None:
            return None if value is None else str(value)

        return {
            "arm": self.arm,
            "requested_model": self.requested_model,
            "deployment": self.deployment,
            "provider": self.provider,
            "resolved_model_raw": self.resolved_model_raw,
            "resolved_model_source": self.resolved_model_source,
            "pricing_key": self.pricing_key,
            "response_id_hash": self.response_id_hash,
            "output_hash": self.output_hash,
            "usage": dict(self.usage),
            "transport_state": self.transport_state,
            "billability_state": self.billability_state,
            "rate_card_hash": self.rate_card_hash,
            "pricing_components": {
                "router_input_markup_usd": money(self.router_input_markup_usd),
                "underlying_input_usd": money(self.underlying_input_usd),
                "underlying_output_usd": money(self.underlying_output_usd),
                "cached_usd": money(self.cached_usd),
                "reasoning_usd": money(self.reasoning_usd),
            },
            "known_rate_card_derived_cost_usd": money(self.known_rate_card_derived_cost_usd),
            "unreconciled_reserved_exposure_usd": money(
                self.unreconciled_reserved_exposure_usd
            ),
            "authorized_upper_bound_usd": money(self.authorized_upper_bound_usd),
            "cost_complete": self.cost_complete,
            "grader": {
                "rule": self.grader_rule,
                "version": self.grader_version,
                "hash": self.grader_hash,
                "passed": self.passed,
            },
            "status": {
                "configured": self.configured,
                "token_acquired": self.token_acquired,
                "data_plane_rbac_verified": self.data_plane_rbac_verified,
                "deployment_config_verified": self.deployment_config_verified,
                "usage_measured": self.usage_measured,
                "cost_derived": self.cost_derived,
                "pricing_complete": self.pricing_complete,
                "cost_complete": self.cost_complete,
                "quality_graded": self.quality_graded,
                "wiring_only": self.wiring_only,
                "benchmark_eligible": self.benchmark_eligible,
                "publishable": self.publishable,
                "savings_claim_allowed": self.savings_claim_allowed,
            },
            "unpriced_reason": self.unpriced_reason,
            "reconciliation_required": self.reconciliation_required,
        }


def build_attempt_accounting(
    *,
    arm: str,
    requested_model: str,
    deployment: str,
    provider: str,
    is_router_arm: bool,
    rate_card: RateCardV2,
    reservation: CostBreakdown,
    transport_state: str,
    resolved_model_raw: str | None = None,
    usage: Mapping[str, Any] | None = None,
    response_id: str | None = None,
    output_text: str | None = None,
    grader_rule: str | None = None,
    grader_version: str | None = None,
    grader_hash: str | None = None,
    passed: bool | None = None,
    run_mode: str = "smoke",
    wiring_only: bool = False,
    configured: bool = True,
    token_acquired: bool = False,
    data_plane_rbac_verified: bool | None = None,
    deployment_config_verified: bool | None = None,
) -> AttemptAccounting:
    """Derive one attempt's accounting from evidence actually present.

    Fails closed exactly like 03Z-b: a missing provider model, unknown alias,
    missing exact rate, or a non-returned transport yields an ``unpriced`` row
    that withholds the amount itself and blocks any savings/publishable claim,
    while retaining the reservation as unreconciled exposure so it is never
    dropped.
    """

    if transport_state not in TRANSPORT_STATES:
        raise ValueError(f"invalid transport_state {transport_state!r}")

    provider_scoped_out = str(provider or "").strip().lower() in FOUNDRY_PROVIDER_ALIASES
    benchmark_mode = str(run_mode or "").strip().lower() == "benchmark"

    returned = transport_state == RETURNED
    usage = dict(usage or {})
    usage_measured = bool(returned and resolved_model_raw and usage)

    resolved_model_source = PROVIDER_REPORTED if resolved_model_raw else UNAVAILABLE
    pricing_key = (
        rate_card.resolve_pricing_key(resolved_model_raw) if resolved_model_raw else None
    )

    authorized_upper_bound = reservation.total_usd if reservation.priced else _ZERO

    if usage_measured:
        cost = rate_card.composite_cost(
            usage, pricing_key=pricing_key, include_router_markup=is_router_arm
        )
    else:
        cost = CostBreakdown(
            priced=False,
            pricing_key=pricing_key,
            router_markup_usd=_ZERO,
            input_usd=_ZERO,
            output_usd=_ZERO,
            cached_usd=_ZERO,
            reasoning_usd=_ZERO,
            reason="no returned provider response with usage" if not returned else None,
        )

    pricing_complete = bool(cost.priced)
    cost_derived = bool(cost.priced)
    known_cost = cost.total_usd if cost.priced else None

    if cost.priced and returned:
        billability_state = KNOWN_BILLED
        unreconciled_exposure = _ZERO
        cost_complete = True
        reconciliation_required = False
    else:
        # Still billable even when unpriced/unknown: retain the reservation as
        # unreconciled exposure and never claim the request cost is settled.
        billability_state = BILLABILITY_UNKNOWN
        unreconciled_exposure = authorized_upper_bound
        cost_complete = False
        reconciliation_required = transport_state in {IN_FLIGHT, UNKNOWN}

    quality_graded = passed is not None
    benchmark_eligible = bool(
        cost.priced
        and cost_complete
        and usage_measured
        and not provider_scoped_out
    )
    publishable = bool(
        benchmark_eligible
        and benchmark_mode
        and not wiring_only
        and quality_graded
        and token_acquired
        and data_plane_rbac_verified is True
        and deployment_config_verified is True
    )
    savings_claim_allowed = bool(
        benchmark_eligible and cost_complete and pricing_complete and not wiring_only
    )

    return AttemptAccounting(
        arm=arm,
        requested_model=requested_model,
        deployment=deployment,
        provider=provider,
        resolved_model_raw=resolved_model_raw,
        resolved_model_source=resolved_model_source,
        pricing_key=pricing_key,
        response_id_hash=hash_secret(response_id),
        output_hash=hash_secret(output_text),
        usage={
            k: float(usage.get(k, 0.0) or 0.0)
            for k in ("input", "cached", "output", "reasoning")
        },
        transport_state=transport_state,
        billability_state=billability_state,
        rate_card_hash=rate_card.rate_card_hash(),
        router_input_markup_usd=cost.router_markup_usd if cost.priced else None,
        underlying_input_usd=cost.input_usd if cost.priced else None,
        underlying_output_usd=cost.output_usd if cost.priced else None,
        cached_usd=cost.cached_usd if cost.priced else None,
        reasoning_usd=cost.reasoning_usd if cost.priced else None,
        known_rate_card_derived_cost_usd=known_cost,
        unreconciled_reserved_exposure_usd=unreconciled_exposure,
        authorized_upper_bound_usd=authorized_upper_bound,
        cost_complete=cost_complete,
        grader_rule=grader_rule,
        grader_version=grader_version,
        grader_hash=grader_hash,
        passed=passed,
        configured=configured,
        token_acquired=token_acquired,
        data_plane_rbac_verified=data_plane_rbac_verified,
        deployment_config_verified=deployment_config_verified,
        usage_measured=usage_measured,
        cost_derived=cost_derived,
        pricing_complete=pricing_complete,
        quality_graded=quality_graded,
        wiring_only=wiring_only,
        benchmark_eligible=benchmark_eligible,
        publishable=publishable,
        savings_claim_allowed=savings_claim_allowed,
        unpriced_reason=cost.reason,
        reconciliation_required=reconciliation_required,
    )
