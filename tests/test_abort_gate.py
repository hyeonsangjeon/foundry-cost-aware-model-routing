"""Tests for the atomic durable abort/dispatch gate (BOLT-03B step 4)."""

from __future__ import annotations

from pathlib import Path

from router.abort_gate import (
    ABORTED,
    COMPLETED,
    IN_FLIGHT,
    AbortGate,
    request_cancellation,
    seal_in_flight_as_unreconciled,
)


def _gate(tmp_path: Path) -> AbortGate:
    return AbortGate(tmp_path / "gate.sqlite")


def test_abort_before_admission_emits_no_wire_request(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    gate.reserve("a1", "0.01")
    outcome = gate.abort()
    assert outcome.status == ABORTED
    # Admission is refused after abort committed: the runner must not dispatch.
    assert gate.admit("a1") is False
    assert gate.attempt_state("a1") != IN_FLIGHT
    assert gate.in_flight_ids() == ()


def test_admission_before_abort_snapshots_the_in_flight_attempt(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    gate.reserve("a1", "0.01")
    assert gate.admit("a1") is True  # dispatched
    outcome = gate.abort()
    assert outcome.status == ABORTED
    assert outcome.in_flight_ids == ("a1",)  # recorded in the abort snapshot
    assert gate.abort_snapshot_ids() == ("a1",)
    assert outcome.any_in_flight is True


def test_no_post_cancellation_admission(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    gate.reserve("a1")
    gate.reserve("a2")
    gate.admit("a1")
    gate.abort()
    # a1 was already in flight (snapshotted); a2 can never be admitted now.
    assert gate.admit("a2") is False
    assert "a2" not in gate.abort_snapshot_ids()


def test_completion_first_then_late_abort_is_already_terminal(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    assert gate.complete().status == COMPLETED
    late = gate.abort()
    assert late.status == "already_terminal"
    assert gate.terminal() == COMPLETED  # not rewritten


def test_abort_first_then_completion_yields_aborted_wins(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    gate.reserve("a1")
    gate.admit("a1")
    gate.abort()
    assert gate.complete().status == "aborted_wins"
    assert gate.terminal() == ABORTED


def test_repeated_abort_is_idempotent(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    gate.reserve("a1")
    gate.admit("a1")
    first = gate.abort()
    second = gate.abort()
    assert first.status == ABORTED
    assert second.status == "already_aborted"
    assert second.in_flight_ids == first.in_flight_ids  # same deterministic snapshot


def test_sigint_uses_the_same_path_and_reports_in_flight(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    gate.reserve("a1")
    gate.admit("a1")
    outcome = request_cancellation(gate, reason="sigint")
    assert outcome.status == ABORTED
    assert outcome.any_in_flight is True and outcome.in_flight_ids == ("a1",)


def test_late_provider_result_is_a_linked_reconciliation_artifact(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    gate.reserve("a1")
    gate.admit("a1")
    gate.abort()
    # The in-flight attempt is captured as needing reconciliation, not dropped.
    seal_in_flight_as_unreconciled(gate, gate.abort_snapshot_ids())
    # A result that arrives after sealing appends an immutable artifact rather
    # than rewriting the sealed snapshot.
    gate.record_reconciliation("a1", '{"cost_usd": "0.004", "billed": true}')
    assert gate.reconciliation_artifacts() == [("a1", '{"cost_usd": "0.004", "billed": true}')]
    assert gate.abort_snapshot_ids() == ("a1",)  # snapshot unchanged


def test_sealed_partial_snapshot_replays_after_reopen(tmp_path: Path) -> None:
    path = tmp_path / "gate.sqlite"
    gate = AbortGate(path)
    gate.reserve("a1")
    gate.admit("a1")
    gate.abort(reason="operator")
    gate.close()
    # A separate process (CLI or Cockpit) reopens the same durable store.
    reopened = AbortGate(path)
    assert reopened.terminal() == ABORTED
    assert reopened.abort_snapshot_ids() == ("a1",)


def test_two_handles_share_one_terminal_state(tmp_path: Path) -> None:
    path = tmp_path / "gate.sqlite"
    cli = AbortGate(path)
    cockpit = AbortGate(path)
    cli.reserve("a1")
    cli.admit("a1")
    # Cockpit aborts; the CLI handle observes the same committed terminal.
    assert cockpit.abort().status == ABORTED
    assert cli.terminal() == ABORTED
    assert cli.admit("a1") is False
