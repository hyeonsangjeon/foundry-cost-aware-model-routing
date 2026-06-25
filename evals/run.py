#!/usr/bin/env python3
"""Summarize local routing replay cost and coverage."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.baselines import baseline_cost_usd  # noqa: E402

from policy import load_default_policy  # noqa: E402
from router import (  # noqa: E402
    PricingTable,
    load_signal_fixture,
    load_workload,
    route_tasks,
    summarize_traces,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize sample routing results.")
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--signals", type=Path, required=True)
    parser.add_argument("--pricing", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workload = load_workload(args.workload)
    signals = load_signal_fixture(args.signals)
    pricing = PricingTable.from_yaml(args.pricing)
    policy = load_default_policy()
    selected_workload = {task_id: workload[task_id] for task_id in signals}
    traces = route_tasks(selected_workload, signals, policy=policy, pricing=pricing)
    routed = summarize_traces(traces)
    baseline_cost = baseline_cost_usd(selected_workload, policy, pricing)
    delta = round(baseline_cost - routed["total_cost_usd"], 6)
    delta_pct = (delta / baseline_cost) if baseline_cost else 0.0

    print(f"tasks: {routed['tasks']}")
    print(f"accepted: {routed['accepted']}")
    print(f"coverage: {routed['coverage']:.1%}")
    print(f"routed_total_usd: {routed['total_cost_usd']:.6f}")
    print(f"baseline_total_usd: {baseline_cost:.6f}")
    print(f"delta_usd: {delta:.6f}")
    print(f"delta_pct: {delta_pct:.1%}")
    print("mode_counts:")
    for mode, count in sorted(routed["mode_counts"].items()):
        print(f"  {mode}: {count}")
    print("reason_counts:")
    for reason, count in sorted(routed["reason_counts"].items()):
        print(f"  {reason}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
