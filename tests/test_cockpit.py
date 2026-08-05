"""BOLT-03C — cockpit paid-run state-machine acceptance (§9).

Every test here is network-free: the cockpit drives a scripted fake
:class:`~router.measure.MeasureClient`, so nothing egresses. The suite pins the
§9 acceptance contract — plan-hash parity from preview through the sealed
snapshot, reservation-before-dispatch budget refusal, the shared 03B abort gate,
and the twelve fake end-to-end scenarios — plus the 03Z-b generalization that an
unverified snapshot withholds the cost *amount*, never just the savings label.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from router.abort_gate import AbortGate, request_cancellation
from router.cockpit import CockpitController, CockpitError, RunState
from router.measure import AttemptResult, RetryPolicy
from router.run_plan import LocalRunConfig, resolve_run_plan

ROOT = Path(__file__).resolve().parents[1]
SMOKE_WORKLOAD = ROOT / "samples" / "workloads" / "validated-smoke.example.jsonl"
FAST_RETRY = RetryPolicy(max_retries=3, base_backoff_ms=1.0)


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _rate_card(
    tmp_path: Path, *, models: str | None = None, name: str = "tenant-rates.yaml"
) -> Path:
    if models is None:
        models = (
            "  model-router: {input: 3.0, cached: 1.5, output: 10.0, reasoning: 10.0}\n"
            "  premium-max: {input: 5.0, cached: 2.5, output: 15.0, reasoning: 15.0}\n"
            "  cheap-floor: {input: 0.2, cached: 0.1, output: 0.5, reasoning: 0.5}\n"
        )
    path = tmp_path / name
    path.write_text(
        "version: 7\n"
        "currency: USD\n"
        "source: acme-tenant\n"
        "effective_date: 2026-08-01\n"
        "pricing_basis: composite\n"
        "models:\n"
        f"{models}"
        "default: {input: 1.0, cached: 0.5, output: 2.0, reasoning: 2.0}\n",
        encoding="utf-8",
    )
    return path


def _config_mapping(
    *,
    rate_card: str = "tenant-rates.yaml",
    budget_usd: float = 5.0,
    repetitions: int = 2,
    max_retries: int = 3,
    extra_arms: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    arms = [
        {
            "id": "router-cost",
            "kind": "model_router",
            "provider": "openai",
            "requested_model": "model-router",
            "deployment": "model-router",
            "expected": {"format": "router", "name": "cost", "version": "2025-01"},
        },
        {
            "id": "direct-premium",
            "kind": "direct",
            "provider": "openai",
            "requested_model": "premium-max",
            "deployment": "premium-max",
        },
    ]
    if extra_arms:
        arms.extend(extra_arms)
    return {
        "schema_version": 1,
        "template": False,
        "run_mode": "benchmark",
        "foundry": {
            "auth": "entra",
            "endpoint_kind": "azure_openai",
            "azure_openai_endpoint": "https://acme-res.example.com/",
            "api_version": "2024-10-21",
        },
        "arms": arms,
        "benchmark": {
            "workload": str(SMOKE_WORKLOAD),
            "rate_card": rate_card,
            "smoke_authorization_ceiling_usd": None,
            "repetitions": repetitions,
            "max_output_tokens": 256,
            "budget_usd": budget_usd,
            "random_seed": 7,
            "estimand": {
                "analysis_unit": "task",
                "repeat_aggregation": "mean",
                "denominator_policy": "all-attempted",
                "failure_policy": "count-as-zero",
                "cost_per_pass_formula": "total_cost / passes",
                "paired_statistic": "wilcoxon",
            },
            "grader": {"kind": "exec-signals", "version": 1},
            "retry": {"max_retries": max_retries},
        },
        "privacy": {"retain_raw_prompts": True, "retain_raw_outputs": True},
        "artifacts": {"local_root": "results/local"},
        "display": {"locale": "en"},
    }


def _plan(tmp_path: Path, *, write_card: bool = True, **kwargs: Any):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if write_card:
        _rate_card(tmp_path)
    mapping = _config_mapping(**kwargs)
    config = LocalRunConfig.from_mapping(
        mapping, base_dir=tmp_path, source=str(tmp_path / ".foundry.local.yaml")
    )
    return config, resolve_run_plan(config, env={})


def _controller(tmp_path: Path, client_factory, *, grader=None, **plan_kwargs) -> CockpitController:
    config, plan = _plan(tmp_path, **plan_kwargs)
    return CockpitController(
        plan,
        config,
        client_factory=client_factory,
        results_root=tmp_path / "cockpit",
        retry=FAST_RETRY,
        grader=grader,
    )


# --------------------------------------------------------------------------- #
# Fake clients
# --------------------------------------------------------------------------- #


_USAGE = {"input": 640, "cached": 0, "output": 220, "reasoning": 0}


class OkClient:
    """Always returns a priced 200 with live provenance."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def attempt(self, *, deployment, provider, task) -> AttemptResult:
        self.calls.append((deployment, task["task_id"]))
        return AttemptResult(
            http_status=200, model=deployment, usage=dict(_USAGE),
            latency_ms=10.0, provenance="live",
        )


