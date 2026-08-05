"""Rate-card v2 — the single composite-pricing authority (BOLT-03B, step 1).

Azure AI Foundry Model Router pricing is *composite*, not a single per-model
rate:

    router request cost
      = router input-token markup
      + resolved underlying-model input cost
      + resolved underlying-model output cost
      + any other explicitly pinned token components (cached / reasoning)

Direct-model arms omit the Router markup. This module freezes that contract in a
*versioned* rate card instead of letting the runner infer one, and exposes ONE
function — :meth:`RateCardV2.composite_cost` — that the rate-card schema, the
dry-run estimate, the reservation ceiling, the trace record, and the
summary/replay/comparison surfaces all call, so the five surfaces can never
disagree.

Design rules (from §8):

* **Exact, versioned alias map.** ``resolved_model_raw`` (the provider's
  unmodified ``model`` value, version suffix intact) is mapped to a
  ``pricing_key`` through an explicit alias table that carries its *own*
  version. A hashed response id is diagnostic only and is never a pricing input.
* **No default fallback in live mode.** An unknown alias or a missing exact rate
  yields ``priced=False`` (``unpriced``); it never silently prices at a
  frontier/default rate and never fabricates a saving.
* **Explicit unsupported components.** A cached/reasoning rate that the tenant
  card does not pin is represented as ``None`` (``unsupported``); pricing a
  present cached/reasoning token against a missing rate fails closed.
* **Decimal sub-dollar arithmetic.** All money is accumulated as
  :class:`decimal.Decimal` and serialized as strings; rounding is a reader-facing
  concern only and never happens per call.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from .ledger.record import stable_hash

RATE_CARD_SCHEMA_VERSION = 2
_MILLION = Decimal(1_000_000)
_ZERO = Decimal(0)


class _DecimalSafeLoader(yaml.SafeLoader):
    """A safe YAML loader that reads floats as exact :class:`Decimal` values.

    Money must never round-trip through binary float, so ``0.20`` stays
    ``Decimal("0.20")`` (from its source text) instead of ``float`` ``0.2``.
    """


def _yaml_decimal(loader: yaml.Loader, node: yaml.Node) -> Decimal:
    return Decimal(loader.construct_scalar(node))


_DecimalSafeLoader.add_constructor("tag:yaml.org,2002:float", _yaml_decimal)

# Canonical token-kind names as normalized by ``foundry_live._usage_from_response``.
_USAGE_KEYS = ("input", "cached", "output", "reasoning")


class RateCardError(RuntimeError):
    """Raised when a rate-card document is malformed or unsupported."""


def _dec(value: Any) -> Decimal:
    """Coerce a rate/token count to :class:`Decimal` (rejecting NaN/inf)."""

    if isinstance(value, bool):
        raise RateCardError(f"expected a number, got bool {value!r}")
    if value is None:
        return _ZERO
    try:
        result = Decimal(str(value))
    except (ArithmeticError, ValueError) as exc:
        raise RateCardError(f"not a valid decimal: {value!r}") from exc
    if not result.is_finite():
        raise RateCardError(f"non-finite value not allowed: {value!r}")
    return result


def _rate(value: Any) -> Decimal | None:
    """A per-1M rate: ``None`` means the component is unsupported/unpinned."""

    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {"unsupported", "n/a", "none"}:
        return None
    rate = _dec(value)
    if rate < 0:
        raise RateCardError(f"a negative rate is not allowed: {value!r}")
    return rate


@dataclass(frozen=True)
class TokenRatesV2:
    """Underlying-model per-1M-token rates for one ``pricing_key``.

    ``cached`` / ``reasoning`` are ``None`` when the tenant card does not pin
    them — an *explicit* unsupported representation, never an inferred discount.
    """

    input: Decimal
    output: Decimal
    cached: Decimal | None = None
    reasoning: Decimal | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TokenRatesV2:
        if "input" not in data or "output" not in data:
            raise RateCardError(f"a rate row needs 'input' and 'output': {dict(data)!r}")
        return cls(
            input=_dec(data["input"]),
            output=_dec(data["output"]),
            cached=_rate(data.get("cached")),
            reasoning=_rate(data.get("reasoning")),
        )

    def to_canonical(self) -> dict[str, Any]:
        row: dict[str, Any] = {"input": str(self.input), "output": str(self.output)}
        row["cached"] = None if self.cached is None else str(self.cached)
        row["reasoning"] = None if self.reasoning is None else str(self.reasoning)
        return row


@dataclass(frozen=True)
class CostBreakdown:
    """A composite cost, decomposed so every component is auditable.

    When ``priced`` is ``False`` the row is ``unpriced``: the caller must mark it
    ``benchmark_eligible=false``, set ``cost_complete=false``, and suppress any
    savings claim rather than emitting a fabricated number.
    """

    priced: bool
    pricing_key: str | None
    router_markup_usd: Decimal
    input_usd: Decimal
    output_usd: Decimal
    cached_usd: Decimal
    reasoning_usd: Decimal
    reason: str | None = None

    @property
    def total_usd(self) -> Decimal:
        return (
            self.router_markup_usd
            + self.input_usd
            + self.output_usd
            + self.cached_usd
            + self.reasoning_usd
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "priced": self.priced,
            "pricing_key": self.pricing_key,
            "router_markup_usd": str(self.router_markup_usd),
            "input_usd": str(self.input_usd),
            "output_usd": str(self.output_usd),
            "cached_usd": str(self.cached_usd),
            "reasoning_usd": str(self.reasoning_usd),
            "total_usd": str(self.total_usd),
            "reason": self.reason,
        }


def _unpriced(pricing_key: str | None, reason: str) -> CostBreakdown:
    return CostBreakdown(
        priced=False,
        pricing_key=pricing_key,
        router_markup_usd=_ZERO,
        input_usd=_ZERO,
        output_usd=_ZERO,
        cached_usd=_ZERO,
        reasoning_usd=_ZERO,
        reason=reason,
    )


@dataclass(frozen=True)
class RateCardV2:
    """A frozen, versioned composite rate card."""

    schema_version: int
    currency: str
    unit_basis: str
    source: str
    effective_date: str
    capture_date: str
    region: str
    sku_meter_basis: str
    applicability_notes: str
    router_input_markup: Decimal
    alias_version: int
    alias_map: dict[str, str]
    rates: dict[str, TokenRatesV2]

    # ---------------------------------------------------------------- loading

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RateCardV2:
        version = int(data.get("schema_version", 0))
        if version != RATE_CARD_SCHEMA_VERSION:
            raise RateCardError(
                f"unsupported rate-card schema_version {version!r}; "
                f"expected {RATE_CARD_SCHEMA_VERSION}"
            )
        alias_block = data.get("alias_map") or {}
        if not isinstance(alias_block, Mapping):
            raise RateCardError("alias_map must be a mapping")
        alias_entries = alias_block.get("entries", alias_block)
        alias_version = int(alias_block.get("version", data.get("alias_version", 1)))
        aliases = {str(k): str(v) for k, v in dict(alias_entries).items()}
        rates_block = data.get("rates") or data.get("models") or {}
        rates = {
            str(key): TokenRatesV2.from_dict(row) for key, row in dict(rates_block).items()
        }
        markup = _rate(data.get("router_input_markup"))
        return cls(
            schema_version=version,
            currency=str(data.get("currency", "USD")),
            unit_basis=str(data.get("unit_basis", data.get("unit", "per_1m_tokens"))),
            source=str(data.get("source", "")),
            effective_date=str(data.get("effective_date", "")),
            capture_date=str(data.get("capture_date", "")),
            region=str(data.get("region", "")),
            sku_meter_basis=str(data.get("sku_meter_basis", "")),
            applicability_notes=str(data.get("applicability_notes", "")),
            router_input_markup=_ZERO if markup is None else markup,
            alias_version=alias_version,
            alias_map=aliases,
            rates=rates,
        )

    @classmethod
    def from_yaml(cls, path: Path | str) -> RateCardV2:
        with open(path, encoding="utf-8") as handle:
            data = yaml.load(handle, Loader=_DecimalSafeLoader)  # noqa: S506 - pinned safe subclass
        if not isinstance(data, Mapping):
            raise RateCardError(f"rate card {path} is not a mapping")
        return cls.from_dict(data)

    # ------------------------------------------------------------ serialize

    def to_canonical(self) -> dict[str, Any]:
        """A deterministic, string-money view for hashing and byte comparison."""

        return {
            "schema_version": self.schema_version,
            "currency": self.currency,
            "unit_basis": self.unit_basis,
            "source": self.source,
            "effective_date": self.effective_date,
            "capture_date": self.capture_date,
            "region": self.region,
            "sku_meter_basis": self.sku_meter_basis,
            "applicability_notes": self.applicability_notes,
            "router_input_markup": str(self.router_input_markup),
            "alias_map": {
                "version": self.alias_version,
                "entries": dict(sorted(self.alias_map.items())),
            },
            "rates": {key: self.rates[key].to_canonical() for key in sorted(self.rates)},
        }

    def rate_card_hash(self) -> str:
        """SHA-256 of the canonical rate card (pins it into plan/prereg hashes)."""

        return stable_hash(self.to_canonical())

    # -------------------------------------------------------------- pricing

    def resolve_pricing_key(self, resolved_model_raw: str | None) -> str | None:
        """Map the raw provider ``model`` to a ``pricing_key`` via the exact alias.

        The lookup preserves model/version distinctions (no normalization). An
        unmapped model returns ``None`` — the caller marks the row ``unpriced``.
        A direct-mapped ``pricing_key`` that also names a rate row is accepted
        verbatim, so a card can list a model under its own name.
        """

        if not resolved_model_raw:
            return None
        raw = str(resolved_model_raw).strip()
        if raw in self.alias_map:
            return self.alias_map[raw]
        if raw in self.rates:
            return raw
        return None

    def rates_for(self, pricing_key: str | None) -> TokenRatesV2 | None:
        if pricing_key is None:
            return None
        return self.rates.get(pricing_key)

    def composite_cost(
        self,
        usage: Mapping[str, Any],
        *,
        pricing_key: str | None,
        include_router_markup: bool,
    ) -> CostBreakdown:
        """THE composite formula — every 03B pricing surface calls this.

        Returns a fully decomposed :class:`CostBreakdown`. Live mode never falls
        back to a default rate: an unknown ``pricing_key`` or a missing exact
        component rate produces an ``unpriced`` breakdown.
        """

        rates = self.rates_for(pricing_key)
        if rates is None:
            return _unpriced(
                pricing_key,
                "no pinned rate for pricing_key "
                f"{pricing_key!r} (unknown alias or missing rate; live mode has no default)",
            )

        input_tokens = _dec(usage.get("input"))
        cached_tokens = _dec(usage.get("cached"))
        if cached_tokens > input_tokens:
            cached_tokens = input_tokens
        uncached = input_tokens - cached_tokens
        output_tokens = _dec(usage.get("output"))
        reasoning_tokens = _dec(usage.get("reasoning"))

        if cached_tokens > _ZERO and rates.cached is None:
            return _unpriced(
                pricing_key,
                f"{cached_tokens} cached tokens present but pricing_key "
                f"{pricing_key!r} pins no cached rate",
            )
        if reasoning_tokens > _ZERO and rates.reasoning is None:
            return _unpriced(
                pricing_key,
                f"{reasoning_tokens} reasoning tokens present but pricing_key "
                f"{pricing_key!r} pins no reasoning rate",
            )

        cached_rate = rates.cached or _ZERO
        reasoning_rate = rates.reasoning or _ZERO
        markup_usd = (
            (input_tokens * self.router_input_markup / _MILLION)
            if include_router_markup
            else _ZERO
        )
        return CostBreakdown(
            priced=True,
            pricing_key=pricing_key,
            router_markup_usd=markup_usd,
            input_usd=uncached * rates.input / _MILLION,
            output_usd=output_tokens * rates.output / _MILLION,
            cached_usd=cached_tokens * cached_rate / _MILLION,
            reasoning_usd=reasoning_tokens * reasoning_rate / _MILLION,
        )

    def reservation_cost(
        self,
        *,
        pricing_key: str | None,
        max_input_tokens: int,
        max_output_tokens: int,
        include_router_markup: bool,
    ) -> CostBreakdown:
        """A conservative *upper-bound* cost for one attempt, before dispatch.

        Reserves the worst case: no cache discount on the input ceiling, plus the
        Router markup, plus the output ceiling billed at the higher of the output
        and reasoning rates. Reuses :meth:`composite_cost` so the reservation
        ceiling shares the one composite formula. An unpriced key yields an
        ``unpriced`` breakdown, which the budget gate treats as unreservable.
        """

        rates = self.rates_for(pricing_key)
        if rates is None:
            return _unpriced(pricing_key, f"no pinned rate for pricing_key {pricing_key!r}")
        reasoning_rate = rates.reasoning if rates.reasoning is not None else _ZERO
        # Bill the whole output ceiling at whichever completion rate is higher so
        # the reservation can never under-price the real attempt.
        if reasoning_rate > rates.output:
            usage = {
                "input": max_input_tokens,
                "cached": 0,
                "output": 0,
                "reasoning": max_output_tokens,
            }
        else:
            usage = {
                "input": max_input_tokens,
                "cached": 0,
                "output": max_output_tokens,
                "reasoning": 0,
            }
        return self.composite_cost(
            usage, pricing_key=pricing_key, include_router_markup=include_router_markup
        )


def conservative_input_token_ceiling(messages: Any) -> int:
    """A tested, provably conservative upper bound on prompt tokens.

    Every BPE/tiktoken token encodes at least one UTF-8 byte, so the UTF-8 byte
    length of the serialized request is a hard upper bound on its token count
    (plus a small per-message framing constant). This never under-reserves,
    which is what the budget gate needs; it is deliberately loose rather than a
    best-effort estimate. Independent of any paid tokenizer or network call.
    """

    if isinstance(messages, str):
        text = messages
        frame = 8
    else:
        parts: list[str] = []
        frame = 0
        try:
            for message in messages:
                if isinstance(message, Mapping):
                    parts.append(str(message.get("content", "")))
                    parts.append(str(message.get("role", "")))
                else:
                    parts.append(str(message))
                frame += 8  # per-message role/delimiter framing overhead
        except TypeError:
            parts = [str(messages)]
            frame = 8
        text = "".join(parts)
    return len(text.encode("utf-8")) + frame
