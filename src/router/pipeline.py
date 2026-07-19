"""High-level offline routing flows shared by the CLI, sample scripts, and evals.

Every entry point (``cost-router`` subcommands, ``samples/python/*.py``, and
``evals/run.py``) funnels through these helpers so the orchestration and output
formatting live in exactly one place.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from policy import (
    PolicyTable,
    TaskClass,
    describe_model,
    diff_policies,
    format_diff,
    load_default_policy,
)

from .arena import bundled_head_to_head
from .baseline import (
    baseline_cost_usd,
    baseline_model_for_task,
    ensemble_all_summary,
    model_router_summary,
    single_call_baseline_arms,
    single_tier_summary,
)
from .budget import BudgetGate
from .classify import classify_task
from .ledger import (
    JsonlLedger,
    build_ledger_record,
    require_valid_records,
    verify_ledger,
    verify_records,
)
from .metrics import fanout_stats
from .offline import (
    load_signal_fixture,
    load_task_prompts,
    load_workload,
    route_task,
    route_tasks,
    summarize_traces,
    synthesize_shared_signals,
    synthesize_signals,
    synthesize_task_signals,
)
from .pricing import PricingTable
from .profile import stratify_traces
from .spotlight import select_spotlight

DEFAULT_WORKLOAD = Path("samples/telemetry/mixed-coding-workload.sample.jsonl")
DEFAULT_SIGNALS = Path("samples/responses/routing-signals.sample.json")
DEFAULT_PRICING = Path("samples/pricing/illustrative.yaml")
DEFAULT_PROMPTS = Path("samples/prompts/curated-arena.sample.json")
ENSEMBLE_SIGNALS = Path("samples/responses/ensemble-fanout-signals.sample.json")
FANOUT_SWEEP_THRESHOLDS: tuple[float, ...] = (0.0, 0.76, 0.86, 1.01)
POLICY_ENV_VAR = "COST_ROUTER_POLICY"


@dataclass(frozen=True)
class ReplayReport:
    """Routed traces plus their aggregate summary."""

    traces: list[dict[str, Any]]
    summary: dict[str, Any]


def find_samples_root(start: Path | str | None = None) -> Path:
    """Walk up from ``start`` (default CWD) to the repo root that holds samples."""

    base = Path(start).resolve() if start is not None else Path.cwd().resolve()
    for candidate in (base, *base.parents):
        if (candidate / DEFAULT_WORKLOAD).is_file():
            return candidate
    return base


def resolve_paths(
    *,
    workload: Path | str | None = None,
    signals: Path | str | None = None,
    pricing: Path | str | None = None,
    root: Path | str | None = None,
) -> dict[str, Path]:
    """Resolve workload/signals/pricing paths, filling blanks from the samples root."""

    base = find_samples_root(root)
    return {
        "workload": Path(workload) if workload is not None else base / DEFAULT_WORKLOAD,
        "signals": Path(signals) if signals is not None else base / DEFAULT_SIGNALS,
        "pricing": Path(pricing) if pricing is not None else base / DEFAULT_PRICING,
    }


def load_default_pricing(root: Path | str | None = None) -> PricingTable:
    """Load the bundled illustrative pricing table (offline sample data)."""

    return PricingTable.from_yaml(resolve_paths(root=root)["pricing"])


def resolve_policy_path(policy: Path | str | None = None) -> Path | None:
    """Resolve the policy source with precedence: CLI arg > env var > bundled.

    Returns ``None`` when neither an explicit path nor ``COST_ROUTER_POLICY`` is
    set, signalling that the bundled seed policy should be used.
    """

    if policy is not None:
        return Path(policy)
    env_value = os.environ.get(POLICY_ENV_VAR)
    if env_value:
        return Path(env_value)
    return None


def load_policy(policy: Path | str | None = None) -> PolicyTable:
    """Load and validate a policy, honouring the CLI > env > bundled precedence."""

    path = resolve_policy_path(policy)
    if path is None:
        return load_default_policy()
    return PolicyTable.from_yaml(path).validate()


def policy_summary(policy: PolicyTable | None = None) -> dict[str, Any]:
    """Summarize a policy as version + ordered candidates per task class.

    Each candidate is enriched with its catalog ``tier``/``reasoning``/``role``
    (a vendor-neutral description of what the placeholder represents), and a
    deduplicated ``catalog`` of the models the policy actually uses is included
    so consumers can render a legend without re-deriving it.
    """

    policy = policy or load_default_policy()
    classes = {
        task_class.value: [
            {
                "model": candidate.model,
                "rank": rank,
                "prior_pass": candidate.prior_pass,
                "prior_usd_resolved": candidate.prior_usd_resolved,
                **{k: v for k, v in describe_model(candidate.model).items() if k != "model"},
            }
            for rank, candidate in enumerate(policy.candidates_for(task_class))
        ]
        for task_class in TaskClass
    }
    used_models: dict[str, float] = {}
    for candidates in policy.classes.values():
        for candidate in candidates:
            prior = candidate.prior_usd_resolved
            if candidate.model not in used_models or prior < used_models[candidate.model]:
                used_models[candidate.model] = prior
    catalog = [
        describe_model(model)
        for model in sorted(used_models, key=lambda m: used_models[m])
    ]
    return {"version": policy.version, "classes": classes, "catalog": catalog}


def route_payload(
    task: Mapping[str, Any],
    *,
    signals: Mapping[str, Mapping[str, Any]] | None = None,
    synth: bool = False,
    policy: PolicyTable | None = None,
    pricing: PricingTable | None = None,
) -> dict[str, Any]:
    """Route a single in-memory task payload and return its trace.

    When ``synth`` is true or no ``signals`` are supplied, deterministic offline
    check signals are synthesized for the task's policy candidates.
    """

    policy = policy or load_default_policy()
    if synth or signals is None:
        candidates = policy.candidates_for(classify_task(task))
        signals = synthesize_task_signals(task, candidates)
    return route_task(task, signals, policy=policy, pricing=pricing)


def batch_route_payload(
    tasks: Sequence[Mapping[str, Any]],
    *,
    signals_by_task: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
    synth: bool = False,
    policy: PolicyTable | None = None,
    pricing: PricingTable | None = None,
) -> dict[str, Any]:
    """Route many in-memory task payloads deterministically and summarize them."""

    policy = policy or load_default_policy()
    traces: list[dict[str, Any]] = []
    for task in tasks:
        task_signals = None
        if not synth and signals_by_task is not None:
            task_signals = signals_by_task.get(str(task.get("task_id")))
        traces.append(
            route_payload(
                task,
                signals=task_signals,
                synth=synth,
                policy=policy,
                pricing=pricing,
            )
        )
    return {"traces": traces, "summary": summarize_traces(traces)}


def _load_context(
    *,
    workload_path: Path | str,
    pricing_path: Path | str,
    policy_path: Path | str | None = None,
) -> tuple[PolicyTable, dict[str, dict[str, Any]], PricingTable]:
    policy = load_policy(policy_path)
    workload = load_workload(workload_path)
    pricing = PricingTable.from_yaml(pricing_path)
    return policy, workload, pricing


def _signals_for(
    *,
    synth: bool,
    workload: dict[str, dict[str, Any]],
    policy: PolicyTable,
    signals_path: Path | str | None,
) -> dict[str, Any]:
    if synth:
        return synthesize_signals(workload, policy)
    if signals_path is None:
        raise ValueError("signals_path is required when synth is False")
    return load_signal_fixture(signals_path)


def run_replay(
    *,
    workload_path: Path | str,
    pricing_path: Path | str,
    signals_path: Path | str | None = None,
    synth: bool = False,
    policy_path: Path | str | None = None,
    ledger_path: Path | str | None = None,
    budget_gate: BudgetGate | None = None,
) -> ReplayReport:
    """Route every task that has signals and return traces plus a summary."""

    policy, workload, pricing = _load_context(
        workload_path=workload_path, pricing_path=pricing_path, policy_path=policy_path
    )
    signals = _signals_for(
        synth=synth, workload=workload, policy=policy, signals_path=signals_path
    )
    return _replay_report(
        workload,
        signals,
        policy=policy,
        pricing=pricing,
        ledger_path=ledger_path,
        signal_kind="synth" if synth else "fixture",
        budget_gate=budget_gate,
    )


def run_bundled_replay(
    *,
    policy: PolicyTable | None = None,
    synth: bool = False,
    root: Path | str | None = None,
    ledger_path: Path | str | None = None,
    budget_gate: BudgetGate | None = None,
) -> ReplayReport:
    """Replay the bundled sample workload with an in-memory policy.

    Shares the exact routing/summary path as :func:`run_replay` but sources the
    workload, signals, and pricing from the checked-in samples so an already
    loaded policy (e.g. a running service's injected policy) can be reused
    without touching a policy file again. Offline and deterministic.
    """

    policy = policy or load_default_policy()
    paths = resolve_paths(root=root)
    workload = load_workload(paths["workload"])
    pricing = PricingTable.from_yaml(paths["pricing"])
    signals = _signals_for(
        synth=synth,
        workload=workload,
        policy=policy,
        signals_path=None if synth else paths["signals"],
    )
    return _replay_report(
        workload,
        signals,
        policy=policy,
        pricing=pricing,
        ledger_path=ledger_path,
        signal_kind="synth" if synth else "fixture",
        budget_gate=budget_gate,
    )


def _replay_report(
    workload: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Any],
    *,
    policy: PolicyTable,
    pricing: PricingTable,
    ledger_path: Path | str | None = None,
    signal_kind: str = "fixture",
    budget_gate: BudgetGate | None = None,
) -> ReplayReport:
    """Route the signalled tasks and attach the naive-vs-routed before/after."""

    traces = route_tasks(
        workload, signals, policy=policy, pricing=pricing, budget_gate=budget_gate
    )
    summary = summarize_traces(traces)
    routed_tasks = {task_id: workload[task_id] for task_id in signals if task_id in workload}
    baseline = baseline_cost_usd(routed_tasks, policy, pricing)
    delta = round(baseline - summary["total_cost_usd"], 6)
    summary["baseline_total_usd"] = baseline
    summary["delta_usd"] = delta
    summary["delta_pct"] = (delta / baseline) if baseline else 0.0
    summary["measured"] = False
    summary["breakdown"] = aggregate_replay(traces, routed_tasks, policy=policy, pricing=pricing)
    summary["baseline_arms"] = single_call_baseline_arms(
        routed_tasks,
        signals,
        policy,
        pricing,
    )
    summary["strata"] = stratify_traces(traces)
    summary["strategies"] = _strategy_comparison(
        routed_tasks, signals, summary, policy=policy, pricing=pricing
    )
    summary["fanout"] = fanout_stats(traces)
    summary["escalated_tasks"] = _count_escalated(traces)
    spotlight = select_spotlight(traces, pricing, "auto")
    summary["spotlight"] = spotlight.to_dict() if spotlight else None
    if ledger_path is not None:
        summary["ledger"] = _append_ledger(
            ledger_path=ledger_path,
            workload=routed_tasks,
            signals=signals,
            traces=traces,
            policy=policy,
            pricing=pricing,
            signal_kind=signal_kind,
        )
    return ReplayReport(traces=traces, summary=summary)


def _strategy_comparison(
    routed_tasks: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Any],
    summary: Mapping[str, Any],
    *,
    policy: PolicyTable,
    pricing: PricingTable,
) -> dict[str, dict[str, float]]:
    """Cost + coverage for all-mini, all-premium, ensemble, model-router, mix.

    all-mini/all-premium reuse :func:`single_tier_summary`; ensemble fans out to
    every model; ``model_router`` is a difficulty-tiered single-call pick (one
    model per prompt, no escalation — the shape of a managed model router); the
    mix is the routed result already in ``summary``. Together they surface the
    trade-off: cheapest-only loses coverage, premium/ensemble hold coverage but
    cost the most, a single-call router commits up front, and only the
    observe-then-escalate mix wins on both cost and coverage.
    """

    mini = single_tier_summary(routed_tasks, signals, policy, pricing, cheapest=True)
    premium = single_tier_summary(routed_tasks, signals, policy, pricing, cheapest=False)
    ensemble = ensemble_all_summary(routed_tasks, signals, policy, pricing)
    router = model_router_summary(routed_tasks, signals, policy, pricing)
    return {
        "all_mini": {
            "total_cost_usd": mini["total_cost_usd"],
            "coverage": mini["coverage"],
        },
        "all_premium": {
            "total_cost_usd": premium["total_cost_usd"],
            "coverage": premium["coverage"],
        },
        "all_ensemble": {
            "total_cost_usd": ensemble["total_cost_usd"],
            "coverage": ensemble["coverage"],
        },
        "model_router": {
            "total_cost_usd": router["total_cost_usd"],
            "coverage": router["coverage"],
            "selection": router["selection"],
            "model_counts": router["model_counts"],
            "labels": router["labels"],
        },
        "mix": {
            "total_cost_usd": summary["total_cost_usd"],
            "coverage": summary["coverage"],
        },
    }


def _count_escalated(traces: Sequence[Mapping[str, Any]]) -> int:
    """Count tasks routed to a tier above the cheapest candidate for their class."""

    escalated = 0
    for trace in traces:
        candidates = trace.get("candidates") or []
        if not candidates:
            continue
        cheapest = min(candidates, key=lambda item: item.get("prior_usd_resolved", 0.0))
        chosen = trace.get("chosen")
        if chosen and chosen != cheapest.get("model"):
            escalated += 1
    return escalated


def aggregate_replay(
    traces: Sequence[Mapping[str, Any]],
    routed_tasks: Mapping[str, Mapping[str, Any]],
    *,
    policy: PolicyTable,
    pricing: PricingTable,
) -> dict[str, Any]:
    """Aggregate routed traces for dashboard-style statistics.

    Returns per-class (routed vs naive-baseline cost + savings), per-chosen-model
    (task count, routed cost), and per-mode/per-reason tallies. Deterministic and
    derived only from the given traces/tasks — no re-routing.
    """

    by_class: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    mode_cost: dict[str, float] = {}
    reason_counts: dict[str, int] = {}
    for trace in traces:
        cls = str(trace.get("class"))
        model = str(trace.get("chosen"))
        mode = str(trace.get("mode"))
        reason = str(trace.get("reason"))
        cost = float(trace.get("cost_usd") or 0.0)
        cbucket = by_class.setdefault(
            cls, {"tasks": 0, "routed_usd": 0.0, "baseline_usd": 0.0}
        )
        cbucket["tasks"] += 1
        cbucket["routed_usd"] = round(cbucket["routed_usd"] + cost, 6)
        mbucket = by_model.setdefault(model, {"tasks": 0, "routed_usd": 0.0})
        mbucket["tasks"] += 1
        mbucket["routed_usd"] = round(mbucket["routed_usd"] + cost, 6)
        mode_cost[mode] = round(mode_cost.get(mode, 0.0) + cost, 6)
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    for task in routed_tasks.values():
        cls = classify_task(task)
        model = baseline_model_for_task(task, policy)
        cost = pricing.cost_usd(model, task.get("tokens", {})) if pricing else 0.0
        cbucket = by_class.setdefault(
            cls, {"tasks": 0, "routed_usd": 0.0, "baseline_usd": 0.0}
        )
        cbucket["baseline_usd"] = round(cbucket["baseline_usd"] + (cost or 0.0), 6)

    for cbucket in by_class.values():
        saved = round(cbucket["baseline_usd"] - cbucket["routed_usd"], 6)
        cbucket["saved_usd"] = saved
        cbucket["saved_pct"] = (saved / cbucket["baseline_usd"]) if cbucket["baseline_usd"] else 0.0

    return {
        "by_class": by_class,
        "by_model": by_model,
        "mode_cost_usd": mode_cost,
        "reason_counts": reason_counts,
    }


def run_route_once(
    *,
    task_id: str,
    workload_path: Path | str,
    pricing_path: Path | str,
    signals_path: Path | str | None = None,
    synth: bool = False,
    policy_path: Path | str | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Route a single task and return its trace."""

    policy, workload, pricing = _load_context(
        workload_path=workload_path, pricing_path=pricing_path, policy_path=policy_path
    )
    if task_id not in workload:
        raise KeyError(f"unknown task id: {task_id}")
    signals = _signals_for(
        synth=synth, workload=workload, policy=policy, signals_path=signals_path
    )
    if task_id not in signals:
        raise KeyError(f"no sample signals for task id: {task_id}")
    trace = route_task(workload[task_id], signals[task_id], policy=policy, pricing=pricing)
    if ledger_path is not None:
        _append_ledger(
            ledger_path=ledger_path,
            workload={task_id: workload[task_id]},
            signals={task_id: signals[task_id]},
            traces=[trace],
            policy=policy,
            pricing=pricing,
            signal_kind="synth" if synth else "fixture",
        )
    return trace


def _eval_traces(
    *,
    policy: PolicyTable,
    workload: dict[str, dict[str, Any]],
    pricing: PricingTable,
    signals: dict[str, Any],
) -> dict[str, Any]:
    selected = {task_id: workload[task_id] for task_id in signals}
    traces = route_tasks(selected, signals, policy=policy, pricing=pricing)
    routed = summarize_traces(traces)
    baseline = baseline_cost_usd(selected, policy, pricing)
    delta = round(baseline - routed["total_cost_usd"], 6)
    delta_pct = (delta / baseline) if baseline else 0.0
    return {
        "tasks": routed["tasks"],
        "accepted": routed["accepted"],
        "coverage": routed["coverage"],
        "routed_total_usd": routed["total_cost_usd"],
        "baseline_total_usd": baseline,
        "delta_usd": delta,
        "delta_pct": delta_pct,
        "mode_counts": routed["mode_counts"],
        "reason_counts": routed["reason_counts"],
        "by_class": summarize_by_class(traces),
        "baseline_arms": single_call_baseline_arms(selected, signals, policy, pricing),
        "strata": stratify_traces(traces),
    }


def _append_ledger(
    *,
    ledger_path: Path | str,
    workload: Mapping[str, Mapping[str, Any]],
    signals: Mapping[str, Any],
    traces: Sequence[Mapping[str, Any]],
    policy: PolicyTable,
    pricing: PricingTable,
    signal_kind: str,
) -> dict[str, Any]:
    """Build, verify, append, then re-verify a batch of ledger records."""

    records = []
    for trace in traces:
        task_id = str(trace.get("task_id"))
        if task_id not in workload or task_id not in signals:
            raise ValueError(f"cannot record ledger entry for unknown task {task_id!r}")
        records.append(
            build_ledger_record(
                task=workload[task_id],
                signals_by_model=signals[task_id],
                trace=trace,
                policy=policy,
                pricing=pricing,
                signal_kind=signal_kind,
            )
        )
    batch_report = verify_records(records)
    if not batch_report.ok:
        raise ValueError("ledger batch failed deterministic replay before append")
    store = JsonlLedger(ledger_path)
    appended = store.append_many(records, validator=require_valid_records)
    full_report = verify_ledger(ledger_path)
    if not full_report.ok:
        raise ValueError("ledger failed deterministic replay after append")
    return {
        "path": str(Path(ledger_path)),
        "appended": len(appended),
        **full_report.to_dict(),
    }


def run_evals(
    *,
    workload_path: Path | str,
    pricing_path: Path | str,
    signals_path: Path | str | None = None,
    synth: bool = False,
    policy_path: Path | str | None = None,
) -> dict[str, Any]:
    """Summarize routed cost/coverage against the always-most-expensive baseline."""

    policy, workload, pricing = _load_context(
        workload_path=workload_path, pricing_path=pricing_path, policy_path=policy_path
    )
    signals = _signals_for(
        synth=synth, workload=workload, policy=policy, signals_path=signals_path
    )
    return _eval_traces(policy=policy, workload=workload, pricing=pricing, signals=signals)


def summarize_by_class(traces: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group traces by task class with count/accepted/cost per class."""

    out: dict[str, dict[str, Any]] = {}
    for trace in traces:
        cls = str(trace.get("class"))
        bucket = out.setdefault(cls, {"tasks": 0, "accepted": 0, "cost_usd": 0.0})
        bucket["tasks"] += 1
        bucket["accepted"] += 1 if _trace_accepted(trace) else 0
        bucket["cost_usd"] = round(bucket["cost_usd"] + _cost(trace), 6)
    return out


def _trace_accepted(trace: dict[str, Any]) -> bool:
    chosen = trace.get("chosen")
    for attempt in trace.get("attempts", []):
        if attempt.get("model") == chosen:
            return bool(attempt.get("accepted"))
    return False


def regression_report(
    *,
    workload_path: Path | str,
    pricing_path: Path | str,
    candidate_policy_path: Path | str,
    base_policy_path: Path | str | None = None,
    signals_path: Path | str | None = None,
    synth: bool = False,
) -> dict[str, Any]:
    """Compare a candidate policy against a base policy on the same workload.

    Both policies route the identical workload, pricing, and a single shared set
    of evaluation signals, so the deltas isolate the routing change alone. With
    ``synth=True`` the shared signals are synthesized once from the *union* of
    both policies' candidates (base-preferred priors, union fallback forced
    clean); with ``synth=False`` both policies read the same checked-in fixture.
    The result is deterministic for a given workload and ``synth``.
    """

    workload = load_workload(workload_path)
    pricing = PricingTable.from_yaml(pricing_path)
    base = load_policy(base_policy_path)
    candidate = PolicyTable.from_yaml(candidate_policy_path).validate()
    if synth:
        signals = synthesize_shared_signals(workload, base, candidate)
        signal_kind = "shared-synth"
    else:
        if signals_path is None:
            raise ValueError("signals_path is required when synth is False")
        signals = load_signal_fixture(signals_path)
        signal_kind = "fixture"
    base_eval = _eval_traces(policy=base, workload=workload, pricing=pricing, signals=signals)
    cand_eval = _eval_traces(policy=candidate, workload=workload, pricing=pricing, signals=signals)
    return {
        "base": base_eval,
        "candidate": cand_eval,
        "cost_delta_usd": round(cand_eval["routed_total_usd"] - base_eval["routed_total_usd"], 6),
        "coverage_delta": round(cand_eval["coverage"] - base_eval["coverage"], 6),
        "diff": format_diff(diff_policies(base, candidate)),
        "evaluation": {"signals": signal_kind, "tasks": len(signals)},
    }


# The bundled candidate policy that naively deletes expensive fallbacks. Compared
# against the seed policy it exposes the coverage cliff (see lab notebook 03).
COVERAGE_CLIFF_CANDIDATE = Path("experiments/policies/cost-cut.yaml")


def bundled_coverage_cliff(
    root: Path | str | None = None,
    *,
    candidate_policy: Path | str = COVERAGE_CLIFF_CANDIDATE,
) -> dict[str, Any]:
    """Compact seed-vs-candidate coverage-cliff view for the dashboard.

    Runs the deterministic policy regression (bundled seed policy vs the naive
    ``cost-cut`` candidate over shared synthetic signals) and trims it to the few
    fields the dashboard renders: each arm's coverage and routed cost, plus the
    coverage/cost deltas. Offline and deterministic; ``measured = false``.
    """

    base = find_samples_root(root)
    candidate_path = Path(candidate_policy)
    if not candidate_path.is_absolute():
        candidate_path = base / candidate_path
    report = regression_report(
        workload_path=base / DEFAULT_WORKLOAD,
        pricing_path=base / DEFAULT_PRICING,
        candidate_policy_path=candidate_path,
        base_policy_path=None,
        synth=True,
    )
    return {
        "base": {
            "label": "seed policy",
            "coverage": report["base"]["coverage"],
            "routed_total_usd": report["base"]["routed_total_usd"],
            "tasks": report["base"]["tasks"],
        },
        "candidate": {
            "label": "cost-cut",
            "coverage": report["candidate"]["coverage"],
            "routed_total_usd": report["candidate"]["routed_total_usd"],
            "tasks": report["candidate"]["tasks"],
        },
        "coverage_delta": report["coverage_delta"],
        "cost_delta_usd": report["cost_delta_usd"],
        "measured": False,
    }


def bundled_fanout_sweep(
    root: Path | str | None = None,
    *,
    thresholds: Sequence[float] = FANOUT_SWEEP_THRESHOLDS,
) -> dict[str, Any]:
    """Sweep the fan-out dial over the bundled ensemble workload for the dashboard.

    Re-runs the ensemble fan-out workload once per ``compare_min_value`` threshold
    and reports, at each notch, how many tasks fan out (compare) vs route single
    (ordered), the coverage, the routed (winner) cost, the savings vs the naive
    premium arm, and the ensemble tax. It exposes the honest shape of experiment
    05 vs 06: as the dial rises, coverage and savings stay flat while the ensemble
    tax collapses toward zero. Offline and deterministic; ``measured = false``.
    """

    base = find_samples_root(root)
    workload = load_workload(base / DEFAULT_WORKLOAD)
    pricing = PricingTable.from_yaml(base / DEFAULT_PRICING)
    policy = load_policy(None)
    signals = load_signal_fixture(base / ENSEMBLE_SIGNALS)
    routed_tasks = {tid: workload[tid] for tid in signals if tid in workload}
    baseline = baseline_cost_usd(routed_tasks, policy, pricing)

    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        gate = BudgetGate(compare_min_value=float(threshold))
        traces = route_tasks(workload, signals, policy=policy, pricing=pricing, budget_gate=gate)
        summary = summarize_traces(traces)
        fanout = fanout_stats(traces)
        routed = float(summary["total_cost_usd"])
        delta = round(baseline - routed, 6)
        rows.append(
            {
                "threshold": round(float(threshold), 3),
                "fanout_tasks": fanout["ensemble_tasks"],
                "single_tasks": fanout["single_tasks"],
                "coverage": summary["coverage"],
                "routed_usd": round(routed, 6),
                "delta_pct": round((delta / baseline) if baseline else 0.0, 6),
                "fanout_usd": fanout["fanout_usd"],
                "ensemble_tax_usd": fanout["ensemble_tax_usd"],
                "tax_ratio": fanout["tax_ratio"],
            }
        )
    return {
        "baseline_usd": round(baseline, 6),
        "tasks": len(routed_tasks),
        "rows": rows,
        "measured": False,
    }


def bundled_compare(
    root: Path | str | None = None,
    *,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Head-to-head "one problem, four ways" payload for the dashboard.

    Scores the four approaches (cheapest / premium / ensemble / cost-aware
    router) on each curated task and returns a task menu plus every task's
    arena, so the web app can switch problems with no round-trip. Cost and
    accuracy reuse the same offline machinery as the aggregate panels; latency
    is an illustrative projection. Offline and deterministic; ``measured = false``.
    """

    base = find_samples_root(root)
    workload = load_workload(base / DEFAULT_WORKLOAD)
    pricing = PricingTable.from_yaml(base / DEFAULT_PRICING)
    policy = load_policy(None)
    signals = load_signal_fixture(base / DEFAULT_SIGNALS)
    prompts_path = base / DEFAULT_PROMPTS
    prompts = load_task_prompts(prompts_path) if prompts_path.is_file() else None
    return bundled_head_to_head(
        workload, signals, policy, pricing, task_id=task_id, prompts=prompts
    )


def format_replay_text(report: ReplayReport) -> str:
    """Render a replay report as the human-readable per-task + summary block."""

    lines = [
        f"{trace['task_id']} "
        f"class={trace['class']} "
        f"mode={trace['mode']} "
        f"chosen={trace['chosen']} "
        f"reason={trace['reason']} "
        f"cost=${_cost(trace):.6f}"
        for trace in report.traces
    ]
    summary = report.summary
    lines.append("")
    lines.append(
        "summary "
        f"tasks={summary['tasks']} "
        f"accepted={summary['accepted']} "
        f"coverage={summary['coverage']:.1%} "
        f"cost=${summary['total_cost_usd']:.6f}"
    )
    lines.extend(_format_before_after(summary))
    ledger = summary.get("ledger")
    if ledger:
        lines.append("")
        lines.append(
            f"ledger  path={ledger['path']} appended={ledger['appended']} "
            f"matched={ledger['matched']}/{ledger['records']} "
            f"completeness={ledger['completeness']:.1%} "
            f"status={'PASS' if ledger['ok'] else 'FAIL'}"
        )
    return "\n".join(lines)


def _format_before_after(summary: Mapping[str, Any]) -> list[str]:
    """Render the 30-second naive-vs-routed 'aha' block (offline projection).

    Omitted when the summary carries no baseline (e.g. legacy callers), so the
    per-task + summary output stays intact.
    """

    if "baseline_total_usd" not in summary:
        return []
    baseline = float(summary["baseline_total_usd"])
    routed = float(summary["total_cost_usd"])
    delta = float(summary.get("delta_usd", baseline - routed))
    delta_pct = float(summary.get("delta_pct", 0.0))
    coverage = float(summary.get("coverage", 0.0))
    mode_counts = summary.get("mode_counts", {})
    reason_counts = summary.get("reason_counts", {})
    single = int(mode_counts.get("ordered", 0))
    ensemble = int(mode_counts.get("compare", 0))
    routes = " ".join(f"{reason}={count}" for reason, count in sorted(reason_counts.items()))
    return [
        "",
        "before / after  (offline projection over synthetic data; labels.measured=false)",
        f"  BEFORE  naive: premium model on every task   ${baseline:.6f}",
        f"  AFTER   cost-aware routing                   ${routed:.6f}",
        f"  SAVED   ${delta:.6f}  ({delta_pct:.1%} lower)  at {coverage:.1%} coverage",
        f"  strategy  single-route={single} ensemble={ensemble}"
        + (f"  |  {routes}" if routes else ""),
    ]


def format_replay_json(report: ReplayReport) -> str:
    return json.dumps(report.traces, indent=2, sort_keys=True)


def format_eval_report(report: dict[str, Any]) -> str:
    """Render an eval report as the human-readable cost/coverage summary."""

    lines = [
        f"tasks: {report['tasks']}",
        f"accepted: {report['accepted']}",
        f"coverage: {report['coverage']:.1%}",
        f"routed_total_usd: {report['routed_total_usd']:.6f}",
        f"baseline_total_usd: {report['baseline_total_usd']:.6f}",
        f"delta_usd: {report['delta_usd']:.6f}",
        f"delta_pct: {report['delta_pct']:.1%}",
        "mode_counts:",
    ]
    for mode, count in sorted(report["mode_counts"].items()):
        lines.append(f"  {mode}: {count}")
    lines.append("reason_counts:")
    for reason, count in sorted(report["reason_counts"].items()):
        lines.append(f"  {reason}: {count}")
    by_class = report.get("by_class")
    if by_class:
        lines.append("by_class:")
        for cls, stats in sorted(by_class.items()):
            lines.append(
                f"  {cls}: tasks={stats['tasks']} "
                f"accepted={stats['accepted']} cost=${stats['cost_usd']:.6f}"
            )
    baseline_arms = report.get("baseline_arms")
    if baseline_arms:
        lines.append("single_call_baseline_arms:")
        for arm, stats in baseline_arms.items():
            lines.append(
                f"  {arm}: coverage={stats['coverage']:.1%} "
                f"cost=${stats['total_cost_usd']:.6f}"
            )
    return "\n".join(lines)


def format_regression_report(report: dict[str, Any]) -> str:
    """Render a base-vs-candidate regression report as a human-readable block."""

    base, cand = report["base"], report["candidate"]
    evaluation = report.get("evaluation", {})
    lines = [
        report["diff"],
        "",
        f"evaluation: signals={evaluation.get('signals', '?')} "
        f"tasks={evaluation.get('tasks', '?')} "
        "(base and candidate scored on identical shared signals)",
        "",
        "regression (candidate vs base):",
        f"  tasks: {cand['tasks']} (base {base['tasks']})",
        f"  coverage: {cand['coverage']:.1%} (base {base['coverage']:.1%}, "
        f"delta {report['coverage_delta']:+.4f})",
        f"  routed_total_usd: {cand['routed_total_usd']:.6f} "
        f"(base {base['routed_total_usd']:.6f}, delta {report['cost_delta_usd']:+.6f})",
        f"  baseline_total_usd: {cand['baseline_total_usd']:.6f}",
        f"  delta_pct vs baseline: {cand['delta_pct']:.1%} (base {base['delta_pct']:.1%})",
    ]
    return "\n".join(lines)


def _cost(trace: dict[str, Any]) -> float:
    value = trace.get("cost_usd")
    return float(value) if isinstance(value, int | float) else 0.0
