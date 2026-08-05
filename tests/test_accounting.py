"""Tests for the separated per-attempt accounting record (BOLT-03B step 2)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from router.accounting import (
    BILLABILITY_UNKNOWN,
    IN_FLIGHT,
    KNOWN_BILLED,
    PROVIDER_REPORTED,
    RETURNED,
    UNAVAILABLE,
    build_attempt_accounting,
)
from router.rate_card import RateCardV2

ROOT = Path(__file__).resolve().parents[1]
CARD_YAML = ROOT / "samples" / "pricing" / "rate-card-v2.example.yaml"


@pytest.fixture
def card() -> RateCardV2:
    return RateCardV2.from_yaml(CARD_YAML)


def _reservation(card: RateCardV2, key: str = "grok-4-1-fast-reasoning"):
    return card.reservation_cost(
        pricing_key=key, max_input_tokens=2000, max_output_tokens=1000,
        include_router_markup=True,
    )


def test_router_resolving_to_grok_prices_markup_plus_grok(card: RateCardV2) -> None:
    acct = build_attempt_accounting(
        arm="router-smoke",
        requested_model="model-router",
        deployment="model-router",
        provider="openai",
        is_router_arm=True,
        rate_card=card,
        reservation=_reservation(card),
        transport_state=RETURNED,
        resolved_model_raw="grok-4-1-fast-reasoning-2026-05-01",
        usage={"input": 1000, "cached": 0, "output": 500, "reasoning": 0},
        response_id="resp_ABC123",
    )
    # Raw provider model survives; alias yields the pricing key; NOT a placeholder.
    assert acct.resolved_model_raw == "grok-4-1-fast-reasoning-2026-05-01"
    assert acct.resolved_model_source == PROVIDER_REPORTED
    assert acct.pricing_key == "grok-4-1-fast-reasoning"
    assert acct.router_input_markup_usd == Decimal("1000") * Decimal("0.20") / Decimal(1_000_000)
    assert acct.underlying_input_usd == Decimal("1000") * Decimal("0.20") / Decimal(1_000_000)
    assert acct.underlying_output_usd == Decimal("500") * Decimal("0.50") / Decimal(1_000_000)
    assert acct.known_rate_card_derived_cost_usd == (
        acct.router_input_markup_usd + acct.underlying_input_usd + acct.underlying_output_usd
    )
    assert acct.billability_state == KNOWN_BILLED
    assert acct.cost_complete and acct.usage_measured and acct.pricing_complete


def test_response_id_is_hashed_and_never_a_pricing_input(card: RateCardV2) -> None:
    acct = build_attempt_accounting(
        arm="router-smoke", requested_model="model-router", deployment="model-router",
        provider="openai", is_router_arm=True, rate_card=card,
        reservation=_reservation(card), transport_state=RETURNED,
        resolved_model_raw="grok-4-1-fast-reasoning",
        usage={"input": 10, "output": 10}, response_id="resp_secret",
    )
    assert acct.response_id_hash is not None
    assert acct.response_id_hash != "resp_secret"  # hashed, not raw
    assert len(acct.response_id_hash) == 64  # sha256 hex


def test_missing_provider_model_is_unavailable_and_unpriced(card: RateCardV2) -> None:
    acct = build_attempt_accounting(
        arm="router-smoke", requested_model="model-router", deployment="model-router",
        provider="openai", is_router_arm=True, rate_card=card,
        reservation=_reservation(card), transport_state=RETURNED,
        resolved_model_raw=None,  # provider gave no model field
        usage={"input": 10, "output": 10}, response_id="resp_1",
    )
    # A response id must never become a resolved-model source or a pricing key.
    assert acct.resolved_model_source == UNAVAILABLE
    assert acct.pricing_key is None
    assert acct.known_rate_card_derived_cost_usd is None  # amount withheld, not fabricated
    assert acct.cost_complete is False and acct.usage_measured is False
    assert acct.benchmark_eligible is False and acct.savings_claim_allowed is False
    # Reservation retained as unreconciled exposure — never dropped.
    assert acct.unreconciled_reserved_exposure_usd == acct.authorized_upper_bound_usd
    assert acct.unreconciled_reserved_exposure_usd > 0


def test_unknown_alias_is_unpriced(card: RateCardV2) -> None:
    acct = build_attempt_accounting(
        arm="router-smoke", requested_model="model-router", deployment="model-router",
        provider="openai", is_router_arm=True, rate_card=card,
        reservation=_reservation(card), transport_state=RETURNED,
        resolved_model_raw="mystery-model-9000",
        usage={"input": 10, "output": 10},
    )
    assert acct.resolved_model_source == PROVIDER_REPORTED
    assert acct.pricing_key is None
    assert acct.known_rate_card_derived_cost_usd is None
    assert acct.benchmark_eligible is False


def test_in_flight_attempt_keeps_exposure_and_requires_reconciliation(card: RateCardV2) -> None:
    acct = build_attempt_accounting(
        arm="router-smoke", requested_model="model-router", deployment="model-router",
        provider="openai", is_router_arm=True, rate_card=card,
        reservation=_reservation(card), transport_state=IN_FLIGHT,
        resolved_model_raw=None, usage=None,
    )
    assert acct.usage_measured is False
    assert acct.billability_state == BILLABILITY_UNKNOWN
    assert acct.cost_complete is False
    assert acct.reconciliation_required is True
    assert acct.unreconciled_reserved_exposure_usd > 0


def test_no_successful_response_means_usage_not_measured(card: RateCardV2) -> None:
    acct = build_attempt_accounting(
        arm="router-smoke", requested_model="model-router", deployment="model-router",
        provider="openai", is_router_arm=True, rate_card=card,
        reservation=_reservation(card), transport_state="unknown",
        resolved_model_raw=None, usage=None,
    )
    assert acct.usage_measured is False
    assert acct.cost_derived is False


def test_direct_arm_omits_router_markup(card: RateCardV2) -> None:
    acct = build_attempt_accounting(
        arm="premium", requested_model="gpt-5.6-sol", deployment="gpt-5.6-sol",
        provider="openai", is_router_arm=False, rate_card=card,
        reservation=card.reservation_cost(
            pricing_key="gpt-5.6-sol", max_input_tokens=2000, max_output_tokens=1000,
            include_router_markup=False,
        ),
        transport_state=RETURNED, resolved_model_raw="gpt-5.6-sol",
        usage={"input": 1000, "output": 500},
    )
    assert acct.router_input_markup_usd == Decimal(0)
    assert acct.known_rate_card_derived_cost_usd == (
        acct.underlying_input_usd + acct.underlying_output_usd
    )


def test_partner_provider_not_benchmark_eligible(card: RateCardV2) -> None:
    acct = build_attempt_accounting(
        arm="partner", requested_model="deepseek", deployment="deepseek",
        provider="foundry", is_router_arm=False, rate_card=card,
        reservation=card.reservation_cost(
            pricing_key="gpt-4o", max_input_tokens=10, max_output_tokens=10,
            include_router_markup=False,
        ),
        transport_state=RETURNED, resolved_model_raw="gpt-4o",
        usage={"input": 10, "output": 10}, run_mode="benchmark",
    )
    # Scoped-out SDK surface can never be a benchmark-eligible measured row.
    assert acct.benchmark_eligible is False
    assert acct.publishable is False


def test_status_fields_are_independent_in_the_record(card: RateCardV2) -> None:
    acct = build_attempt_accounting(
        arm="router-smoke", requested_model="model-router", deployment="model-router",
        provider="openai", is_router_arm=True, rate_card=card,
        reservation=_reservation(card), transport_state=RETURNED,
        resolved_model_raw="grok-4-1-fast-reasoning",
        usage={"input": 10, "output": 10}, passed=True, run_mode="benchmark",
        wiring_only=False, token_acquired=True,
        data_plane_rbac_verified=True, deployment_config_verified=True,
        grader_rule="exec-signals", grader_version="1",
    )
    status = acct.to_record()["status"]
    for key in (
        "configured", "token_acquired", "data_plane_rbac_verified",
        "deployment_config_verified", "usage_measured", "cost_derived",
        "pricing_complete", "cost_complete", "quality_graded", "wiring_only",
        "benchmark_eligible", "publishable", "savings_claim_allowed",
    ):
        assert key in status
    assert acct.quality_graded is True and acct.passed is True
    assert acct.publishable is True  # all gates satisfied


def test_wiring_only_smoke_is_not_publishable_even_when_priced(card: RateCardV2) -> None:
    acct = build_attempt_accounting(
        arm="router-smoke", requested_model="model-router", deployment="model-router",
        provider="openai", is_router_arm=True, rate_card=card,
        reservation=_reservation(card), transport_state=RETURNED,
        resolved_model_raw="grok-4-1-fast-reasoning",
        usage={"input": 10, "output": 10}, passed=True, run_mode="smoke",
        wiring_only=True, token_acquired=True,
        data_plane_rbac_verified=True, deployment_config_verified=True,
    )
    assert acct.publishable is False
    assert acct.savings_claim_allowed is False