class StatusClient:
    """Returns a fixed HTTP status (no usage) — models a provider rejection."""

    def __init__(self, status: int) -> None:
        self.status = status
        self.calls = 0

    def attempt(self, *, deployment, provider, task) -> AttemptResult:
        self.calls += 1
        return AttemptResult(http_status=self.status, latency_ms=1.0, provenance="live")


class ThrottleThenOkClient:
    """429s the first ``n`` outbound attempts, then serves priced 200s."""

    def __init__(self, throttles: int) -> None:
        self.remaining = throttles
        self.saw_429 = 0

    def attempt(self, *, deployment, provider, task) -> AttemptResult:
        if self.remaining > 0:
            self.remaining -= 1
            self.saw_429 += 1
            return AttemptResult(http_status=429, latency_ms=1.0, provenance="live")
        return AttemptResult(
            http_status=200, model=deployment, usage=dict(_USAGE),
            latency_ms=10.0, provenance="live",
        )


# --------------------------------------------------------------------------- #
# 1. success smoke → replay-verified + measured (only after replay)
# --------------------------------------------------------------------------- #


def test_scenario_01_success_smoke_measured_only_after_replay(tmp_path):
    client = OkClient()
    ctrl = _controller(tmp_path, lambda: client, budget_usd=50.0)

    # preview + preflight agree on the plan hash before any dispatch.
    assert ctrl.preview()["plan_hash"] == ctrl.plan_hash
    assert ctrl.preflight()["plan_hash"] == ctrl.plan_hash

    run = ctrl.approve_and_start(
        plan_hash=ctrl.plan_hash, idempotency_key="click-1", inline=True
    )
    # The start payload never claims measured=true.
    assert ctrl.start_response(run)["measured"] is False

    assert run.state is RunState.REPLAY_VERIFIED
    assert run.measured is True
    assert run.cost_withheld is False
    assert run.summary_matches is True
    assert run.cells_done == run.cells_total == ctrl.plan.planned_cells
    assert float(run.ledger.known_derived_total) > 0.0

    snap = ctrl.snapshot(run.run_id)
    assert snap["measured"] is True and snap["ok"] is True
    assert snap["cost_withheld"] is False and snap["summary"]


# --------------------------------------------------------------------------- #
# 2. auth failure before inference → fail closed, nothing billed
# --------------------------------------------------------------------------- #


def test_scenario_02_auth_failure_before_inference(tmp_path):
    def factory():
        raise RuntimeError("401 Unauthorized: Entra token/RBAC rejected")

    ctrl = _controller(tmp_path, factory, budget_usd=50.0)
    run = ctrl.approve_and_start(
        plan_hash=ctrl.plan_hash, idempotency_key="k", inline=True
    )
    assert run.state is RunState.FAILED
    assert "401" in (run.error or "")
    assert run.measured is False
    assert float(run.ledger.known_derived_total) == 0.0  # no billable dispatch
    assert run.cells_done == 0
    # The active-run lock is released even though the run failed.
    assert ctrl._active is None


