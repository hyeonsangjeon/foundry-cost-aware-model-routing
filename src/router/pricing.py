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


#: Reader-facing USD rendering contract.
#:
#: Every *human-readable* surface renders money through :func:`format_usd` or
#: :func:`format_usd_avg`: totals use two decimals, sub-cent amounts use four so
#: real per-task costs do not collapse to ``$0.00``. The dashboard mirrors the
#: same rule in ``usdSmart`` / ``usdAvg``.
#:
#: The listed callables are the declared reader-facing renderers; they are
#: enforced by ``tests/test_reader_facing_precision.py``. Machine surfaces —
#: ``--json`` payloads, the audit ledger JSONL, replay records, embedded facts
#: and any calculation input — deliberately keep canonical full precision and
#: must never be routed through these formatters.
READER_FACING_USD_RENDERERS: tuple[str, ...] = (
    "router.pipeline.format_replay_text",
    "router.experiment.format_experiment_text",
    "router.measure.format_dry_run_table",
    "router.measure.format_catalog",
    "router.cli.format_compare_text",
)

#: Machine surfaces that must retain canonical (unrounded) precision.
CANONICAL_PRECISION_SURFACES: tuple[str, ...] = (
    "router.pipeline.format_replay_json",
    "router.pipeline.format_eval_report",
    "router.pipeline.format_regression_report",
    "router.measure run-record stopped_reason",
    "router.ledger",
    "experiment --json",
    "replay --ledger",
)


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
