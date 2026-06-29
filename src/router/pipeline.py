"""High-level offline routing flows shared by the CLI, sample scripts, and evals.

Every entry point (``cost-router`` subcommands, ``samples/python/*.py``, and
``evals/run.py``) funnels through these helpers so the orchestration and output
formatting live in exactly one place.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from policy import PolicyTable, load_default_policy

from .baseline import baseline_cost_usd
from .offline import (
    load_signal_fixture,
    load_workload,
    route_task,
    route_tasks,
    summarize_traces,
    synthesize_signals,
)
from .pricing import PricingTable

DEFAULT_WORKLOAD = Path("samples/telemetry/mixed-coding-workload.sample.jsonl")
DEFAULT_SIGNALS = Path("samples/responses/routing-signals.sample.json")
DEFAULT_PRICING = Path("samples/pricing/illustrative.yaml")


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


def _load_context(
    *,
    workload_path: Path | str,
    pricing_path: Path | str,
) -> tuple[PolicyTable, dict[str, dict[str, Any]], PricingTable]:
    policy = load_default_policy()
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
) -> ReplayReport:
    """Route every task that has signals and return traces plus a summary."""

    policy, workload, pricing = _load_context(
        workload_path=workload_path, pricing_path=pricing_path
    )
    signals = _signals_for(
        synth=synth, workload=workload, policy=policy, signals_path=signals_path
    )
    traces = route_tasks(workload, signals, policy=policy, pricing=pricing)
    return ReplayReport(traces=traces, summary=summarize_traces(traces))


def run_route_once(
    *,
    task_id: str,
    workload_path: Path | str,
    pricing_path: Path | str,
    signals_path: Path | str | None = None,
    synth: bool = False,
) -> dict[str, Any]:
    """Route a single task and return its trace."""

    policy, workload, pricing = _load_context(
        workload_path=workload_path, pricing_path=pricing_path
    )
    if task_id not in workload:
        raise KeyError(f"unknown task id: {task_id}")
    signals = _signals_for(
        synth=synth, workload=workload, policy=policy, signals_path=signals_path
    )
    if task_id not in signals:
        raise KeyError(f"no sample signals for task id: {task_id}")
    return route_task(workload[task_id], signals[task_id], policy=policy, pricing=pricing)


def run_evals(
    *,
    workload_path: Path | str,
    pricing_path: Path | str,
    signals_path: Path | str | None = None,
    synth: bool = False,
) -> dict[str, Any]:
    """Summarize routed cost/coverage against the always-most-expensive baseline."""

    policy, workload, pricing = _load_context(
        workload_path=workload_path, pricing_path=pricing_path
    )
    signals = _signals_for(
        synth=synth, workload=workload, policy=policy, signals_path=signals_path
    )
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
    }


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
    return "\n".join(lines)


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
    return "\n".join(lines)


def _cost(trace: dict[str, Any]) -> float:
    value = trace.get("cost_usd")
    return float(value) if isinstance(value, int | float) else 0.0
