"""Atomic durable abort/dispatch gate (BOLT-03B, step 4).

Dispatch admission and operator abort share ONE atomic durable gate so an
abort-versus-completion race has a single deterministic terminal state. The gate
is a small SQLite store (the "authenticated local cancellation endpoint/store"
that a separate CLI process and the Cockpit both call). SQLite ``BEGIN
IMMEDIATE`` transactions serialize writers, giving a real compare-and-set:

* A worker transitions ``reserved -> in_flight`` (``admit``) only while
  atomically confirming that cancellation has **not** committed. If abort won the
  gate, admission fails and no wire request starts.
* ``abort`` commits cancellation under the gate and snapshots the already
  admitted in-flight attempt IDs. An in-flight request may still finish; before
  sealing, each is either settled or captured as ``reconciliation_required`` with
  its full reservation retained — the gate never claims "no request in flight".
* If completion committed first, a late ``abort`` returns ``already_terminal`` and
  cannot rewrite the sealed run. A later provider result becomes a *linked
  immutable reconciliation artifact*, never a rewrite of the sealed snapshot.
* Repeated abort is idempotent and safe; ``SIGINT`` requests the same path.
"""

from __future__ import annotations

import signal
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType

RESERVED = "reserved"
IN_FLIGHT = "in_flight"
RETURNED = "returned"
CANCELLED = "cancelled"
UNKNOWN = "unknown"

RUNNING = "running"
ABORTED = "aborted"
COMPLETED = "completed"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class AbortOutcome:
    """Result of an ``abort`` request."""

    status: str  # aborted | already_aborted | already_terminal
    in_flight_ids: tuple[str, ...]

    @property
    def any_in_flight(self) -> bool:
        return bool(self.in_flight_ids)


@dataclass(frozen=True)
class CompleteOutcome:
    """Result of a ``complete`` (seal) request."""

    status: str  # completed | already_completed | aborted_wins