# --------------------------------------------------------------------------- #
# 3. 429 then retry → run still completes measured; attempts shown as a range
# --------------------------------------------------------------------------- #


def test_scenario_03_throttle_then_retry_completes(tmp_path):
    client = ThrottleThenOkClient(throttles=2)
    ctrl = _controller(tmp_path, lambda: client, budget_usd=50.0, max_retries=3)

    preview = ctrl.preview()
    # A retryable call is shown as base..max attempts, never "exactly N".
    assert preview["base_transport_attempts"] == 1
    assert preview["max_transport_attempts"] == 1 + 3

    run = ctrl.approve_and_start(
        plan_hash=ctrl.plan_hash, idempotency_key="k", inline=True
    )
    assert run.state is RunState.REPLAY_VERIFIED
    assert run.measured is True
    assert client.saw_429 == 2
    # The throttled attempts are recorded in the sealed trace, not hidden.
    traces = (run.run_dir / "traces.jsonl").read_text(encoding="utf-8")
    assert any(json.loads(line).get("http_status") == 429 for line in traces.splitlines())


# --------------------------------------------------------------------------- #
# 4. provider terminal failure → sealed but not measured, no cost claimed
# --------------------------------------------------------------------------- #


def test_scenario_04_provider_terminal_failure_not_measured(tmp_path):
    client = StatusClient(status=500)
    ctrl = _controller(tmp_path, lambda: client, budget_usd=50.0, max_retries=1)

    run = ctrl.approve_and_start(
        plan_hash=ctrl.plan_hash, idempotency_key="k", inline=True
    )
    # Every cell exhausted its retries with a 5xx: nothing measured, nothing billed.
    assert run.measured is False
    assert float(run.ledger.known_derived_total) == 0.0
    snap = ctrl.snapshot(run.run_id)
    assert snap["measured"] is False


# --------------------------------------------------------------------------- #
# 5. grader failure → fails closed, never a fake measured pass
# --------------------------------------------------------------------------- #


def test_scenario_05_grader_failure_fails_closed(tmp_path):
    def grader(task_id, task, model, usage):
        raise RuntimeError("grader harness crashed")

    ctrl = _controller(tmp_path, OkClient, grader=grader, budget_usd=50.0)
    run = ctrl.approve_and_start(
        plan_hash=ctrl.plan_hash, idempotency_key="k", inline=True
    )
    # A grader crash is surfaced as a failed run — never silently a measured pass.
    assert run.state is RunState.FAILED
    assert run.measured is False
    assert "grader" in (run.error or "")


# --------------------------------------------------------------------------- #
# 6. stale plan approval → refused before any dispatch
# --------------------------------------------------------------------------- #


def test_scenario_06_stale_plan_approval_refused(tmp_path):
    ctrl = _controller(tmp_path, OkClient, budget_usd=50.0)
    stale = "sha256:" + "0" * 64
    with pytest.raises(CockpitError):
        ctrl.approve_and_start(plan_hash=stale, idempotency_key="k", inline=True)
    # No run was created and no lock was taken.
    assert ctrl._active is None
    assert ctrl._runs == {}


# --------------------------------------------------------------------------- #
# 7. duplicate click → idempotent (same run, no second spend); active-run lock
# --------------------------------------------------------------------------- #


def test_scenario_07_duplicate_click_idempotent_and_locked(tmp_path):
    ctrl = _controller(tmp_path, OkClient, budget_usd=50.0)
    run1 = ctrl.approve_and_start(
        plan_hash=ctrl.plan_hash, idempotency_key="same", inline=True
    )
    spend = float(run1.ledger.known_derived_total)
    # Same idempotency key returns the very same run — no second sweep, no re-spend.
    run2 = ctrl.approve_and_start(
        plan_hash=ctrl.plan_hash, idempotency_key="same", inline=True
    )
    assert run2.run_id == run1.run_id
    assert len(ctrl._runs) == 1
    assert float(run2.ledger.known_derived_total) == spend


