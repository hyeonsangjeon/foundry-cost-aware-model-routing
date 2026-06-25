#!/usr/bin/env python3
"""Run the local routing replay over sample fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from policy import load_default_policy  # noqa: E402
from router import (  # noqa: E402
    PricingTable,
    load_signal_fixture,
    load_workload,
    route_tasks,
    summarize_traces,
)

DEFAULT_SIGNALS = ROOT / "samples" / "responses" / "routing-signals.sample.json"
DEFAULT_PRICING = ROOT / "samples" / "pricing" / "illustrative.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay sample routing decisions.")
    parser.add_argument("workload", type=Path, help="JSONL workload file")
    parser.add_argument("--signals", type=Path, default=DEFAULT_SIGNALS)
    parser.add_argument("--pricing", type=Path, default=DEFAULT_PRICING)
    parser.add_argument("--json", action="store_true", help="print traces as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workload = load_workload(args.workload)
    signals = load_signal_fixture(args.signals)
    pricing = PricingTable.from_yaml(args.pricing)
    traces = route_tasks(
        workload,
        signals,
        policy=load_default_policy(),
        pricing=pricing,
    )
    if args.json:
        print(json.dumps(traces, indent=2, sort_keys=True))
        return 0

    for trace in traces:
        print(
            f"{trace['task_id']} "
            f"class={trace['class']} "
            f"mode={trace['mode']} "
            f"chosen={trace['chosen']} "
            f"reason={trace['reason']} "
            f"cost=${trace['cost_usd']:.6f}"
        )

    summary = summarize_traces(traces)
    print()
    print(
        "summary "
        f"tasks={summary['tasks']} "
        f"accepted={summary['accepted']} "
        f"coverage={summary['coverage']:.1%} "
        f"cost=${summary['total_cost_usd']:.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
