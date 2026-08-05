"""Reservation-based hard spend gate (BOLT-03B, step 3).

The pre-existing runner priced each call *after* it returned, so a run could
overshoot ``budget_usd`` by exactly the last call's cost. This module fixes that
by proving spend *before* dispatch:

    known_derived_total + outstanding_reservations + next_reservation <= budget_usd

Every transport attempt reserves its conservative maximum cost first; only if
that inequality holds is the attempt admitted. A returned+priced attempt settles
its reservation into the known total; a timeout/unknown attempt keeps its
reservation *consumed* as unreconciled exposure (never silently released before
retry or reconciliation), so the authorized upper bound can never be reused to
authorize spend beyond the cap.

All money is :class:`decimal.Decimal`; rounding is reader-facing only. This is a
local *authorization* guarantee, not a promise about the final Azure invoice —
that boundary is disclosed in reader-facing copy.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from decimal import Decimal

_ZERO = Decimal(0)


class BudgetError(ValueError):
    """Raised for a budget that cannot authorize spend (bool/0/neg/NaN/inf)."""


class BudgetExceeded(RuntimeError):
    """Raised when a reservation would cross the configured local cap."""


def validate_budget(budget: object) -> Decimal:
    """Coerce and validate ``budget_usd``; reject bool/0/negative/NaN/inf.

    A budget must be a positive, finite number. A boolean (even ``True``) is
    rejected because ``budget_usd`` is money, not a flag.
    """

    if isinstance(budget, bool):
        raise BudgetError("budget_usd must be a number, not a bool")
    if isinstance(budget, Decimal):
        value = budget
    elif isinstance(budget, int | float):
        value = Decimal(str(budget))
    elif isinstance(budget, str):
        try:
            value = Decimal(budget)
        except ArithmeticError as exc:
            raise BudgetError(f"budget_usd is not a number: {budget!r}") from exc
    else:
        raise BudgetError(f"budget_usd must be a number, got {type(budget).__name__}")
    if not value.is_finite():
        raise BudgetError("budget_usd must be finite (not NaN/inf)")
    if value <= _ZERO:
        raise BudgetError("budget_usd must be strictly positive")
    return value


@dataclass
class Reservation:
    """A single admitted reservation held against the budget until settled."""

    id: int
    amount_usd: Decimal
    state: str = "outstanding"  # outstanding | settled | unreconciled | released

    @property
    def open(self) -> bool:
        return self.state in {"outstanding", "unreconciled"}


@dataclass
class SpendLedger:
    """Decimal spend authority for one run: reserve, then settle.

    ``authorized_upper_bound`` = known derived total + every still-open
    reservation. ``reserve`` admits an attempt only while that bound plus the new
    reservation stays within ``budget_usd``.
    """

    budget_usd: Decimal
    known_derived_total: Decimal = _ZERO
    _reservations: dict[int, Reservation] = field(default_factory=dict)
    _ids: itertools.count[int] = field(default_factory=lambda: itertools.count(1))

    @classmethod
    def create(cls, budget: object) -> SpendLedger:
        return cls(budget_usd=validate_budget(budget))

    # ---------------------------------------------------------------- views

    @property
    def outstanding_reservations(self) -> Decimal:
        return sum((r.amount_usd for r in self._reservations.values() if r.open), _ZERO)

    @property
    def unreconciled_exposure(self) -> Decimal:
        return sum(
            (r.amount_usd for r in self._reservations.values() if r.state == "unreconciled"),
            _ZERO,
        )

    @property
    def authorized_upper_bound(self) -> Decimal:
        return self.known_derived_total + self.outstanding_reservations

    @property
    def remaining(self) -> Decimal:
        return self.budget_usd - self.authorized_upper_bound

    @property
    def cost_complete(self) -> bool:
        """A run is cost-complete only with zero open/unreconciled exposure."""

        return self.unreconciled_exposure == _ZERO and all(
            r.state in {"settled", "released"} for r in self._reservations.values()
        )

    # -------------------------------------------------------------- reserve

    def can_afford(self, reservation_usd: Decimal) -> bool:
        return (self.authorized_upper_bound + Decimal(reservation_usd)) <= self.budget_usd

    def reserve(
        self, reservation_usd: Decimal, *, raise_on_deny: bool = False
    ) -> Reservation | None:
        """Prove the cap BEFORE dispatch; admit only if it holds.

        Returns the :class:`Reservation` (attempt admitted) or ``None`` (denied,
        fail closed — the caller must NOT dispatch). A non-positive reservation
        is rejected: a real attempt always has a conservative positive ceiling.
        """

        amount = Decimal(reservation_usd)
        if not amount.is_finite() or amount <= _ZERO:
            raise BudgetError(f"reservation must be finite and positive: {reservation_usd!r}")
        if not self.can_afford(amount):
            if raise_on_deny:
                raise BudgetExceeded(
                    f"reservation {amount} would exceed budget {self.budget_usd} "
                    f"(authorized upper bound already {self.authorized_upper_bound})"
                )
            return None
        reservation = Reservation(id=next(self._ids), amount_usd=amount)
        self._reservations[reservation.id] = reservation
        return reservation

    # -------------------------------------------------------------- settle

    def settle_known(self, reservation: Reservation, known_cost_usd: Decimal) -> None:
        """A returned+priced attempt: release the reservation, book the known cost."""

        self._require_open(reservation)
        reservation.state = "settled"
        self.known_derived_total += Decimal(known_cost_usd)

    def settle_unreconciled(self, reservation: Reservation) -> None:
        """Timeout/unknown: keep the reservation consumed as unreconciled exposure.

        The reservation is NOT released; it continues to count against the cap so
        it can never be reused to authorize further spend before reconciliation.
        """

        self._require_open(reservation)
        reservation.state = "unreconciled"

    def release_not_billed(self, reservation: Reservation) -> None:
        """A confirmed not-billed attempt (e.g. rejected pre-dispatch): release it."""

        self._require_open(reservation)
        reservation.state = "released"

    def _require_open(self, reservation: Reservation) -> None:
        held = self._reservations.get(reservation.id)
        if held is None:
            raise BudgetError("reservation was not issued by this ledger")
        if not held.open:
            # Guards against double-release / double-settle re-crediting the cap.
            raise BudgetError(f"reservation {reservation.id} already {held.state}")
