"""Pricing helpers for offline cost calculations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class TokenRates:
    """Per-token-kind rates in USD per one million tokens."""

    input: float
    cached: float
    output: float
    reasoning: float

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TokenRates:
        return cls(
            input=float(data["input"]),
            cached=float(data["cached"]),
            output=float(data["output"]),
            reasoning=float(data["reasoning"]),
        )


@dataclass(frozen=True)
class PricingTable:
    """Model-name to token-rate table."""

    models: dict[str, TokenRates]
    default: TokenRates
    version: int = 1
    currency: str = "USD"

    @classmethod
    def from_yaml(cls, path: Path | str) -> PricingTable:
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        models = {
            str(model): TokenRates.from_dict(rates)
            for model, rates in data.get("models", {}).items()
        }
        return cls(
            models=models,
            default=TokenRates.from_dict(data["default"]),
            version=int(data.get("version", 1)),
            currency=str(data.get("currency", "USD")),
        )

    def rates_for(self, model: str) -> TokenRates:
        return self.models.get(model, self.default)

    def cost_usd(self, model: str, tokens: Mapping[str, Any]) -> float:
        rates = self.rates_for(model)
        input_tokens = _number(tokens.get("input"))
        cached_tokens = min(input_tokens, _number(tokens.get("cached")))
        uncached_input = max(input_tokens - cached_tokens, 0.0)
        output_tokens = _number(tokens.get("output"))
        reasoning_tokens = _number(tokens.get("reasoning"))
        total = (
            uncached_input * rates.input
            + cached_tokens * rates.cached
            + output_tokens * rates.output
            + reasoning_tokens * rates.reasoning
        )
        return round(total / 1_000_000, 6)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def format_usd(value: float) -> str:
    """Format a USD amount for a human-readable surface (CLI, README, docs).

    Totals show two decimals; sub-cent amounts (``|value| < $0.01``) show four so
    real per-task/model costs don't collapse to ``$0.00``. This mirrors the
    dashboard's ``usdSmart`` helper. The underlying data is never rounded here —
    ledger (JSONL) and ``--json`` output keep full precision for re-verification.
    """

    amount = _number(value)
    if amount != 0.0 and abs(amount) < 0.01:
        return f"${amount:.4f}"
    return f"${amount:.2f}"


def format_usd_avg(value: float) -> str:
    """Format a per-task/per-unit USD average with four decimals (sub-cent detail).

    Mirrors the dashboard's ``usdAvg`` helper: averages are naturally small, so
    four decimals keep them meaningful instead of rounding to two.
    """

    return f"${_number(value):.4f}"
