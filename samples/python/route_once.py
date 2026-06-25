#!/usr/bin/env python3
"""Inspect one local routing decision."""

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
from router import PricingTable, load_signal_fixture, load_workload, route_task  # noqa: E402

DEFAULT_WORKLOAD = ROOT / "samples" / "telemetry" / "mixed-coding-workload.sample.jsonl"
DEFAULT_SIGNALS = ROOT / "samples" / "responses" / "routing-signals.sample.json"
DEFAULT_PRICING = ROOT / "samples" / "pricing" / "illustrative.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Print one sample routing trace.")
    parser.add_argument("--task-id", default="t-0001")
    parser.add_argument("--workload", type=Path, default=DEFAULT_WORKLOAD)
    parser.add_argument("--signals", type=Path, default=DEFAULT_SIGNALS)
    parser.add_argument("--pricing", type=Path, default=DEFAULT_PRICING)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workload = load_workload(args.workload)
    signals = load_signal_fixture(args.signals)
    if args.task_id not in workload:
        raise SystemExit(f"unknown task id: {args.task_id}")
    if args.task_id not in signals:
        raise SystemExit(f"no sample signals for task id: {args.task_id}")
    trace = route_task(
        workload[args.task_id],
        signals[args.task_id],
        policy=load_default_policy(),
        pricing=PricingTable.from_yaml(args.pricing),
    )
    print(json.dumps(trace, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
