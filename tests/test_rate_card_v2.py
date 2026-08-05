"""Golden tests for the rate-card v2 composite-pricing contract (BOLT-03B step 1).

These pin the composite formula, the versioned exact alias map, the explicit
unsupported-component representation, and the no-default live behavior. Money is
compared as :class:`Decimal` so a float rounding change can never quietly pass.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from router.rate_card import (
    RATE_CARD_SCHEMA_VERSION,
    RateCardError,
    RateCardV2,
    TokenRatesV2,
    conservative_input_token_ceiling,
)

ROOT = Path(__file__).resolve().parents[1]
CARD_YAML = ROOT / "samples" / "pricing" / "rate-card-v2.example.yaml"


@pytest.fixture
def card() -> RateCardV2:
    return RateCardV2.from_yaml(CARD_YAML)


def test_loads_schema_v2_with_markup_alias_and_rates(card: RateCardV2) -> None:
    assert card.schema_version == RATE_CARD_SCHEMA_VERSION
    assert card.router_input_markup == Decimal("0.20")
    assert card.alias_version == 1
    assert card.rates_for("grok-4-1-fast-reasoning") is not None


def test_rejects_unsupported_schema_version() -> None:
    with pytest.raises(RateCardError):
        RateCardV2.from_dict({"schema_version": 1, "rates": {}})


def test_alias_map_is_exact_and_version_preserving(card: RateCardV2) -> None:
    # Two dated variants collapse to one pricing_key, but the map is exact —
    # an unmapped id is never normalized into a neighbour.
    assert card.resolve_pricing_key("grok-4-1-fast-reasoning-2026-05-01") == (
        "grok-4-1-fast-reasoning"
    )
    assert card.resolve_pricing_key("grok-4-1-fast-reasoning") == "grok-4-1-fast-reasoning"
    assert card.resolve_pricing_key("grok-4-1-fast-reasoning-2099-01-01") is None


def test_router_response_resolving_to_grok_is_priced_as_markup_plus_grok(
    card: RateCardV2,
) -> None:
    # §8 acceptance: a fake Router resolving to Grok is priced as Router input
    # markup + pinned Grok input/output, NOT a "model-router" placeholder.
    pricing_key = card.resolve_pricing_key("grok-4-1-fast-reasoning-2026-05-01")
    usage = {"input": 1000, "cached": 0, "output": 500, "reasoning": 0}
    router = card.composite_cost(usage, pricing_key=pricing_key, include_router_markup=True)
    assert router.priced and router.pricing_key == "grok-4-1-fast-reasoning"
    # markup: 1000 * 0.20 / 1e6 ; input: 1000 * 0.20 / 1e6 ; output: 500 * 0.50 / 1e6
    assert router.router_markup_usd == Decimal("1000") * Decimal("0.20") / Decimal(1_000_000)
    assert router.input_usd == Decimal("1000") * Decimal("0.20") / Decimal(1_000_000)
    assert router.output_usd == Decimal("500") * Decimal("0.50") / Decimal(1_000_000)
    assert router.total_usd == (
        router.router_markup_usd + router.input_usd + router.output_usd
    )


def test_direct_arm_omits_router_markup(card: RateCardV2) -> None:
    usage = {"input": 1000, "cached": 0, "output": 500, "reasoning": 0}
    direct = card.composite_cost(
        usage, pricing_key="grok-4-1-fast-reasoning", include_router_markup=False
    )
    router = card.composite_cost(
        usage, pricing_key="grok-4-1-fast-reasoning", include_router_markup=True
    )
    assert direct.router_markup_usd == Decimal(0)
    assert router.total_usd - direct.total_usd == router.router_markup_usd
    assert router.router_markup_usd > 0


def test_cached_and_reasoning_components_are_priced(card: RateCardV2) -> None:
    usage = {"input": 1000, "cached": 400, "output": 200, "reasoning": 100}
    breakdown = card.composite_cost(
        usage, pricing_key="gpt-5.6-sol", include_router_markup=False
    )
    # uncached 600 @ 1.25 ; cached 400 @ 0.125 ; output 200 @ 10 ; reasoning 100 @ 10
    assert breakdown.input_usd == Decimal("600") * Decimal("1.25") / Decimal(1_000_000)
    assert breakdown.cached_usd == Decimal("400") * Decimal("0.125") / Decimal(1_000_000)
    assert breakdown.output_usd == Decimal("200") * Decimal("10.00") / Decimal(1_000_000)
    assert breakdown.reasoning_usd == Decimal("100") * Decimal("10.00") / Decimal(1_000_000)


def test_unsupported_component_fails_closed_when_such_tokens_present(
    card: RateCardV2,
) -> None:
    # gpt-4o pins reasoning: null. Reasoning tokens against it must NOT be
    # priced at an inferred rate — the row goes unpriced.
    usage = {"input": 1000, "cached": 0, "output": 200, "reasoning": 50}
    breakdown = card.composite_cost(
        usage, pricing_key="gpt-4o", include_router_markup=False
    )
    assert not breakdown.priced
    assert "reasoning" in (breakdown.reason or "")


def test_unsupported_component_is_fine_when_zero_such_tokens(card: RateCardV2) -> None:
    usage = {"input": 1000, "cached": 0, "output": 200, "reasoning": 0}
    breakdown = card.composite_cost(
        usage, pricing_key="gpt-4o", include_router_markup=False
    )
    assert breakdown.priced
    assert breakdown.reasoning_usd == Decimal(0)


def test_no_default_fallback_in_live_mode(card: RateCardV2) -> None:
    # An unknown alias / missing rate never prices at a default — it is unpriced.
    key = card.resolve_pricing_key("some-model-nobody-pinned")
    assert key is None
    breakdown = card.composite_cost(
        {"input": 10, "output": 10}, pricing_key=key, include_router_markup=True
    )
    assert not breakdown.priced and breakdown.total_usd == Decimal(0)


def test_serialization_is_stable_and_decimal_stringly(card: RateCardV2) -> None:
    canonical = card.to_canonical()
    assert canonical["router_input_markup"] == "0.20"
    assert canonical["rates"]["gpt-4o"]["reasoning"] is None  # explicit unsupported
    # Money is serialized as strings, and the hash is deterministic.
    assert card.rate_card_hash() == card.rate_card_hash()
    # A full canonical round-trip reproduces the exact same hash.
    reloaded = RateCardV2.from_dict(card.to_canonical())
    assert reloaded.rate_card_hash() == card.rate_card_hash()
    assert reloaded.router_input_markup == card.router_input_markup


def test_reservation_cost_is_a_conservative_upper_bound(card: RateCardV2) -> None:
    reservation = card.reservation_cost(
        pricing_key="grok-4-1-fast-reasoning",
        max_input_tokens=1000,
        max_output_tokens=500,
        include_router_markup=True,
    )
    # The real attempt (with a cache discount and fewer output tokens) can never
    # exceed the reservation.
    real = card.composite_cost(
        {"input": 1000, "cached": 500, "output": 300, "reasoning": 0},
        pricing_key="grok-4-1-fast-reasoning",
        include_router_markup=True,
    )
    assert reservation.priced and reservation.total_usd >= real.total_usd


def test_reservation_uses_the_higher_completion_rate(card: RateCardV2) -> None:
    # A card whose reasoning rate exceeds its output rate must reserve output
    # tokens at the reasoning rate.
    hot = RateCardV2.from_dict(
        {
            "schema_version": 2,
            "router_input_markup": 0,
            "alias_map": {"version": 1, "entries": {}},
            "rates": {"x": {"input": 1.0, "output": 1.0, "reasoning": 9.0}},
        }
    )
    reservation = hot.reservation_cost(
        pricing_key="x", max_input_tokens=0, max_output_tokens=1000,
        include_router_markup=False,
    )
    assert reservation.total_usd == Decimal("1000") * Decimal("9.0") / Decimal(1_000_000)


def test_conservative_input_token_ceiling_is_an_upper_bound() -> None:
    messages = [
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "hello world " * 20},
    ]
    ceiling = conservative_input_token_ceiling(messages)
    # A real tokenizer produces far fewer tokens than the UTF-8 byte length.
    total_chars = len("you are helpful") + len("hello world " * 20)
    assert ceiling >= total_chars
    assert conservative_input_token_ceiling("abc") >= 3


def test_rejects_bool_and_nonfinite_rates() -> None:
    with pytest.raises(RateCardError):
        TokenRatesV2.from_dict({"input": True, "output": 1})
    with pytest.raises(RateCardError):
        TokenRatesV2.from_dict({"input": "inf", "output": 1})
