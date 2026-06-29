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

from router.pipeline import (  # noqa: E402
    DEFAULT_PRICING,
    DEFAULT_SIGNALS,
    DEFAULT_WORKLOAD,
    run_route_once,
)

DEFAULT_WORKLOAD_PATH = ROOT / DEFAULT_WORKLOAD
DEFAULT_SIGNALS_PATH = ROOT / DEFAULT_SIGNALS
DEFAULT_PRICING_PATH = ROOT / DEFAULT_PRICING


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Print one sample routing trace.")
    parser.add_argument("--task-id", default="t-0001")
    parser.add_argument("--workload", type=Path, default=DEFAULT_WORKLOAD_PATH)
    parser.add_argument("--signals", type=Path, default=DEFAULT_SIGNALS_PATH)
    parser.add_argument("--pricing", type=Path, default=DEFAULT_PRICING_PATH)
    parser.add_argument(
        "--synth",
        action="store_true",
        help="synthesize deterministic signals for every workload task (offline)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        trace = run_route_once(
            task_id=args.task_id,
            workload_path=args.workload,
            pricing_path=args.pricing,
            signals_path=None if args.synth else args.signals,
            synth=args.synth,
        )
    except KeyError as exc:
        raise SystemExit(str(exc).strip('"')) from exc
    print(json.dumps(trace, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