def test_scenario_07b_active_run_lock_refuses_concurrent(tmp_path):
    # A duplicate click *while a run is active* (a different key) is refused by
    # the active-run lock. Drive it by re-entering start from inside a cell.
    holder: dict[str, Any] = {}

    class ReentrantClient:
        def __init__(self) -> None:
            self.tried = False

        def attempt(self, *, deployment, provider, task) -> AttemptResult:
            if not self.tried:
                self.tried = True
                try:
                    holder["ctrl"].approve_and_start(
                        plan_hash=holder["ctrl"].plan_hash,
                        idempotency_key="second-click",
                        inline=True,
                    )
                except CockpitError as exc:
                    holder["refused"] = str(exc)
            return AttemptResult(
                http_status=200, model=deployment, usage=dict(_USAGE),
                latency_ms=10.0, provenance="live",
            )

    client = ReentrantClient()
    ctrl = _controller(tmp_path, lambda: client, budget_usd=50.0)
    holder["ctrl"] = ctrl
    run = ctrl.approve_and_start(
        plan_hash=ctrl.plan_hash, idempotency_key="first-click", inline=True
    )
    assert run.state is RunState.REPLAY_VERIFIED
    assert "active-run lock" in holder.get("refused", "")


# --------------------------------------------------------------------------- #
# 8. budget reservation refusal → reserved before dispatch, never overspends
# --------------------------------------------------------------------------- #


def test_scenario_08_budget_reservation_refused_before_dispatch(tmp_path):
    client = OkClient()
    # A budget that admits the first cell's reservation but cannot fund the sweep.
    ctrl = _controller(tmp_path, lambda: client, budget_usd=0.02)

    run = ctrl.approve_and_start(
        plan_hash=ctrl.plan_hash, idempotency_key="k", inline=True
    )
    assert run.state is RunState.PARTIAL
    assert "budget reservation refused" in (run.stopped_reason or "")
    assert run.cells_done < run.cells_total
    # The reservation gate is the authority: known spend never crosses the cap.
    assert float(run.ledger.known_derived_total) <= ctrl.plan.budget_usd
    # A partial run is not a complete measurement.
    assert run.measured is False


# --------------------------------------------------------------------------- #
# 9. unpriced resolved backend → fail closed (never price off the default)
# --------------------------------------------------------------------------- #


def test_scenario_09_unpriced_backend_fails_closed(tmp_path):
    # A rate card that omits premium-max: that arm's backend has no explicit rate.
    _rate_card(
        tmp_path,
        models="  model-router: {input: 3.0, cached: 1.5, output: 10.0, reasoning: 10.0}\n",
    )
    mapping = _config_mapping(budget_usd=50.0)
    config = LocalRunConfig.from_mapping(
        mapping, base_dir=tmp_path, source=str(tmp_path / ".foundry.local.yaml")
    )
    plan = resolve_run_plan(config, env={})
    ctrl = CockpitController(
        plan, config, client_factory=OkClient, results_root=tmp_path / "cockpit",
        retry=FAST_RETRY,
    )
    # Preflight fails closed rather than pricing premium-max off the generic default.
    with pytest.raises(CockpitError) as exc:
        ctrl.preflight()
    assert "unpriced" in str(exc.value)
    # And the paid entry point refuses too, before any dispatch.
    with pytest.raises(CockpitError):
        ctrl.approve_and_start(plan_hash=plan.plan_hash, idempotency_key="k", inline=True)


# --------------------------------------------------------------------------- #
# 10. replay tamper → withhold the cost amount, not just the label (03Z-b)
# --------------------------------------------------------------------------- #


