"""``cost-router`` command-line entry point.

Subcommands are thin wrappers over :mod:`router.pipeline`, so they share the
exact orchestration used by the sample scripts and the eval summary.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .pipeline import (
    format_eval_report,
    format_replay_json,
    format_replay_text,
    resolve_paths,
    run_evals,
    run_replay,
    run_route_once,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cost-router",
        description="Offline, deterministic model-routing experiment CLI.",
    )
    parser.add_argument("--version", action="version", version=f"cost-router {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    replay = subparsers.add_parser("replay", help="Replay routing over the sample workload.")
    _add_data_args(replay)
    replay.add_argument("--json", action="store_true", help="print traces as JSON")
    replay.set_defaults(func=_cmd_replay)

    route_once = subparsers.add_parser("route-once", help="Print one routing trace.")
    route_once.add_argument("--task-id", default="t-0001")
    _add_data_args(route_once)
    route_once.set_defaults(func=_cmd_route_once)

    evals = subparsers.add_parser("evals", help="Summarize routed cost vs. baseline.")
    _add_data_args(evals)
    evals.set_defaults(func=_cmd_evals)

    return parser


def _add_data_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workload", type=Path, default=None)
    parser.add_argument("--signals", type=Path, default=None)
    parser.add_argument("--pricing", type=Path, default=None)
    parser.add_argument(
        "--synth",
        action="store_true",
        help="synthesize deterministic signals for every workload task (offline)",
    )


def _paths(args: argparse.Namespace) -> dict[str, Path]:
    return resolve_paths(workload=args.workload, signals=args.signals, pricing=args.pricing)


def _signals_path(args: argparse.Namespace, paths: dict[str, Path]) -> Path | None:
    return None if args.synth else paths["signals"]


def _cmd_replay(args: argparse.Namespace) -> int:
    paths = _paths(args)
    report = run_replay(
        workload_path=paths["workload"],
        pricing_path=paths["pricing"],
        signals_path=_signals_path(args, paths),
        synth=args.synth,
    )
    print(format_replay_json(report) if args.json else format_replay_text(report))
    return 0


def _cmd_route_once(args: argparse.Namespace) -> int:
    paths = _paths(args)
    try:
        trace = run_route_once(
            task_id=args.task_id,
            workload_path=paths["workload"],
            pricing_path=paths["pricing"],
            signals_path=_signals_path(args, paths),
            synth=args.synth,
        )
    except KeyError as exc:
        raise SystemExit(str(exc).strip('"')) from exc
    print(json.dumps(trace, indent=2, sort_keys=True))
    return 0


def _cmd_evals(args: argparse.Namespace) -> int:
    paths = _paths(args)
    report = run_evals(
        workload_path=paths["workload"],
        pricing_path=paths["pricing"],
        signals_path=_signals_path(args, paths),
        synth=args.synth,
    )
    print(format_eval_report(report))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "command", None):
        print(f"cost-router {__version__}")
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
