#!/usr/bin/env python3
"""Run the local routing replay over sample fixtures."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from router.pipeline import (  # noqa: E402
    DEFAULT_PRICING,
    DEFAULT_SIGNALS,
    format_replay_json,
    format_replay_text,
    run_replay,
)

DEFAULT_SIGNALS_PATH = ROOT / DEFAULT_SIGNALS
DEFAULT_PRICING_PATH = ROOT / DEFAULT_PRICING


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay sample routing decisions.")
    parser.add_argument("workload", type=Path, help="JSONL workload file")
    parser.add_argument("--signals", type=Path, default=DEFAULT_SIGNALS_PATH)
    parser.add_argument("--pricing", type=Path, default=DEFAULT_PRICING_PATH)
    parser.add_argument(
        "--synth",
        action="store_true",
        help="synthesize deterministic signals for every workload task (offline)",
    )
    parser.add_argument("--json", action="store_true", help="print traces as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_replay(
        workload_path=args.workload,
        pricing_path=args.pricing,
        signals_path=None if args.synth else args.signals,
        synth=args.synth,
    )
    print(format_replay_json(report) if args.json else format_replay_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
