"""Canonical, hash-chained audit for **measured** runs.

This is the measured-side counterpart to :mod:`router.ledger.record` /
:mod:`~router.ledger.store` / :mod:`~router.ledger.replay` — the strict
*offline* audit that is ``measured = false`` by contract. Real arena rows (live
fleet calls, or a recorded snapshot replayed over real usage) get the same two
guarantees the offline ledger provides, without ever touching it:

* **Tamper-evidence** — every row is sealed with a ``record_hash`` over its
  canonical payload and linked to the prior row through ``previous_hash``, so a
  single edited byte breaks the chain.
* **Deterministic cost replay** — each row embeds the priced ``pricing_snapshot``
  it was scored against, and verification re-derives every call's cost from its
  recorded token ``usage`` × that rate card and confirms it matches. The
  measured *usage* is fixed evidence; the *cost* is a pure function of it.

The two audits stay deliberately separate: the offline ledger only ever holds
offline projections, this one only ever holds measured spend. The only shared
code is the pure hashing primitive (:func:`~router.ledger.record.stable_hash` /
:func:`~router.ledger.record.canonical_json`), so hashes are byte-identical
across both.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any

from ..pricing import PricingTable, TokenRates
from .record import canonical_json, stable_hash

MEASURED_LEDGER_SCHEMA_VERSION = 1


def pricing_snapshot(pricing: PricingTable, models: Iterable[str]) -> dict[str, Any]:
    """Pin the rate card for the models a measured row prices against."""

    unique = sorted({str(model) for model in models})
    return {
        "version": pricing.version,
        "currency": pricing.currency,
        "default": asdict(pricing.default),
        "models": {model: asdict(pricing.rates_for(model)) for model in unique},
    }


def pricing_from_snapshot(snapshot: Mapping[str, Any]) -> PricingTable:
    """Rebuild a :class:`PricingTable` from a stored snapshot for cost replay."""

    try:
        return PricingTable(
            version=int(snapshot["version"]),
            currency=str(snapshot["currency"]),
            default=TokenRates.from_dict(snapshot["default"]),
            models={
                str(model): TokenRates.from_dict(rates)
                for model, rates in snapshot["models"].items()
            },
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"malformed measured pricing_snapshot: {exc}") from exc


def _models_in_outcome(outcome: Mapping[str, Any]) -> list[str]:
    """Every model name a measured outcome prices against (arms + their calls)."""

    models: set[str] = set()
    for arm in outcome.get("arms", {}).values():
        if arm.get("chosen_model"):
            models.add(str(arm["chosen_model"]))
        for call in arm.get("calls", []):
            if call.get("model"):
                models.add(str(call["model"]))
    return sorted(models)


def _is_digest(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


@dataclass(frozen=True)
class MeasuredLedgerRecord:
    """One self-contained, hash-chained measured arena row."""

    schema_version: int
    captured_at: str
    pricing_version: int
    pricing_hash: str
    pricing_snapshot: dict[str, Any]
    outcome: dict[str, Any]
    previous_hash: str | None
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "captured_at": self.captured_at,
            "pricing_version": self.pricing_version,
            "pricing_hash": self.pricing_hash,
            "pricing_snapshot": self.pricing_snapshot,
            "outcome": self.outcome,
            "previous_hash": self.previous_hash,
            "record_hash": self.record_hash,
        }

    def validate(self) -> MeasuredLedgerRecord:
        if self.schema_version != MEASURED_LEDGER_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported measured ledger schema version {self.schema_version}; "
                f"expected {MEASURED_LEDGER_SCHEMA_VERSION}"
            )
        if not isinstance(self.captured_at, str) or not self.captured_at:
            raise ValueError("measured ledger captured_at must be a non-empty ISO-8601 string")
        if not _is_digest(self.pricing_hash):
            raise ValueError("measured ledger pricing_hash must be a lowercase SHA-256 digest")
        if self.pricing_hash != stable_hash(self.pricing_snapshot):
            raise ValueError("measured ledger pricing_hash does not match pricing_snapshot")
        _validate_outcome(self.outcome)
        if self.previous_hash is not None and not _is_digest(self.previous_hash):
            raise ValueError("measured ledger previous_hash must be null or a SHA-256 digest")
        if not _is_digest(self.record_hash):
            raise ValueError("measured ledger record_hash must be a lowercase SHA-256 digest")
        if self.record_hash != _record_hash(self):
            raise ValueError("measured ledger record_hash does not match its canonical payload")
        return self

    def with_previous_hash(self, previous_hash: str | None) -> MeasuredLedgerRecord:
        """Return this row chained to ``previous_hash`` with a fresh digest."""

        unsealed = replace(self, previous_hash=previous_hash, record_hash="")
        return replace(unsealed, record_hash=_record_hash(unsealed)).validate()

    @classmethod
    def build(
        cls,
        outcome: Mapping[str, Any],
        *,
        pricing: PricingTable,
        captured_at: str,
    ) -> MeasuredLedgerRecord:
        """Seal one measured outcome into an unchained record (``previous_hash=None``)."""

        snapshot = pricing_snapshot(pricing, _models_in_outcome(outcome))
        record = cls(
            schema_version=MEASURED_LEDGER_SCHEMA_VERSION,
            captured_at=str(captured_at),
            pricing_version=pricing.version,
            pricing_hash=stable_hash(snapshot),
            pricing_snapshot=snapshot,
            outcome=json.loads(json.dumps(outcome)),
            previous_hash=None,
            record_hash="",
        )
        return record.with_previous_hash(None)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MeasuredLedgerRecord:
        if not isinstance(data, Mapping):
            raise ValueError("measured ledger record must be a JSON object")
        allowed = {field.name for field in fields(cls)}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ValueError(f"unknown measured ledger fields: {', '.join(unknown)}")
        try:
            record = cls(
                schema_version=int(data["schema_version"]),
                captured_at=str(data["captured_at"]),
                pricing_version=int(data["pricing_version"]),
                pricing_hash=str(data["pricing_hash"]),
                pricing_snapshot=dict(data["pricing_snapshot"]),
                outcome=dict(data["outcome"]),
                previous_hash=(
                    str(data["previous_hash"]) if data.get("previous_hash") is not None else None
                ),
                record_hash=str(data["record_hash"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"malformed measured ledger record: {exc}") from exc
        return record.validate()


def _record_hash(record: MeasuredLedgerRecord) -> str:
    payload = record.to_dict()
    payload.pop("record_hash", None)
    return stable_hash(payload)


def _validate_outcome(outcome: Mapping[str, Any]) -> None:
    if not isinstance(outcome, Mapping) or not outcome.get("task_id"):
        raise ValueError("measured ledger outcome must carry a task_id")
    arms = outcome.get("arms")
    if not isinstance(arms, Mapping) or not arms:
        raise ValueError("measured ledger outcome must carry at least one arm")
    labels = outcome.get("labels")
    if not isinstance(labels, Mapping) or "measured" not in labels:
        raise ValueError("measured ledger outcome labels must include 'measured'")
    if not isinstance(labels["measured"], bool):
        raise ValueError("measured ledger outcome labels.measured must be a bool")
    for name, arm in arms.items():
        if "cost_usd" not in arm:
            raise ValueError(f"measured arm {name!r} is missing cost_usd")
        for call in arm.get("calls", []):
            if "model" not in call or "usage" not in call or "cost_usd" not in call:
                raise ValueError(f"measured arm {name!r} has a call missing model/usage/cost_usd")


@dataclass(frozen=True)
class MeasuredJsonlLedger:
    """Append-only, hash-chained JSONL store for measured arena rows."""

    path: Path

    def __init__(self, path: Path | str) -> None:
        object.__setattr__(self, "path", Path(path))

    def append(self, record: MeasuredLedgerRecord) -> MeasuredLedgerRecord:
        return self.append_many((record,))[0]

    def append_many(
        self, records: Iterable[MeasuredLedgerRecord]
    ) -> list[MeasuredLedgerRecord]:
        validated = [record.validate() for record in records]
        if not validated:
            return []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                handle.seek(0)
                raw = handle.read()
                existing = _decode(raw, self.path)
                _verify_chain(existing, self.path)
                previous_hash = existing[-1].record_hash if existing else None
                chained: list[MeasuredLedgerRecord] = []
                for record in validated:
                    sealed = record.with_previous_hash(previous_hash)
                    chained.append(sealed)
                    previous_hash = sealed.record_hash
                separator = "\n" if raw and not raw.endswith("\n") else ""
                encoded = separator + "".join(
                    f"{canonical_json(record.to_dict())}\n" for record in chained
                )
                handle.seek(0, os.SEEK_END)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
                return chained
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def read_all(self) -> list[MeasuredLedgerRecord]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            try:
                records = _decode(handle.read(), self.path)
                _verify_chain(records, self.path)
                return records
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _decode(raw: str, path: Path) -> list[MeasuredLedgerRecord]:
    records: list[MeasuredLedgerRecord] = []
    for line_number, line in enumerate(raw.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid measured ledger JSON at {path}:{line_number}: {exc.msg}"
            ) from exc
        try:
            records.append(MeasuredLedgerRecord.from_dict(payload))
        except ValueError as exc:
            raise ValueError(
                f"invalid measured ledger record at {path}:{line_number}: {exc}"
            ) from exc
    return records


def _verify_chain(records: list[MeasuredLedgerRecord], path: Path) -> None:
    previous_hash = None
    for line_number, record in enumerate(records, start=1):
        if record.previous_hash != previous_hash:
            raise ValueError(
                f"invalid measured ledger hash chain at {path}:{line_number}: "
                "previous_hash does not match the prior record"
            )
        previous_hash = record.record_hash


@dataclass(frozen=True)
class MeasuredReplayReport:
    """Verification result for a sequence of measured ledger records."""

    records: int
    replayed: int
    mismatches: tuple[dict[str, Any], ...]

    @property
    def ok(self) -> bool:
        return self.records > 0 and self.replayed == self.records and not self.mismatches

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": self.records,
            "replayed": self.replayed,
            "mismatches": list(self.mismatches),
            "ok": self.ok,
        }


def verify_measured_records(records: list[MeasuredLedgerRecord]) -> MeasuredReplayReport:
    """Re-derive every recorded call cost from its usage × the pinned rate card."""

    mismatches: list[dict[str, Any]] = []
    for record in records:
        record.validate()  # record_hash + pricing_hash integrity
        pricing = pricing_from_snapshot(record.pricing_snapshot)
        issues = _cost_replay_issues(record.outcome, pricing)
        if issues:
            mismatches.append(
                {
                    "task_id": record.outcome.get("task_id"),
                    "record_hash": record.record_hash,
                    "issues": issues,
                }
            )
    count = len(records)
    return MeasuredReplayReport(
        records=count,
        replayed=count - len(mismatches),
        mismatches=tuple(mismatches),
    )


def verify_measured_ledger(path: Path | str) -> MeasuredReplayReport:
    """Verify chain integrity and cost replay for an on-disk measured ledger."""

    return verify_measured_records(MeasuredJsonlLedger(path).read_all())


def _cost_replay_issues(outcome: Mapping[str, Any], pricing: PricingTable) -> list[str]:
    issues: list[str] = []
    for name, arm in outcome.get("arms", {}).items():
        for index, call in enumerate(arm.get("calls", [])):
            expected = pricing.cost_usd(str(call["model"]), call.get("usage", {}))
            if canonical_json(expected) != canonical_json(call.get("cost_usd")):
                issues.append(f"arms.{name}.calls[{index}].cost_usd")
    return issues
