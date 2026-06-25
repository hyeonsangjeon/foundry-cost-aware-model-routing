"""Deterministic candidate selection over precomputed offline signals."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from policy import Candidate

SignalMap = Mapping[str, Mapping[str, Any]]
TieBreaker = Callable[[tuple[str, ...]], str]


@dataclass(frozen=True)
class SelectionAttempt:
    """One evaluated candidate."""

    model: str
    signals: dict[str, Any]
    accepted: bool
    score: float


@dataclass(frozen=True)
class SelectionResult:
    """Final candidate decision and the evaluated attempts."""

    mode: str
    chosen_model: str | None
    reason: str
    accepted: bool
    attempts: tuple[SelectionAttempt, ...]


def ordered_select(
    candidates: tuple[Candidate, ...],
    signals_by_model: SignalMap,
) -> SelectionResult:
    """Try candidates in policy order and accept the first clean result."""

    attempts: list[SelectionAttempt] = []
    for index, candidate in enumerate(candidates):
        attempt = _attempt(candidate.model, signals_by_model)
        attempts.append(attempt)
        if attempt.accepted:
            return SelectionResult(
                mode="ordered",
                chosen_model=candidate.model,
                reason="clean-first" if index == 0 else "escalated",
                accepted=True,
                attempts=tuple(attempts),
            )

    chosen = max(attempts, key=lambda item: item.score) if attempts else None
    return SelectionResult(
        mode="ordered",
        chosen_model=chosen.model if chosen else None,
        reason="no-clean-candidate",
        accepted=False,
        attempts=tuple(attempts),
    )


def compare_select(
    candidates: tuple[Candidate, ...],
    signals_by_model: SignalMap,
    tie_breaker: TieBreaker | None = None,
) -> SelectionResult:
    """Evaluate every candidate and choose the highest-scoring result."""

    attempts = tuple(_attempt(candidate.model, signals_by_model) for candidate in candidates)
    if not attempts:
        return SelectionResult(
            mode="compare",
            chosen_model=None,
            reason="no-candidates",
            accepted=False,
            attempts=(),
        )

    best_score = max(attempt.score for attempt in attempts)
    tied = tuple(attempt.model for attempt in attempts if attempt.score == best_score)
    chosen_model = _break_tie(tied, candidates, tie_breaker)
    chosen_attempt = next(attempt for attempt in attempts if attempt.model == chosen_model)
    return SelectionResult(
        mode="compare",
        chosen_model=chosen_model,
        reason="compared" if len(tied) == 1 else "tie-broken",
        accepted=chosen_attempt.accepted,
        attempts=attempts,
    )


def _attempt(model: str, signals_by_model: SignalMap) -> SelectionAttempt:
    raw = signals_by_model.get(model)
    if raw is None:
        raise ValueError(f"missing offline signals for model {model!r}")
    signals = dict(raw)
    return SelectionAttempt(
        model=model,
        signals=signals,
        accepted=_is_clean(signals),
        score=_execution_score(signals),
    )


def _is_clean(signals: Mapping[str, Any]) -> bool:
    checks = _boolean_checks(signals)
    return bool(checks) and all(checks.values())


def _execution_score(signals: Mapping[str, Any]) -> float:
    checks = _boolean_checks(signals)
    if not checks:
        return 0.0
    passed = sum(1 for value in checks.values() if value)
    return passed / len(checks)


def _boolean_checks(signals: Mapping[str, Any]) -> dict[str, bool]:
    return {key: value for key, value in signals.items() if isinstance(value, bool)}


def _break_tie(
    tied_models: tuple[str, ...],
    candidates: tuple[Candidate, ...],
    tie_breaker: TieBreaker | None,
) -> str:
    if tie_breaker is not None:
        chosen = tie_breaker(tied_models)
        if chosen not in tied_models:
            raise ValueError(f"tie breaker returned unknown model {chosen!r}")
        return chosen

    rank = {candidate.model: index for index, candidate in enumerate(candidates)}
    return min(tied_models, key=lambda model: rank.get(model, len(rank)))
