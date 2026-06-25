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
