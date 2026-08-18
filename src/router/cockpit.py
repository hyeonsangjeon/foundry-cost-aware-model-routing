"""Cockpit plan-parity run state machine (BOLT-03C, §9).

The browser is a control surface over the *exact* server-side
:class:`~router.run_plan.ResolvedRunPlan`. No credentials or execution authority
live in browser data: the plan, its ``plan_hash``, the human approval, the budget
authority (03B :class:`~router.spend_gate.SpendLedger`), and the abort/dispatch
gate (03B :class:`~router.abort_gate.AbortGate`, the *same* durable store the CLI
uses) are all held here, server-side.

State machine::

    draft -> planned -> preflight_passed -> approved(plan_hash) -> running
      -> complete | partial | failed | aborted
      -> replay_verified | replay_failed

The run is only ever labelled *measured/verified* after it seals a snapshot and
that snapshot **replays** — never from the start response.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from .abort_gate import (
    RETURNED,
    RUNNING,
    UNKNOWN,
    AbortGate,
    request_cancellation,
    seal_in_flight_as_unreconciled,
)
from .measure import (
    DEFAULT_DRY_RUN_TOKENS,
    CellId,
    MeasureCandidate,
    RetryPolicy,
    RunHooks,
    build_catalog,
    load_prompt_workload,
    make_run_id,
    replay_measure,
    run_measure,
)
from .pricing import PricingTable
from .run_plan import (
    ApprovalError,
    LocalRunConfig,
    ResolvedRunPlan,
    check_approval,
    retry_policy_for,
)
from .spend_gate import SpendLedger

_ZERO = Decimal(0)


class RunState(StrEnum):
    DRAFT = "draft"
    PLANNED = "planned"
    PREFLIGHT_PASSED = "preflight_passed"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    ABORTED = "aborted"
    REPLAY_VERIFIED = "replay_verified"
    REPLAY_FAILED = "replay_failed"


# Terminal-before-replay states that seal a snapshot the cockpit then replays.
_SEALED_STATES = {RunState.COMPLETE, RunState.PARTIAL, RunState.ABORTED}


class CockpitError(RuntimeError):
    """A control-surface refusal (stale approval, active-run lock, unpriced, ...)."""


def _attempt_id(cell: CellId) -> str:
    return f"{cell.task_id}::{cell.repeat_idx}::{cell.model}"


@dataclass
class CockpitRun:
    """One live run's server-side state (never trusts the browser for authority)."""

    run_id: str
    run_dir: Path
    plan_hash: str
    idempotency_key: str
    ledger: SpendLedger
    gate_path: Path
    per_cell_reservation: Decimal
    state: RunState = RunState.RUNNING
    events: list[dict[str, Any]] = field(default_factory=list)
    stopped_reason: str | None = None
    error: str | None = None
    measured: bool = False
    summary_matches: bool | None = None
    cost_withheld: bool = False
    cells_done: int = 0
    cells_total: int = 0
    # Reservations for cells admitted but not yet settled (attempt_id -> reservation).
    _pending: dict[str, Any] = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.state not in {RunState.RUNNING}

    @property
    def abort_available(self) -> bool:
        return self.state is RunState.RUNNING

    def view(self) -> dict[str, Any]:
        """Progress/snapshot projection for the browser (no credentials, no paths-as-input)."""

        return {
            "run_id": self.run_id,
            "state": self.state.value,
            "plan_hash": self.plan_hash,
            "cells_done": self.cells_done,
            "cells_total": self.cells_total,
            "running_cost_usd": float(self.ledger.known_derived_total),
            "budget_usd": float(self.ledger.budget_usd),
            "unreconciled_exposure_usd": float(self.ledger.unreconciled_exposure),
            "abort_available": self.abort_available,
            "stopped_reason": self.stopped_reason,
            "error": self.error,
            # measured is only ever true after a verified snapshot replay.
            "measured": self.measured,
            "summary_matches": self.summary_matches,
            "cost_withheld": self.cost_withheld,
            "events": list(self.events),
        }


