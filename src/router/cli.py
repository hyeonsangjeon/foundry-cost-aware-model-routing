"""``cost-router`` command-line entry point.

Subcommands are thin wrappers over :mod:`router.pipeline`, so they share the
exact orchestration used by the sample scripts and the eval summary.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .experiment import (
    format_experiment_list,
    format_experiment_text,
    list_experiments,
    load_experiment,
    run_experiment,
)
from .metrics import (
    FoundryMetricsEmitter,
    JsonlMetricsStore,
    record_experiment_metrics,
    utc_now_iso,
)
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
    replay.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="append replay decisions to an offline JSONL audit ledger",
    )
    replay.add_argument("--json", action="store_true", help="print traces as JSON")
    replay.set_defaults(func=_cmd_replay)

    route_once = subparsers.add_parser("route-once", help="Print one routing trace.")
    route_once.add_argument("--task-id", default="t-0001")
    _add_data_args(route_once)
    route_once.add_argument("--policy", type=Path, default=None)
    route_once.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="append the decision to an offline JSONL audit ledger",
    )
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

    hero = subparsers.add_parser(
        "hero",
        help="Run the flagship experiment: before/after in one command.",
    )
    hero.add_argument("--json", action="store_true", help="print the result as JSON")
    hero.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="append the hero run's decisions to an offline JSONL audit ledger",
    )
    hero.add_argument(
        "--metrics-store",
        type=Path,
        default=None,
        help="record the run's Foundry-shaped metrics to a JSONL history store",
    )
    hero.add_argument(
        "--serve",
        action="store_true",
        help="after the run, boot the offline dashboard to watch it live",
    )
    hero.add_argument("--host", default="127.0.0.1", help="dashboard bind host with --serve")
    hero.add_argument("--port", type=int, default=8000, help="dashboard bind port with --serve")
    hero.set_defaults(func=_cmd_hero)

    _build_policy_parser(subparsers)
    _build_ledger_parser(subparsers)
    _build_experiment_parser(subparsers)
    _build_metrics_parser(subparsers)
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


def _build_ledger_parser(subparsers: argparse._SubParsersAction) -> None:
    ledger = subparsers.add_parser(
        "ledger",
        help="Replay and verify an offline JSONL audit ledger.",
    )
    ledger_sub = ledger.add_subparsers(dest="ledger_command")
    replay = ledger_sub.add_parser(
        "replay",
        help="Re-run stored decisions and compare canonical final payloads.",
    )
    replay.add_argument("--ledger", type=Path, required=True)
    replay.set_defaults(func=_cmd_ledger_replay)


def _build_experiment_parser(subparsers: argparse._SubParsersAction) -> None:
    experiment = subparsers.add_parser(
        "experiment",
        help="List and run named offline experiments (experiments/*.yaml).",
    )
    experiment_sub = experiment.add_subparsers(dest="experiment_command")

    listing = experiment_sub.add_parser("list", help="List available experiments.")
    listing.set_defaults(func=_cmd_experiment_list)

    run = experiment_sub.add_parser("run", help="Run one experiment by name.")
    run.add_argument("name", help="experiment name (e.g. hero) or path to a YAML file")
    run.add_argument("--json", action="store_true", help="print the result as JSON")
    run.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="append the run's decisions to an offline JSONL audit ledger",
    )
    run.add_argument(
        "--metrics-store",
        type=Path,
        default=None,
        help="record the run's Foundry-shaped metrics to a JSONL history store",
    )
    run.set_defaults(func=_cmd_experiment_run)


def _build_metrics_parser(subparsers: argparse._SubParsersAction) -> None:
    metrics = subparsers.add_parser(
        "metrics",
        help="Record, inspect, and Foundry-emit experiment metrics.",
    )
    metrics_sub = metrics.add_subparsers(dest="metrics_command")

    history = metrics_sub.add_parser("history", help="Show recorded experiment run history.")
    history.add_argument("--store", type=Path, required=True, help="metrics JSONL history store")
    history.add_argument("--experiment", default=None, help="filter to one experiment name")
    history.add_argument("--limit", type=int, default=None, help="show only the last N runs")
    history.add_argument("--json", action="store_true", help="print the history as JSON")
    history.set_defaults(func=_cmd_metrics_history)

    emit = metrics_sub.add_parser(
        "emit",
        help="Render an experiment's Azure-Foundry-shaped metric records.",
    )
    emit.add_argument("name", help="experiment name (e.g. hero) or path to a YAML file")
    emit.add_argument(
        "--connection-string",
        default=None,
        help="Azure Foundry / App Insights connection string (marks the emitter configured; "
        "no egress happens offline)",
    )
    emit.add_argument(
        "--store",
        type=Path,
        default=None,
        help="also record the snapshot to a JSONL history store",
    )
    emit.set_defaults(func=_cmd_metrics_emit)


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
    try:
        report = run_replay(
            workload_path=paths["workload"],
            pricing_path=paths["pricing"],
            signals_path=_signals_path(args, paths),
            synth=args.synth,
            policy_path=args.policy,
            ledger_path=args.ledger,
        )
    except (OSError, ValueError) as exc:
        if args.ledger is None:
            raise
        print(f"ledger error: {exc}")
        return 1
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
            ledger_path=args.ledger,
        )
    except KeyError as exc:
        raise SystemExit(str(exc).strip('"')) from exc
    except (OSError, ValueError) as exc:
        if args.ledger is None:
            raise
        print(f"ledger error: {exc}")
        return 1
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


def _cmd_ledger_replay(args: argparse.Namespace) -> int:
    from .ledger import verify_ledger

    try:
        report = verify_ledger(args.ledger)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}")
        print("status: FAIL")
        return 1
    print(f"records: {report.records}")
    print(f"matched: {report.matched}")
    print(f"completeness: {report.completeness:.1%}")
    print(f"status: {'PASS' if report.ok else 'FAIL'}")
    if report.mismatches:
        print(json.dumps(list(report.mismatches), indent=2, sort_keys=True))
    return 0 if report.ok else 1


def _run_named_experiment(
    name: str,
    *,
    as_json: bool,
    ledger: Path | None,
    metrics_store: Path | None = None,
) -> int:
    try:
        experiment = load_experiment(name)
        result = run_experiment(experiment, ledger_path=ledger)
    except (OSError, ValueError, KeyError) as exc:
        print(f"experiment error: {exc}")
        return 1
    if metrics_store is not None:
        record_experiment_metrics(result, store=JsonlMetricsStore(metrics_store))
    if as_json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(format_experiment_text(result))
        if metrics_store is not None:
            print(f"\nmetrics  recorded to {metrics_store}")
    return 0 if result.ok else 1


def _cmd_experiment_list(args: argparse.Namespace) -> int:
    print(format_experiment_list(list_experiments()))
    return 0


def _cmd_experiment_run(args: argparse.Namespace) -> int:
    return _run_named_experiment(
        args.name,
        as_json=args.json,
        ledger=args.ledger,
        metrics_store=args.metrics_store,
    )


def _cmd_metrics_history(args: argparse.Namespace) -> int:
    store = JsonlMetricsStore(args.store)
    try:
        rows = store.history(experiment=args.experiment, limit=args.limit)
    except (OSError, ValueError) as exc:
        print(f"metrics error: {exc}")
        return 1
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    if not rows:
        print(f"no recorded runs in {args.store}")
        return 0
    print(f"metrics history  ({len(rows)} run(s) from {args.store})")
    for row in rows:
        stamp = row.get("recorded_at") or "—"
        print(
            f"  {stamp}  {row.get('experiment'):<10} "
            f"cov={float(row.get('coverage', 0.0)):.1%} "
            f"routed=${float(row.get('routed_usd', 0.0)):.6f} "
            f"saved={float(row.get('delta_pct', 0.0)):.1%} "
            f"fanout_tax=${float(row.get('ensemble_tax_usd', 0.0)):.6f} "
            f"repro={'PASS' if row.get('reproducible') else 'FAIL'}"
        )
    return 0


def _cmd_metrics_emit(args: argparse.Namespace) -> int:
    try:
        experiment = load_experiment(args.name)
        result = run_experiment(experiment)
    except (OSError, ValueError, KeyError) as exc:
        print(f"metrics error: {exc}")
        return 1
    emitter = FoundryMetricsEmitter(connection_string=args.connection_string)
    store = JsonlMetricsStore(args.store) if args.store is not None else None
    metrics = record_experiment_metrics(
        result, store=store, emitter=emitter, recorded_at=utc_now_iso()
    )
    sink = "Azure Foundry (configured)" if emitter.configured else "local capture (offline)"
    print(f"# {len(emitter.captured)} metric records for {metrics.experiment} → {sink}")
    print(json.dumps(emitter.captured, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def _cmd_hero(args: argparse.Namespace) -> int:
    code = _run_named_experiment(
        "hero",
        as_json=args.json,
        ledger=args.ledger,
        metrics_store=args.metrics_store,
    )
    if not args.serve:
        if not args.json:
            print("")
            print("next  cost-router serve   →  open the dashboard to watch it live")
        return code
    from . import server

    if not args.json:
        url = f"http://{args.host}:{args.port}/?run=1"
        print("")
        print(f"serving the offline dashboard on {url} (Ctrl-C to stop)", flush=True)
        print("open it to watch the before/after animate automatically", flush=True)
    return server.serve(host=args.host, port=args.port)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "command", None):
        print(f"cost-router {__version__}")
        return 0
    if args.command == "policy" and not getattr(args, "policy_command", None):
        from policy import show_text

        print(show_text(load_policy(None)))
        return 0
    if args.command == "ledger" and not getattr(args, "ledger_command", None):
        print("usage: cost-router ledger replay --ledger PATH")
        return 0
    if args.command == "experiment" and not getattr(args, "experiment_command", None):
        print("usage: cost-router experiment [list|run <name>]")
        return 0
    if args.command == "metrics" and not getattr(args, "metrics_command", None):
        print("usage: cost-router metrics [history --store PATH | emit <name>]")
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
