"""Append-only JSONL storage for replayable ledger records."""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from .record import LedgerRecord, canonical_json

LedgerValidator = Callable[[list[LedgerRecord]], None]


@dataclass(frozen=True)
class JsonlLedger:
    """Small append-only ledger backed by newline-delimited JSON."""

    path: Path

    def __init__(self, path: Path | str) -> None:
        object.__setattr__(self, "path", Path(path))

    def append(
        self,
        record: LedgerRecord,
        *,
        validator: LedgerValidator | None = None,
    ) -> LedgerRecord:
        return self.append_many((record,), validator=validator)[0]

    def append_many(
        self,
        records: Iterable[LedgerRecord],
        *,
        validator: LedgerValidator | None = None,
    ) -> list[LedgerRecord]:
        validated = [record.validate() for record in records]
        if not validated:
            return []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                handle.seek(0)
                raw = handle.read()
                existing = _decode_records(raw, self.path)
                _verify_chain(existing, self.path)
                if validator is not None:
                    validator(existing)

                previous_hash = existing[-1].record_hash if existing else None
                chained: list[LedgerRecord] = []
                for record in validated:
                    sealed = record.with_previous_hash(previous_hash)
                    chained.append(sealed)
                    previous_hash = sealed.record_hash
                if validator is not None:
                    validator([*existing, *chained])

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

    def iter_records(self) -> Iterator[LedgerRecord]:
        return iter(self.read_all())

    def read_all(self) -> list[LedgerRecord]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            try:
                records = _decode_records(handle.read(), self.path)
                _verify_chain(records, self.path)
                return records
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _decode_records(raw: str, path: Path) -> list[LedgerRecord]:
    records: list[LedgerRecord] = []
    for line_number, line in enumerate(raw.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid ledger JSON at {path}:{line_number}: {exc.msg}"
            ) from exc
        try:
            records.append(LedgerRecord.from_dict(payload))
        except ValueError as exc:
            raise ValueError(f"invalid ledger record at {path}:{line_number}: {exc}") from exc
    return records


def _verify_chain(records: list[LedgerRecord], path: Path) -> None:
    previous_hash = None
    for line_number, record in enumerate(records, start=1):
        if record.previous_hash != previous_hash:
            raise ValueError(
                f"invalid ledger hash chain at {path}:{line_number}: "
                "previous_hash does not match the prior record"
            )
        previous_hash = record.record_hash
