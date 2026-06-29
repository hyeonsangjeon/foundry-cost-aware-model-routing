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
    format_regression_report,
    format_replay_json,
    format_replay_text,
    load_policy,
    regression_report,
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
    replay.add_argument("--policy", type=Path, default=None)
    replay.add_argument("--json", action="store_true", help="print traces as JSON")
    replay.set_defaults(func=_cmd_replay)

    route_once = subparsers.add_parser("route-once", help="Print one routing trace.")
    route_once.add_argument("--task-id", default="t-0001")
    _add_data_args(route_once)
    route_once.add_argument("--policy", type=Path, default=None)
    route_once.set_defaults(func=_cmd_route_once)

    evals = subparsers.add_parser("evals", help="Summarize routed cost vs. baseline.")
    _add_data_args(evals)
    evals.add_argument("--policy", type=Path, default=None)
    evals.set_defaults(func=_cmd_evals)

    serve = subparsers.add_parser("serve", help="Run the offline routing HTTP service.")
    serve.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1)")
    serve.add_argument("--port", type=int, default=8000, help="bind port (default 8000)")
    serve.add_argument("--policy", type=Path, default=None, help="policy YAML to serve")
    serve.set_defaults(func=_cmd_serve)

    _build_policy_parser(subparsers)
    return parser


def _build_policy_parser(subparsers: argparse._SubParsersAction) -> None:
    policy = subparsers.add_parser("policy", help="Inspect, validate, diff, simulate policies.")
    policy_sub = policy.add_subparsers(dest="policy_command")

    show = policy_sub.add_parser("show", help="Print policy version/classes/candidates.")
    show.add_argument("--policy", type=Path, default=None)
    show.set_defaults(func=_cmd_policy_show)

    validate = policy_sub.add_parser("validate", help="Validate a policy YAML contract.")
    validate.add_argument("--policy", type=Path, default=None)
    validate.set_defaults(func=_cmd_policy_validate)

    diff = policy_sub.add_parser("diff", help="Summarize candidate vs. base policy changes.")
    diff.add_argument("--base", type=Path, default=None)
    diff.add_argument("--candidate", type=Path, required=True)
    diff.set_defaults(func=_cmd_policy_diff)

    simulate = policy_sub.add_parser("simulate", help="Replay/eval a policy on the workload.")
    simulate.add_argument("--policy", type=Path, default=None)
    _add_data_args(simulate)
    simulate.set_defaults(func=_cmd_policy_simulate)

    regression = policy_sub.add_parser("regression", help="Base vs. candidate cost/coverage.")
    regression.add_argument("--base", type=Path, default=None)
    regression.add_argument("--candidate", type=Path, required=True)
    _add_data_args(regression)
    regression.set_defaults(func=_cmd_policy_regression)


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
        policy_path=args.policy,
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
            policy_path=args.policy,
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
        policy_path=args.policy,
    )
    print(format_eval_report(report))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from . import server

    return server.serve(host=args.host, port=args.port, policy_path=args.policy)


def _cmd_policy_show(args: argparse.Namespace) -> int:
    from policy import show_text

    print(show_text(load_policy(args.policy)))
    return 0


def _cmd_policy_validate(args: argparse.Namespace) -> int:
    from policy import PolicyTable, validate_errors

    try:
        table = PolicyTable.from_yaml(args.policy) if args.policy else load_policy()
    except (ValueError, OSError) as exc:
        print(f"INVALID: {exc}")
        return 1
    errors = validate_errors(table)
    if errors:
        for err in errors:
            print(f"INVALID: {err}")
        return 1
    print("OK: policy is valid")
    return 0


def _cmd_policy_diff(args: argparse.Namespace) -> int:
    from policy import PolicyTable, diff_policies, format_diff

    base = load_policy(args.base)
    candidate = PolicyTable.from_yaml(args.candidate).validate()
    print(format_diff(diff_policies(base, candidate)))
    return 0


def _cmd_policy_simulate(args: argparse.Namespace) -> int:
    paths = _paths(args)
    report = run_evals(
        workload_path=paths["workload"],
        pricing_path=paths["pricing"],
        signals_path=_signals_path(args, paths),
        synth=args.synth,
        policy_path=args.policy,
    )
    print(format_eval_report(report))
    return 0


def _cmd_policy_regression(args: argparse.Namespace) -> int:
    paths = _paths(args)
    report = regression_report(
        workload_path=paths["workload"],
        pricing_path=paths["pricing"],
        candidate_policy_path=args.candidate,
        base_policy_path=args.base,
        signals_path=_signals_path(args, paths),
        synth=args.synth,
    )
    print(format_regression_report(report))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "command", None):
        print(f"cost-router {__version__}")
        return 0
    if args.command == "policy" and not getattr(args, "policy_command", None):
        from policy import show_text

        print(show_text(load_policy(None)))
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