def test_scenario_10_replay_tamper_withholds_cost(tmp_path):
    client = OkClient()
    ctrl = _controller(tmp_path, lambda: client, budget_usd=50.0)
    run = ctrl.approve_and_start(
        plan_hash=ctrl.plan_hash, idempotency_key="k", inline=True
    )
    assert run.state is RunState.REPLAY_VERIFIED and run.measured is True

    # Tamper the sealed snapshot after the fact.
    summary_path = run.run_dir / "summary.json"
    doc = json.loads(summary_path.read_text(encoding="utf-8"))
    doc["totals"] = {"tampered": True}
    summary_path.write_text(json.dumps(doc), encoding="utf-8")

    snap = ctrl.snapshot(run.run_id)
    assert snap["ok"] is False
    assert snap["measured"] is False
    # 03Z-b generalization: the amount itself is withheld, not just the savings.
    assert snap["cost_withheld"] is True
    assert snap["summary"] == {}


# --------------------------------------------------------------------------- #
# 11. abort mid-run → aborted + sealed partial; completed cells' cost retained
# --------------------------------------------------------------------------- #


def test_scenario_11_abort_mid_run(tmp_path):
    holder: dict[str, Any] = {}

    class AbortingClient:
        def __init__(self) -> None:
            self.n = 0

        def attempt(self, *, deployment, provider, task) -> AttemptResult:
            self.n += 1
            if self.n == 3:
                holder["abort"] = holder["ctrl"].abort(holder["ctrl"]._active.run_id)
            return AttemptResult(
                http_status=200, model=deployment, usage=dict(_USAGE),
                latency_ms=10.0, provenance="live",
            )

    client = AbortingClient()
    ctrl = _controller(tmp_path, lambda: client, budget_usd=50.0)
    holder["ctrl"] = ctrl
    run = ctrl.approve_and_start(
        plan_hash=ctrl.plan_hash, idempotency_key="k", inline=True
    )
    assert run.state is RunState.ABORTED
    assert run.cells_done < run.cells_total
    assert "aborted" in (run.stopped_reason or "")
    # An aborted run is never a complete measurement...
    assert run.measured is False
    # ...but the cells that DID complete have real, replayable cost (not withheld).
    assert float(run.ledger.known_derived_total) > 0.0
    assert run.cost_withheld is False
    assert run.abort_available is False


# --------------------------------------------------------------------------- #
# 12. abort/completion race + repeated abort + SIGINT (shared durable gate)
# --------------------------------------------------------------------------- #


def test_scenario_12_abort_completion_race_repeated_and_sigint(tmp_path):
    # (a) abort-after-completion race: completion committed first, so a late
    #     abort loses and the verified run is unchanged.
    ctrl = _controller(tmp_path, OkClient, budget_usd=50.0)
    run = ctrl.approve_and_start(
        plan_hash=ctrl.plan_hash, idempotency_key="k", inline=True
    )
    assert run.state is RunState.REPLAY_VERIFIED and run.measured is True
    late = ctrl.abort(run.run_id)
    assert late["status"] == "already_terminal"
    assert run.state is RunState.REPLAY_VERIFIED and run.measured is True

    # (b) repeated abort is idempotent — still terminal, no crash, no re-spend.
    again = ctrl.abort(run.run_id)
    assert again["status"] == "already_terminal"

    # (c) SIGINT routes through the SAME durable gate the cockpit reads: a mid-run
    #     interrupt (the SIGINT handler calls request_cancellation on the gate)
    #     halts the sweep and seals it aborted.
    holder: dict[str, Any] = {}

    class SigintClient:
        def __init__(self) -> None:
            self.n = 0

        def attempt(self, *, deployment, provider, task) -> AttemptResult:
            self.n += 1
            if self.n == 2:
                gate = AbortGate(holder["ctrl"]._active.gate_path)
                try:
                    request_cancellation(gate, reason="sigint")
                finally:
                    gate.close()
            return AttemptResult(
                http_status=200, model=deployment, usage=dict(_USAGE),
                latency_ms=10.0, provenance="live",
            )

    client = SigintClient()
    ctrl2 = _controller(tmp_path / "sig", lambda: client, budget_usd=50.0)
    holder["ctrl"] = ctrl2
    run2 = ctrl2.approve_and_start(
        plan_hash=ctrl2.plan_hash, idempotency_key="k", inline=True
    )
    assert run2.state is RunState.ABORTED
    assert run2.cells_done < run2.cells_total