class CockpitController:
    """Server-side owner of the plan, approval, budget, and abort gate.

    One controller per injected plan. Holds at most one active run (the
    active-run lock); an idempotency key dedupes duplicate clicks; run IDs are
    collision-resistant so a duplicate click can never spend twice or collide an
    output directory.
    """

    def __init__(
        self,
        plan: ResolvedRunPlan,
        config: LocalRunConfig,
        *,
        pricing: PricingTable | None = None,
        client_factory: Callable[[], Any] | None = None,
        results_root: Path | str | None = None,
        retry: RetryPolicy | None = None,
        grader: Any = None,
        prereg: Any = None,
    ) -> None:
        self.plan = plan
        self.config = config
        self._pricing = pricing
        self._client_factory = client_factory
        self._results_root = Path(results_root or "results/cockpit")
        self._retry = retry
        self._grader = grader
        self._prereg = prereg
        self._active: CockpitRun | None = None
        self._runs: dict[str, CockpitRun] = {}
        self._by_idem: dict[str, str] = {}
        self._lock = threading.Lock()

    # -- identity / preview ------------------------------------------------

    @property
    def plan_hash(self) -> str:
        return self.plan.plan_hash

    def preview(self) -> dict[str, Any]:
        """The human-approval summary: planned_cells + base/max transport attempts.

        Never collapses retry-dependent outbound attempts into an exact count.
        """

        return self.plan.approval_view()

    def parity(self) -> dict[str, Any]:
        """The fields every surface must agree on, keyed by ``plan_hash``."""

        ex = self.plan.execution
        return {
            "plan_hash": self.plan_hash,
            "run_mode": self.plan.run_mode,
            "workload": dict(ex["workload"]),
            "arms": [dict(a) for a in self.plan.arms],
            "pricing": {
                "authorization_basis": self.plan.authorization_basis,
                "rate_card_path": self.plan.rate_card_path,
                "fingerprint": ex["pricing"].get("fingerprint"),
            },
            "repetitions": self.plan.repetitions,
            "max_output_tokens": int(ex["request"]["max_output_tokens"]),
            "budget_usd": self.plan.budget_usd,
            "grader": dict(ex["grader"]),
            "planned_cells": self.plan.planned_cells,
        }

    # -- preflight ---------------------------------------------------------

    def _load_pricing(self) -> PricingTable:
        if self._pricing is not None:
            return self._pricing
        card = self.plan.rate_card_path
        if not card:
            raise CockpitError(
                "no pinned rate card: cost cannot be derived — fail closed "
                "(smoke ceiling reserves spend but derives no cost)"
            )
        self._pricing = PricingTable.from_yaml(self.config.resolve_path(card))
        return self._pricing

    def _workload(self) -> dict[str, dict[str, Any]]:
        return load_prompt_workload(self.config.resolve_path(self.plan.workload_path))

    def _candidates(self) -> list[MeasureCandidate]:
        return self.plan.candidates()

    def _unpriced_backends(self, pricing: PricingTable) -> list[str]:
        """Resolved backends with no *explicit* rate-card entry (would price off default)."""

        return [c.model for c in self._candidates() if c.model not in pricing.models]

    def preflight(self) -> dict[str, Any]:
        """Price the plan's workload offline; fail closed on an unpriced backend.

        Returns the dry-run catalog (prompts, validation, per-arm estimate) with
        the ``plan_hash`` so preview and approval bind to the same plan.
        """

        pricing = self._load_pricing()
        workload = self._workload()
        if not workload:
            raise CockpitError(f"workload has no prompt-bearing tasks: {self.plan.workload_path}")
        candidates = self._candidates()
        unpriced = self._unpriced_backends(pricing)
        if unpriced:
            raise CockpitError(
                "unpriced resolved backend(s) "
                f"{sorted(unpriced)}: the pinned rate card has no entry to price them; "
                "fail closed rather than price off the generic default"
            )
        catalog = build_catalog(
            workload, candidates, n=self.plan.repetitions, pricing=pricing
        )
        catalog["plan_hash"] = self.plan_hash
        catalog["workload_path"] = str(self.plan.workload_path)
        return catalog

    def _per_cell_reservation(
        self, pricing: PricingTable, workload: Mapping[str, Mapping[str, Any]]
    ) -> Decimal:
        """Conservative per-cell reservation: the max single-cell list-price cost.

        Reserving this before *every* dispatch never under-reserves, so the hard
        cap can only ever be crossed by refusing a dispatch — never by a
        surprise settle. A run with only a smoke ceiling still reserves a
        strictly positive floor so :class:`SpendLedger` can gate it.
        """

        candidates = self._candidates()
        costs = [
            Decimal(str(pricing.cost_usd(c.model, task.get("tokens") or DEFAULT_DRY_RUN_TOKENS)))
            for c in candidates
            for task in workload.values()
        ]
        top = max(costs) if costs else _ZERO
        if top <= _ZERO:
            # Degenerate estimate (all-zero tokens): reserve a tiny positive floor
            # so the ledger still admits/denies rather than dividing by zero.
            top = Decimal("0.000001")
        return top

    # -- approve + start ---------------------------------------------------

    def approve_and_start(
        self,
        *,
        plan_hash: str | None,
        idempotency_key: str | None,
        inline: bool = False,
    ) -> CockpitRun:
        """The paid-run entry point. Fail-closed before any dispatch.

        Requires the *current* ``plan_hash`` (binds the human's approval to the
        exact reviewed plan) and an idempotency key. A repeated key returns the
        same run (no second spend); a different click while a run is active is
        refused by the active-run lock.
        """

        if not idempotency_key or not str(idempotency_key).strip():
            raise CockpitError("a paid run requires an idempotency key")
        key = str(idempotency_key).strip()

        # Stale/mismatched approval is rejected here, before any dispatch.
        try:
            check_approval(self.plan, plan_hash)
        except ApprovalError as exc:
            raise CockpitError(str(exc)) from exc

        with self._lock:
            # Idempotent duplicate click: return the existing run, no new spend.
            existing_id = self._by_idem.get(key)
            if existing_id is not None:
                return self._runs[existing_id]
            # Active-run lock: one paid run at a time (prevents duplicate spend).
            if self._active is not None and not self._active.terminal:
                raise CockpitError(
                    "a run is already active — the active-run lock refuses a "
                    "concurrent paid run"
                )
            pricing = self._load_pricing()
            workload = self._workload()
            if not workload:
                raise CockpitError(
                    f"workload has no prompt-bearing tasks: {self.plan.workload_path}"
                )
            unpriced = self._unpriced_backends(pricing)
            if unpriced:
                raise CockpitError(
                    f"unpriced resolved backend(s) {sorted(unpriced)}: fail closed"
                )
            per_cell = self._per_cell_reservation(pricing, workload)
            # Budget authority proof: the first cell's reservation must fit the cap.
            ledger = SpendLedger.create(self.plan.budget_usd)
            if not ledger.can_afford(per_cell):
                raise CockpitError(
                    "budget reservation refused before dispatch: a single cell's "
                    f"reservation ${per_cell} exceeds budget_usd ${self.plan.budget_usd}"
                )
            # Collision-resistant run id (timestamp + random suffix) so a duplicate
            # click can never collide an output directory.
            run_id = f"{make_run_id()}-{secrets.token_hex(4)}"
            run_dir = self._results_root / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            gate_path = run_dir / "abort.gate.sqlite3"
            run = CockpitRun(
                run_id=run_id,
                run_dir=run_dir,
                plan_hash=self.plan_hash,
                idempotency_key=key,
                ledger=ledger,
                gate_path=gate_path,
                per_cell_reservation=per_cell,
                cells_total=self.plan.planned_cells,
            )
            self._runs[run_id] = run
            self._by_idem[key] = run_id
            self._active = run

        if inline:
            self._run_sweep(run, pricing)
        else:  # pragma: no cover - thread scheduling exercised via inline in tests
            threading.Thread(
                target=self._run_sweep, args=(run, pricing), daemon=True
            ).start()
        return run

    def start_response(self, run: CockpitRun) -> dict[str, Any]:
        """The start payload handed back to the browser. Never claims measured=true."""

        return {
            "run_id": run.run_id,
            "run_dir": str(run.run_dir),
            "state": run.state.value,
            "plan_hash": run.plan_hash,
            "measured": False,
        }

    # -- the sweep (gated by SpendLedger + AbortGate) ----------------------

    def _run_sweep(self, run: CockpitRun, pricing: PricingTable) -> None:
        gate = AbortGate(run.gate_path)
        ledger = run.ledger
        per_cell = run.per_cell_reservation
        try:
            # Building the live client is the authentication step; a failure here
            # (bad token / RBAC) fails the run closed BEFORE any dispatch, with
            # no billable cost and the active-run lock released in ``finally``.
            # An injected factory (tests) stays zero-arg; the live one is handed
            # the plan so the client it builds carries the plan's own request cap,
            # transport cutoffs, and run_mode instead of constructor defaults.
            client = (
                self._client_factory() if self._client_factory is not None
                else _live_client_factory(self.plan)
            )

            def before_cell(cell: CellId) -> str | None:
                # Abort admission first: once cancellation commits, no later cell
                # is admitted (the CAS in gate.admit is the real guard below).
                if gate.terminal() != RUNNING:
                    return "aborted by operator"
                # Reservation-before-dispatch: prove the cap holds, or fail closed.
                reservation = ledger.reserve(per_cell)
                if reservation is None:
                    return "budget reservation refused before dispatch"
                attempt_id = _attempt_id(cell)
                gate.reserve(attempt_id, str(per_cell))
                if not gate.admit(attempt_id):
                    # Abort won the atomic gate between our check and admit.
                    ledger.release_not_billed(reservation)
                    return "aborted by operator"
                run._pending[attempt_id] = reservation
                return None

            def after_cell(cell: CellId, rows: list[dict[str, Any]]) -> None:
                attempt_id = _attempt_id(cell)
                reservation = run._pending.pop(attempt_id, None)
                if reservation is not None:
                    self._settle(ledger, gate, attempt_id, reservation, rows)
                run.cells_done += 1

            result = run_measure(
                self._workload(),
                self._candidates(),
                client=client,
                pricing=pricing,
                exp_id="cockpit",
                run_dir=run.run_dir,
                run_id=run.run_id,
                n=self.plan.repetitions,
                budget_usd=self.plan.budget_usd,
                retry=self._retry or retry_policy_for(self.plan),
                grader=self._grader,
                prereg=self._prereg,
                plan_hash=self.plan_hash,
                hooks=RunHooks(before_cell=before_cell, after_cell=after_cell),
                progress=lambda ev: run.events.append(dict(ev)),
            )
            self._finalize(run, gate, result)
        except Exception as exc:  # a worker exception is a safe terminal 'failed'
            run.state = RunState.FAILED
            run.error = str(exc)
            run.events.append({"event": "failed", "error": str(exc)})
        finally:
            gate.close()
            with self._lock:
                if self._active is run:
                    self._active = None

    @staticmethod
    def _settle(
        ledger: SpendLedger,
        gate: AbortGate,
        attempt_id: str,
        reservation: Any,
        rows: list[dict[str, Any]],
    ) -> None:
        last = rows[-1] if rows else {}
        status = int(last.get("http_status", 0))
        reason = last.get("fail_reason")
        if 200 <= status < 300 and reason is None:
            cost = sum(float(r.get("cost_usd", 0.0)) for r in rows)
            ledger.settle_known(reservation, Decimal(str(cost)))
            gate.settle(attempt_id, RETURNED)
        elif reason in {"timeout", "transport_error"}:
            # Could have left the request in flight: keep the reservation as
            # unreconciled exposure (never silently released).
            ledger.settle_unreconciled(reservation)
            gate.settle(attempt_id, UNKNOWN)
        else:
            # Provider-rejected with a definite status and no derivable usage.
            ledger.release_not_billed(reservation)
            gate.settle(attempt_id, RETURNED)

    def _finalize(self, run: CockpitRun, gate: AbortGate, result: Any) -> None:
        manifest = result.manifest if isinstance(result.manifest, Mapping) else {}
        run.stopped_reason = manifest.get("stopped_reason")
        partial = bool(result.partial)
        aborted = gate.terminal() != RUNNING
        if aborted:
            # Seal any still-in-flight admitted attempt as unreconciled exposure.
            seal_in_flight_as_unreconciled(gate, gate.in_flight_ids())
            run.state = RunState.ABORTED
        elif partial:
            run.state = RunState.PARTIAL
        else:
            outcome = gate.complete()
            run.state = RunState.ABORTED if outcome.status == "aborted_wins" else RunState.COMPLETE
        self._replay_into(run)

    def _replay_into(self, run: CockpitRun) -> None:
        """Derive measured/verified ONLY from a successful snapshot replay."""

        try:
            report = replay_measure(run.run_dir)
        except (OSError, ValueError, KeyError) as exc:
            run.summary_matches = False
            run.measured = False
            # 03Z-b generalization: unverifiable evidence withholds the cost
            # AMOUNT, not merely the savings/measured label.
            run.cost_withheld = True
            run.state = RunState.REPLAY_FAILED
            run.error = f"snapshot replay failed: {exc}"
            return
        run.summary_matches = bool(report.summary_matches)
        recomputed = (
            report.recomputed_summary if isinstance(report.recomputed_summary, Mapping) else {}
        )
        labels = recomputed.get("labels", {}) if isinstance(recomputed, Mapping) else {}
        if report.ok and report.summary_matches:
            run.cost_withheld = False
            if run.state is RunState.COMPLETE:
                run.state = RunState.REPLAY_VERIFIED
                run.measured = bool(labels.get("measured"))
            else:
                # A partial/aborted seal can replay clean (its recorded cost is
                # real and derivable, so it is NOT withheld), but a run that did
                # not COMPLETE is never a complete measurement — never measured.
                run.measured = False
        else:
            run.measured = False
            run.cost_withheld = True
            run.state = RunState.REPLAY_FAILED

    # -- abort / progress / snapshot --------------------------------------

    def abort(self, run_id: str, *, reason: str = "operator") -> dict[str, Any]:
        """Commit cancellation through the shared durable gate (03B AbortGate)."""

        run = self._runs.get(run_id)
        if run is None:
            raise CockpitError(f"unknown run {run_id!r}")
        gate = AbortGate(run.gate_path)
        try:
            outcome = request_cancellation(gate, reason=reason)
        finally:
            gate.close()
        return {
            "run_id": run_id,
            "status": outcome.status,
            "in_flight_ids": list(outcome.in_flight_ids),
            "any_in_flight": outcome.any_in_flight,
        }

    def progress(self, run_id: str) -> dict[str, Any] | None:
        run = self._runs.get(run_id)
        return run.view() if run is not None else None

    def snapshot(self, run_id: str) -> dict[str, Any]:
        """Re-derive the sealed run by replaying it; measured iff the replay holds."""

        run = self._runs.get(run_id)
        if run is None:
            raise CockpitError(f"unknown run {run_id!r}")
        report = replay_measure(run.run_dir)
        verified = bool(report.ok and report.summary_matches)
        summary = (
            report.recomputed_summary if isinstance(report.recomputed_summary, Mapping) else {}
        )
        labels = summary.get("labels", {}) if isinstance(summary, Mapping) else {}
        # measured/verified is claimed ONLY for a run that COMPLETED and whose
        # snapshot still replays clean here (this fresh replay also catches any
        # post-seal tampering).
        measured = bool(
            verified and run.state is RunState.REPLAY_VERIFIED and labels.get("measured")
        )
        return {
            "run": str(run.run_dir),
            "state": run.state.value,
            "ok": report.ok,
            "summary_matches": report.summary_matches,
            "measured": measured,
            # 03Z-b generalization: an unverified snapshot withholds the cost
            # amount itself — never render figures from evidence that did not
            # replay clean.
            "cost_withheld": not verified,
            "summary": dict(summary) if verified else {},
        }