class AbortGate:
    """An atomic durable gate over a SQLite file (shared by CLI + Cockpit)."""

    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        # isolation_level=None -> autocommit; we drive explicit BEGIN IMMEDIATE
        # transactions for the compare-and-set operations.
        self._conn = sqlite3.connect(self.path, isolation_level=None, timeout=30.0)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS gate (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                terminal TEXT NOT NULL,
                terminal_at TEXT,
                reason TEXT
            );
            CREATE TABLE IF NOT EXISTS attempts (
                attempt_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                reserved_usd TEXT,
                reconciliation_required INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS abort_snapshot (
                attempt_id TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS reconciliation (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id TEXT NOT NULL,
                payload TEXT,
                recorded_at TEXT NOT NULL
            );
            """
        )
        self._conn.execute(
            "INSERT OR IGNORE INTO gate (id, terminal) VALUES (1, ?)", (RUNNING,)
        )

    # ------------------------------------------------------------- helpers

    def close(self) -> None:
        self._conn.close()

    def _terminal(self) -> str:
        row = self._conn.execute("SELECT terminal FROM gate WHERE id = 1").fetchone()
        return row[0] if row else RUNNING

    def terminal(self) -> str:
        return self._terminal()

    def _begin(self) -> None:
        self._conn.execute("BEGIN IMMEDIATE")

    # ------------------------------------------------------------- reserve

    def reserve(self, attempt_id: str, reserved_usd: str | None = None) -> None:
        """Record an attempt as ``reserved`` (before admission)."""

        self._conn.execute(
            "INSERT OR REPLACE INTO attempts "
            "(attempt_id, state, reserved_usd, reconciliation_required, updated_at) "
            "VALUES (?, ?, ?, COALESCE("
            "(SELECT reconciliation_required FROM attempts WHERE attempt_id = ?), 0), ?)",
            (attempt_id, RESERVED, reserved_usd, attempt_id, _now()),
        )

    # -------------------------------------------------------------- admit

    def admit(self, attempt_id: str) -> bool:
        """CAS: transition ``reserved -> in_flight`` iff not aborted/terminal.

        Returns ``True`` when the attempt is admitted (the caller may dispatch
        exactly one wire request) or ``False`` when abort/completion already won
        the gate (the caller must NOT dispatch).
        """

        self._begin()
        try:
            terminal = self._terminal()
            if terminal != RUNNING:
                self._conn.execute("ROLLBACK")
                return False
            self._conn.execute(
                "INSERT OR REPLACE INTO attempts "
                "(attempt_id, state, reserved_usd, reconciliation_required, updated_at) "
                "VALUES (?, ?, "
                "(SELECT reserved_usd FROM attempts WHERE attempt_id = ?), "
                "COALESCE((SELECT reconciliation_required FROM attempts "
                "WHERE attempt_id = ?), 0), ?)",
                (attempt_id, IN_FLIGHT, attempt_id, attempt_id, _now()),
            )
            self._conn.execute("COMMIT")
            return True
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # -------------------------------------------------------------- settle

    def settle(self, attempt_id: str, state: str) -> None:
        """Record a confirmed terminal transport state for an in-flight attempt.

        After the run is sealed this does not rewrite the sealed snapshot; use
        :meth:`record_reconciliation` for a post-seal provider result.
        """

        if state not in {RETURNED, CANCELLED, UNKNOWN}:
            raise ValueError(f"invalid settle state {state!r}")
        reconciliation = 1 if state in {UNKNOWN} else 0
        self._conn.execute(
            "UPDATE attempts SET state = ?, reconciliation_required = ?, updated_at = ? "
            "WHERE attempt_id = ?",
            (state, reconciliation, _now(), attempt_id),
        )

    # --------------------------------------------------------------- abort

    def abort(self, reason: str = "operator") -> AbortOutcome:
        """Commit cancellation under the gate and snapshot in-flight attempts."""

        self._begin()
        try:
            terminal = self._terminal()
            if terminal == COMPLETED:
                self._conn.execute("ROLLBACK")
                return AbortOutcome(status="already_terminal", in_flight_ids=())
            if terminal == ABORTED:
                ids = self._snapshot_ids()
                self._conn.execute("ROLLBACK")
                return AbortOutcome(status="already_aborted", in_flight_ids=ids)
            in_flight = tuple(
                row[0]
                for row in self._conn.execute(
                    "SELECT attempt_id FROM attempts WHERE state = ? ORDER BY attempt_id",
                    (IN_FLIGHT,),
                ).fetchall()
            )
            self._conn.execute(
                "UPDATE gate SET terminal = ?, terminal_at = ?, reason = ? WHERE id = 1",
                (ABORTED, _now(), reason),
            )
            for attempt_id in in_flight:
                self._conn.execute(
                    "INSERT OR IGNORE INTO abort_snapshot (attempt_id) VALUES (?)",
                    (attempt_id,),
                )
                # In-flight requests may still finish: retain the reservation as
                # unreconciled exposure until settled/reconciled.
                self._conn.execute(
                    "UPDATE attempts SET reconciliation_required = 1, updated_at = ? "
                    "WHERE attempt_id = ?",
                    (_now(), attempt_id),
                )
            self._conn.execute("COMMIT")
            return AbortOutcome(status=ABORTED, in_flight_ids=in_flight)
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def _snapshot_ids(self) -> tuple[str, ...]:
        return tuple(
            row[0]
            for row in self._conn.execute(
                "SELECT attempt_id FROM abort_snapshot ORDER BY attempt_id"
            ).fetchall()
        )

    def abort_snapshot_ids(self) -> tuple[str, ...]:
        return self._snapshot_ids()

    # ------------------------------------------------------------ complete

    def complete(self) -> CompleteOutcome:
        """Seal the run as completed, unless abort already won the gate."""

        self._begin()
        try:
            terminal = self._terminal()
            if terminal == ABORTED:
                self._conn.execute("ROLLBACK")
                return CompleteOutcome(status="aborted_wins")
            if terminal == COMPLETED:
                self._conn.execute("ROLLBACK")
                return CompleteOutcome(status="already_completed")
            self._conn.execute(
                "UPDATE gate SET terminal = ?, terminal_at = ? WHERE id = 1",
                (COMPLETED, _now()),
            )
            self._conn.execute("COMMIT")
            return CompleteOutcome(status=COMPLETED)
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ------------------------------------------------------- reconciliation

    def record_reconciliation(self, attempt_id: str, payload: str) -> None:
        """Append a linked immutable reconciliation artifact (post-seal result)."""

        self._conn.execute(
            "INSERT INTO reconciliation (attempt_id, payload, recorded_at) VALUES (?, ?, ?)",
            (attempt_id, payload, _now()),
        )

    def reconciliation_artifacts(self) -> list[tuple[str, str | None]]:
        return [
            (row[0], row[1])
            for row in self._conn.execute(
                "SELECT attempt_id, payload FROM reconciliation ORDER BY seq"
            ).fetchall()
        ]

    # -------------------------------------------------------------- status

    def attempt_state(self, attempt_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT state FROM attempts WHERE attempt_id = ?", (attempt_id,)
        ).fetchone()
        return row[0] if row else None

    def in_flight_ids(self) -> tuple[str, ...]:
        return tuple(
            row[0]
            for row in self._conn.execute(
                "SELECT attempt_id FROM attempts WHERE state = ? ORDER BY attempt_id",
                (IN_FLIGHT,),
            ).fetchall()
        )


def request_cancellation(gate: AbortGate, reason: str = "sigint") -> AbortOutcome:
    """SIGINT/Cockpit/CLI entry point: the same cancellation/seal path.

    Reports whether any attempt remains in flight so the caller can surface that
    honestly rather than claiming a clean stop.
    """

    return gate.abort(reason=reason)


def install_sigint_handler(gate: AbortGate) -> None:  # pragma: no cover - signal wiring
    """Route ``SIGINT`` through the same durable cancellation gate."""

    def _handler(signum: int, frame: FrameType | None) -> None:
        request_cancellation(gate, reason="sigint")

    signal.signal(signal.SIGINT, _handler)


def seal_in_flight_as_unreconciled(gate: AbortGate, ids: Iterable[str]) -> None:
    """Mark the abort snapshot's still-in-flight attempts as needing reconciliation."""

    for attempt_id in ids:
        state = gate.attempt_state(attempt_id)
        if state == IN_FLIGHT:
            gate.settle(attempt_id, UNKNOWN)
