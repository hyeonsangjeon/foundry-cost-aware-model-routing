"""Tests for the reservation-based hard spend gate (BOLT-03B step 3)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from router.rate_card import RateCardV2
from router.spend_gate import (
    BudgetError,
    BudgetExceeded,
    SpendLedger,
    validate_budget,
)

ROOT = Path(__file__).resolve().parents[1]
CARD_YAML = ROOT / "samples" / "pricing" / "rate-card-v2.example.yaml"


@pytest.fixture
def card() -> RateCardV2:
    return RateCardV2.from_yaml(CARD_YAML)


@pytest.mark.parametrize("bad", [True, False, 0, -1, -0.5, float("nan"), float("inf")])
def test_validate_budget_rejects_invalid(bad: object) -> None:
    with pytest.raises(BudgetError):
        validate_budget(bad)


def test_validate_budget_accepts_positive() -> None:
    assert validate_budget(0.10) == Decimal("0.10")
    assert validate_budget("0.25") == Decimal("0.25")


def test_reservation_proves_cap_before_dispatch(card: RateCardV2) -> None:
    # A conservative rate-card reservation that would cross the cap is denied,
    # and (in a runner) no wire request is dispatched.
    reservation = card.reservation_cost(
        pricing_key="gpt-5.6-sol", max_input_tokens=1_000_000, max_output_tokens=1_000_000,
        include_router_markup=True,
    )
    ledger = SpendLedger.create(0.01)
    assert reservation.total_usd > Decimal("0.01")
    assert ledger.reserve(reservation.total_usd) is None  # fail closed
    assert ledger.authorized_upper_bound == Decimal(0)  # nothing admitted


def test_prove_before_dispatch_stops_before_overshoot() -> None:
    # The old bug overshot by the last call's cost. Here each attempt reserves
    # BEFORE dispatch, so the run stops one attempt earlier instead.
    ledger = SpendLedger.create(Decimal("0.30"))
    per_call = Decimal("0.10")
    dispatched = 0
    for _ in range(10):
        reservation = ledger.reserve(per_call)
        if reservation is None:
            break
        dispatched += 1
        ledger.settle_known(reservation, per_call)
    assert dispatched == 3  # 3 * 0.10 == 0.30, the 4th is refused before dispatch
    assert ledger.known_derived_total == Decimal("0.30")


def test_ceiling_only_smoke_cannot_cross_cap() -> None:
    # A one-call smoke reserves its whole authorization ceiling; a second one
    # that would exceed the cap is refused.
    ledger = SpendLedger.create(Decimal("0.10"))
    first = ledger.reserve(Decimal("0.10"))
    assert first is not None
    assert ledger.reserve(Decimal("0.01")) is None
    assert ledger.remaining == Decimal("0")


def test_unreconciled_reservation_is_not_released() -> None:
    ledger = SpendLedger.create(Decimal("0.20"))
    reservation = ledger.reserve(Decimal("0.10"))
    assert reservation is not None
    ledger.settle_unreconciled(reservation)
    # The reservation stays consumed: exposure remains, budget not recovered.
    assert ledger.unreconciled_exposure == Decimal("0.10")
    assert ledger.authorized_upper_bound == Decimal("0.10")
    assert ledger.cost_complete is False
    # It cannot be reused to authorize spend beyond the cap.
    assert ledger.reserve(Decimal("0.11")) is None


def test_reservation_cannot_be_double_settled() -> None:
    ledger = SpendLedger.create(Decimal("1.00"))
    reservation = ledger.reserve(Decimal("0.10"))
    assert reservation is not None
    ledger.settle_known(reservation, Decimal("0.05"))
    with pytest.raises(BudgetError):
        ledger.settle_known(reservation, Decimal("0.05"))
    with pytest.raises(BudgetError):
        ledger.settle_unreconciled(reservation)


def test_double_release_cannot_recredit_the_cap() -> None:
    ledger = SpendLedger.create(Decimal("0.10"))
    reservation = ledger.reserve(Decimal("0.10"))
    assert reservation is not None
    ledger.release_not_billed(reservation)
    with pytest.raises(BudgetError):
        ledger.release_not_billed(reservation)


def test_settle_known_recovers_headroom_but_never_exceeds_cap() -> None:
    ledger = SpendLedger.create(Decimal("0.10"))
    reservation = ledger.reserve(Decimal("0.10"))
    assert reservation is not None
    # Real cost came in cheaper than the conservative reservation.
    ledger.settle_known(reservation, Decimal("0.04"))
    assert ledger.known_derived_total == Decimal("0.04")
    assert ledger.remaining == Decimal("0.06")
    assert ledger.cost_complete is True


def test_reserve_can_raise_instead_of_returning_none() -> None:
    ledger = SpendLedger.create(Decimal("0.01"))
    with pytest.raises(BudgetExceeded):
        ledger.reserve(Decimal("0.10"), raise_on_deny=True)


def test_reservation_must_be_positive() -> None:
    ledger = SpendLedger.create(Decimal("1.00"))
    with pytest.raises(BudgetError):
        ledger.reserve(Decimal("0"))