def _live_client_factory(plan: ResolvedRunPlan) -> Any:  # pragma: no cover - live egress
    """Build the live Azure measure client for ``plan``. Only reached on the operator path.

    Every field here comes off the approved plan rather than a constructor
    default, because the default is not neutral: ``max_output_tokens`` falls back
    to 512 (a plan asking for 2048 would silently truncate every completion and
    the truncated answers would still be scored), ``timeouts`` falls back to the
    committed cutoffs (so a plan that pinned its own would not get them), and
    ``benchmark_mode`` falls back to ``False``, which is the one that matters —
    it makes :func:`~router.foundry_live.assert_provider_benchmark_safe` evaluate
    every dispatch as a smoke and lets a scoped-out provider through a measured
    run. See ``tests/test_dispatch_field_parity.py``.
    """

    from .foundry_live import (
        AzureModelRouterClient,
        FoundryConfig,
        TransportTimeouts,
        is_benchmark_run_mode,
    )
    from .measure import AzureMeasureClient

    execution = plan.execution
    return AzureMeasureClient(
        AzureModelRouterClient(
            config=FoundryConfig.from_env(),
            max_output_tokens=int(execution["request"]["max_output_tokens"]),
            timeouts=TransportTimeouts.from_retry(execution.get("retry")),
            benchmark_mode=is_benchmark_run_mode(execution.get("run_mode")),
        )
    )
