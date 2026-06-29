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

from router.pipeline import (  # noqa: E402
    DEFAULT_PRICING,
    DEFAULT_SIGNALS,
    DEFAULT_WORKLOAD,
    format_eval_report,
    run_evals,
)

DEFAULT_WORKLOAD_PATH = ROOT / DEFAULT_WORKLOAD
DEFAULT_SIGNALS_PATH = ROOT / DEFAULT_SIGNALS
DEFAULT_PRICING_PATH = ROOT / DEFAULT_PRICING


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize sample routing results.")
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
    report = run_evals(
        workload_path=args.workload,
        pricing_path=args.pricing,
        signals_path=None if args.synth else args.signals,
        synth=args.synth,
    )
    print(format_eval_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
