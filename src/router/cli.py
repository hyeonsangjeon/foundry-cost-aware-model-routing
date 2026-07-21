"""``cost-router`` command-line entry point.

Subcommands are thin wrappers over :mod:`router.pipeline`, so they share the
exact orchestration used by the sample scripts and the eval summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import textwrap
from pathlib import Path

from . import __version__
from .baseline import model_router_summary
from .experiment import (
    format_experiment_list,
    format_experiment_text,
    list_experiments,
    load_experiment,
    run_experiment,
)
from .foundry_arena import (
    FleetSlate,
    FoundryFleet,
    MeasuredArenaLedger,
    arena_report,
    load_arena_tasks,
    run_live_arena,
)
from .foundry_live import (
    AzureModelRouterClient,
    FoundryConfig,
    RecordedRouterClient,
    capture_recorded_usage,
    load_dotenv_file,
    load_recorded_usage,
    measured_router_summary,
)
from .foundry_router import (
    FoundryModelRouter,
    azure_router_choice_client,
    capture_recorded_choices,
    load_recorded_choices,
    summary_from_choices,
)
from .metrics import (
    ExperimentMetrics,
    FoundryMetricsEmitter,
    JsonlMetricsStore,
    record_experiment_metrics,
    utc_now_iso,
)
from .offline import load_workload
from .pipeline import (
    _signals_for,
    bundled_compare,
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
from .pricing import PricingTable

# Bundled recorded provider-usage snapshot: replayed offline so `foundry live`
# demonstrates the measured scoring path with no credentials (measured=false).
DEFAULT_USAGE_FIXTURE = Path("samples/responses/model-router-usage.sample.json")

# Bundled recorded single-call *choices* snapshot: illustrative task->model picks
# replayed offline so `foundry router` demos the exp-07 comparison (measured=false).
DEFAULT_CHOICES_FIXTURE = Path("samples/responses/model-router-choices.sample.json")

# Live arena defaults: prompt-bearing curated workload + real fleet list prices.
DEFAULT_ARENA_WORKLOAD = Path("samples/telemetry/curated-arena-live.sample.jsonl")
DEFAULT_FLEET_PRICING = Path("samples/pricing/foundry-5series.yaml")


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

    compare = subparsers.add_parser(
        "compare",
        help="One problem, four ways: cost vs latency vs accuracy head-to-head.",
    )
    compare.add_argument(
        "--task",
        default=None,
        help="task id to compare (default: the most instructive curated task)",
    )
    compare.add_argument("--json", action="store_true", help="print the arena as JSON")
    compare.set_defaults(func=_cmd_compare)

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

    foundry = subparsers.add_parser(
        "foundry",
        help="Live Azure AI Foundry Model Router bridge — measured spend (opt-in).",
    )
    foundry_sub = foundry.add_subparsers(dest="foundry_command")

    fstatus = foundry_sub.add_parser(
        "status",
        help="Show the (redacted) Foundry configuration and live-call readiness.",
    )
    fstatus.add_argument("--json", action="store_true", help="print the status as JSON")
    fstatus.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="dotenv file to load before reading config (default: .env; missing is fine)",
    )
    fstatus.set_defaults(func=_cmd_foundry_status)

    flive = foundry_sub.add_parser(
        "live",
        help="Score a Model Router run on real token usage (recorded fixture unless --live).",
    )
    _add_data_args(flive)
    flive.add_argument(
        "--recorded",
        type=Path,
        default=None,
        help="recorded provider-usage fixture to replay offline (default: bundled sample)",
    )
    flive.add_argument(
        "--live",
        action="store_true",
        help="make real Azure calls (requires credentials AND a workload with prompts)",
    )
    flive.add_argument(
        "--capture",
        type=Path,
        default=None,
        metavar="PATH",
        help="with --live: capture the real router's outcomes to PATH as a recorded "
        "snapshot (genuine Azure output the RecordedRouterClient can replay offline)",
    )
    flive.add_argument(
        "--max-output-tokens",
        type=int,
        default=2048,
        help="per-call completion budget for live calls (raise for reasoning models)",
    )
    flive.add_argument(
        "--store",
        type=Path,
        default=None,
        help="record the measured run to a JSONL metrics history store (shows in the dashboard)",
    )
    flive.add_argument("--json", action="store_true", help="print the summary as JSON")
    flive.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="dotenv file to load before reading config (default: .env; missing is fine)",
    )
    flive.set_defaults(func=_cmd_foundry_live)

    frouter = foundry_sub.add_parser(
        "router",
        help="Single-call router choice — exp-07 head-to-head (recorded fixture unless --live).",
    )
    _add_data_args(frouter)
    frouter.add_argument(
        "--recorded",
        type=Path,
        default=None,
        help="recorded task->model choices fixture to replay offline (default: bundled sample)",
    )
    frouter.add_argument(
        "--live",
        action="store_true",
        help="ask a real Model Router deployment for each choice (requires credentials + prompts)",
    )
    frouter.add_argument(
        "--capture",
        type=Path,
        default=None,
        metavar="PATH",
        help="with --live: capture the real router's genuine per-task choices to PATH",
    )
    frouter.add_argument(
        "--max-output-tokens",
        type=int,
        default=2048,
        help="per-call completion budget for live calls (raise for reasoning models)",
    )
    frouter.add_argument("--json", action="store_true", help="print the summary as JSON")
    frouter.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="dotenv file to load before reading config (default: .env; missing is fine)",
    )
    frouter.set_defaults(func=_cmd_foundry_router)

    farena = foundry_sub.add_parser(
        "arena",
        help="One problem, four ways — measured head-to-head on real deployments (--live).",
    )
    farena.add_argument(
        "--workload",
        type=Path,
        default=None,
        help="prompt-bearing JSONL workload (default: curated live arena sample)",
    )
    farena.add_argument(
        "--pricing",
        type=Path,
        default=None,
        help="rate card for pricing real usage (default: bundled 5-series list prices)",
    )
    farena.add_argument(
        "--live",
        action="store_true",
        help="make real Azure calls for all four arms (requires credentials)",
    )
    farena.add_argument(
        "--max-output-tokens",
        type=int,
        default=2048,
        help="per-call completion budget (reasoning models need headroom; default 2048)",
    )
    farena.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the full measured report to this JSON file",
    )
    farena.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="append one honest measured row per task to this JSONL ledger",
    )
    farena.add_argument("--json", action="store_true", help="print the report as JSON")
    farena.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="dotenv file to load before reading config (default: .env; missing is fine)",
    )
    farena.set_defaults(func=_cmd_foundry_arena)


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


def _yn(flag: bool) -> str:
    return "yes" if flag else "no"


def _auth_label(method: str) -> str:
    return {
        "entra": "Microsoft Entra ID (Azure AD token, keyless)",
        "key": "API key",
        "none": "none (not configured)",
    }.get(method, method)


def _cmd_foundry_status(args: argparse.Namespace) -> int:
    loaded = load_dotenv_file(args.env_file)
    status = FoundryConfig.from_env().status()
    status["dotenv_loaded"] = len(loaded)
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    print("Azure AI Foundry — live measured Model Router bridge")
    print(f"  router configured : {_yn(status['router_configured'])}")
    print(f"  credentialed      : {_yn(status['credentialed'])}")
    print(f"  auth method       : {_auth_label(status['auth_method'])}")
    if status["auth_method"] == "entra":
        print(f"  token scope       : {status['token_scope']}")
    print(f"  observability     : {_yn(status['observability_configured'])}")
    print(f"  endpoint          : {status['endpoint'] or '—'}")
    print(f"  deployment        : {status['deployment'] or '—'}")
    print(f"  api key           : {status['api_key']}")
    print(f"  api version       : {status['api_version']}")
    print(f"  connection string : {status['connection_string']}")
    print(f"  pricing           : {status['pricing_path']}")
    print(f"  .env loaded       : {len(loaded)} setting(s) from {args.env_file}")
    if status["missing"]:
        print(f"  missing           : {', '.join(status['missing'])}")
        print("  → set these in .env (see .env.sample), then `cost-router foundry live --live`.")
        if status["auth_method"] != "entra":
            print("  → key auth disabled on your resource? use Microsoft Entra ID: "
                  "set AZURE_AI_FOUNDRY_AUTH=entra and `az login` (no key needed).")
    elif status["auth_method"] == "entra":
        print("  ready (Entra ID): `az login` once, then "
              "`cost-router foundry live --live` (needs a workload with prompts).")
    else:
        print("  ready: `cost-router foundry live --live` (needs a workload with prompts).")
    print("  note: without --live, runs replay a recorded snapshot (measured=false).")
    return 0


def _load_scoring_inputs(args: argparse.Namespace):
    paths = _paths(args)
    policy = load_policy(None)
    workload = load_workload(paths["workload"])
    pricing = PricingTable.from_yaml(paths["pricing"])
    bundle = _signals_for(
        synth=args.synth,
        workload=workload,
        policy=policy,
        signals_path=_signals_path(args, paths),
    )
    signals = bundle.signals
    workload = {task_id: workload[task_id] for task_id in signals if task_id in workload}
    return workload, signals, policy, pricing


def _measured_metrics_record(summary: dict, *, recorded_at: str) -> ExperimentMetrics:
    labels = summary.get("labels", {})
    routed = float(summary.get("total_cost_usd", 0.0))
    tasks = int(summary.get("tasks", 0))
    seed = f"foundry-live|{labels.get('provenance')}|{tasks}|{routed}|{summary.get('coverage')}"
    run_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return ExperimentMetrics(
        run_id=run_id,
        experiment="foundry-live",
        title="Azure Model Router (live measured bridge)",
        source=str(labels.get("provenance", "recorded")),
        tasks=tasks,
        accepted=int(summary.get("accepted", 0)),
        coverage=float(summary.get("coverage") or 0.0),
        routed_usd=routed,
        baseline_usd=routed,
        delta_usd=0.0,
        delta_pct=0.0,
        avg_usd_per_task=float(summary.get("avg_usd_per_task", 0.0)),
        ensemble_tasks=0,
        single_tasks=tasks,
        fanout_candidates=0,
        fanout_usd=0.0,
        ensemble_tax_usd=0.0,
        tax_ratio=0.0,
        spotlight_task=None,
        spotlight_ratio=None,
        reproducible=True,
        recorded_at=recorded_at,
        measured=bool(labels.get("measured", False)),
        dimensions={
            "selection": str(summary.get("selection", "azure-model-router")),
            "spend_source": str(labels.get("spend_source", "provider-usage")),
            "provenance": str(labels.get("provenance", "recorded")),
            "coverage_measured": str(labels.get("coverage_measured", False)).lower(),
        },
    )


def _capture_resource_meta(config: FoundryConfig) -> dict[str, str]:
    """Non-secret provenance for a captured snapshot (never the endpoint URL)."""

    host = str(config.endpoint or "").split("://", 1)[-1].split("/", 1)[0]
    account = host.split(".", 1)[0] if host else os.environ.get("AZURE_AI_SERVICES_ACCOUNT", "")
    meta = {
        "account": account,
        "resource_group": os.environ.get("AZURE_RESOURCE_GROUP", ""),
        "region": os.environ.get("CLOUD_LOCATION", ""),
        "auth": "microsoft-entra-id-keyless" if config.auth_method == "entra" else "api-key",
        "router_deployment": str(config.deployment or ""),
        "api_version": config.resolved_api_version,
    }
    return {key: value for key, value in meta.items() if value}


def _capture_recorded_snapshot(args: argparse.Namespace) -> int:
    if not args.live:
        print("foundry live --capture: capturing real outcomes needs live calls. Add --live")
        print("  (and sign in with `az login`); `cost-router foundry status` must show yes.")
        return 2
    config = FoundryConfig.from_env()
    if not config.credentialed:
        print("foundry live --capture: not credentialed — set AZURE_AI_FOUNDRY_* in .env, "
              "then `az login`.")
        return 1
    workload_path = args.workload or DEFAULT_ARENA_WORKLOAD
    try:
        workload = load_workload(workload_path)
    except (OSError, ValueError) as exc:
        print(f"foundry live --capture: {exc}")
        return 1
    if not workload:
        print(f"foundry live --capture: no tasks in {workload_path}")
        return 1

    client = AzureModelRouterClient(config=config, max_output_tokens=args.max_output_tokens)
    try:
        snapshot = capture_recorded_usage(
            workload, client, resource=_capture_resource_meta(config)
        )
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"foundry live --capture: {exc}")
        return 1

    args.capture.parent.mkdir(parents=True, exist_ok=True)
    args.capture.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    outcomes = snapshot["outcomes"]
    mix: dict[str, int] = {}
    for entry in outcomes.values():
        mix[entry["model"]] = mix.get(entry["model"], 0) + 1
    mix_str = ", ".join(f"{model}×{count}" for model, count in sorted(mix.items()))
    print(f"foundry live — captured {len(outcomes)} real outcomes → {args.capture}")
    print(f"  source     : LIVE Azure Model Router ({config.deployment})")
    print(f"  captured_at: {snapshot['captured_at']}")
    print(f"  models     : {mix_str}")
    print("  labels     : measured=false  provenance=recorded  captured_from=live")
    print(f"  replay     : cost-router foundry live --recorded {args.capture}")
    return 0


def _cmd_foundry_live(args: argparse.Namespace) -> int:
    load_dotenv_file(args.env_file)

    if args.capture is not None:
        return _capture_recorded_snapshot(args)

    try:
        workload, signals, policy, pricing = _load_scoring_inputs(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"foundry live: {exc}")
        return 1

    # The shipped recorded snapshot carries real 5-series model names, so price it
    # with the real fleet list rates unless the caller pinned their own --pricing.
    if args.pricing is None:
        try:
            pricing = PricingTable.from_yaml(DEFAULT_FLEET_PRICING)
        except (OSError, ValueError) as exc:
            print(f"foundry live: {exc}")
            return 1

    config = FoundryConfig.from_env()
    if args.live:
        if not config.credentialed:
            print(
                "foundry live: not credentialed — set AZURE_AI_FOUNDRY_* in .env "
                "(run `cost-router foundry status`)."
            )
            return 1
        client: object = AzureModelRouterClient(
            config=config, max_output_tokens=args.max_output_tokens
        )
        mode = "LIVE Azure Model Router"
    else:
        fixture = args.recorded or DEFAULT_USAGE_FIXTURE
        try:
            outcomes = load_recorded_usage(fixture)
        except (OSError, ValueError) as exc:
            print(f"foundry live: {exc}")
            return 1
        client = RecordedRouterClient(outcomes)
        workload = {task_id: task for task_id, task in workload.items() if task_id in outcomes}
        mode = f"recorded snapshot ({fixture})"

    try:
        summary = measured_router_summary(
            workload, signals, policy, pricing, client=client  # type: ignore[arg-type]
        )
    except (KeyError, ValueError, RuntimeError) as exc:
        print(f"foundry live: {exc}")
        return 1

    if args.store is not None:
        record = _measured_metrics_record(summary, recorded_at=utc_now_iso())
        JsonlMetricsStore(args.store).record(record)

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    labels = summary["labels"]
    print(f"Azure Model Router — measured spend  ({mode})")
    print(f"  tasks             : {summary['tasks']}")
    print(f"  routed cost (real): ${summary['total_cost_usd']:.6f}")
    print(f"  avg $/task        : ${summary['avg_usd_per_task']:.6f}")
    coverage = summary["coverage"]
    if coverage is None:
        print(f"  coverage          : ungraded ({labels['coverage_basis']} — "
              "spend is measured, correctness needs a grader)")
    else:
        cov_kind = "measured" if labels["coverage_measured"] else "projected"
        print(f"  coverage ({cov_kind}): {coverage:.1%}")
    print(f"  spend source      : {labels['spend_source']}")
    print(f"  provenance        : {labels['provenance']}")
    print(f"  measured          : {_yn(labels['measured'])}")
    if not labels["measured"]:
        print("  → this is a replay/projection; run with --live + credentials for measured=true.")
    return 0


def _capture_recorded_choices_snapshot(args: argparse.Namespace) -> int:
    if not args.live:
        print("foundry router --capture: capturing real choices needs live calls. Add --live")
        print("  (and sign in with `az login`); `cost-router foundry status` must show yes.")
        return 2
    config = FoundryConfig.from_env()
    if not config.credentialed:
        print("foundry router --capture: not credentialed — set AZURE_AI_FOUNDRY_* in .env, "
              "then `az login`.")
        return 1
    workload_path = args.workload or DEFAULT_ARENA_WORKLOAD
    try:
        workload = load_workload(workload_path)
    except (OSError, ValueError) as exc:
        print(f"foundry router --capture: {exc}")
        return 1
    if not workload:
        print(f"foundry router --capture: no tasks in {workload_path}")
        return 1

    client = AzureModelRouterClient(config=config, max_output_tokens=args.max_output_tokens)
    router = FoundryModelRouter(
        endpoint=config.endpoint,
        deployment=config.deployment,
        client=azure_router_choice_client(client),
    )
    try:
        snapshot = capture_recorded_choices(
            workload, router, resource=_capture_resource_meta(config)
        )
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"foundry router --capture: {exc}")
        return 1

    args.capture.parent.mkdir(parents=True, exist_ok=True)
    args.capture.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    choices = snapshot["choices"]
    mix: dict[str, int] = {}
    for model in choices.values():
        mix[model] = mix.get(model, 0) + 1
    mix_str = ", ".join(f"{model}×{count}" for model, count in sorted(mix.items()))
    print(f"foundry router — captured {len(choices)} real choices → {args.capture}")
    print(f"  source     : LIVE Azure Model Router ({config.deployment})")
    print(f"  captured_at: {snapshot['captured_at']}")
    print(f"  choices    : {mix_str}")
    print("  labels     : measured=false  decisions=recorded  captured_from=live")
    print(f"  replay     : cost-router foundry router --recorded {args.capture}")
    return 0


def _cmd_foundry_router(args: argparse.Namespace) -> int:
    load_dotenv_file(args.env_file)

    if args.capture is not None:
        return _capture_recorded_choices_snapshot(args)

    try:
        workload, signals, policy, pricing = _load_scoring_inputs(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"foundry router: {exc}")
        return 1

    proxy = model_router_summary(workload, signals, policy, pricing)

    config = FoundryConfig.from_env()
    if args.live:
        if not config.credentialed:
            print(
                "foundry router: --live needs credentials (set AZURE_AI_FOUNDRY_* in .env, then "
                "`az login`) and a prompt-bearing workload (run `cost-router foundry status`)."
            )
            return 1
        client = AzureModelRouterClient(config=config, max_output_tokens=args.max_output_tokens)
        router = FoundryModelRouter(
            endpoint=config.endpoint,
            deployment=config.deployment,
            client=azure_router_choice_client(client),
        )
        try:
            choices = {tid: router.choose(task) for tid, task in workload.items()}
        except (RuntimeError, ValueError, KeyError) as exc:
            print(f"foundry router: {exc}")
            return 1
        arm = summary_from_choices(workload, signals, policy, pricing, choices, provenance="live")
        mode = "LIVE Azure Model Router"
    else:
        fixture = args.recorded or DEFAULT_CHOICES_FIXTURE
        try:
            choices = load_recorded_choices(fixture)
        except (OSError, ValueError) as exc:
            print(f"foundry router: {exc}")
            return 1
        arm = summary_from_choices(workload, signals, policy, pricing, choices)
        mode = f"recorded snapshot ({fixture})"

    if args.json:
        print(json.dumps(
            {"proxy": proxy, "router_choices": arm, "choices": choices},
            indent=2, sort_keys=True, ensure_ascii=False,
        ))
        return 0

    labels = arm["labels"]
    delta = arm["total_cost_usd"] - proxy["total_cost_usd"]
    print(f"Azure Model Router — single-call choice  ({mode})")
    print(f"  tasks                 : {arm['tasks']}")
    print(f"  offline proxy pick    : ${proxy['total_cost_usd']:.6f}   "
          f"coverage {proxy['coverage']:.1%}  (difficulty-tiered, illustrative)")
    print(f"  router choices        : ${arm['total_cost_usd']:.6f}   "
          f"coverage {arm['coverage']:.1%}  (decisions: {labels['decisions']})")
    print(f"  Δ cost vs proxy       : {'+' if delta >= 0 else '-'}${abs(delta):.6f}")
    mix = arm["model_counts"]
    mix_str = ", ".join(f"{model}×{count}" for model, count in sorted(mix.items()))
    print(f"  chosen models         : {mix_str}")
    print(f"  labels                : measured={_yn(labels['measured'])}  "
          f"decisions={labels['decisions']}")
    if args.live:
        print("  → the CHOICE is a live decision; cost/coverage stay offline projections "
              "(measured=false).")
        print("    real 5-series names fall back to the proxy pick unless your policy/pricing "
              "use them.")
    else:
        print("  → cost/coverage are offline projections (measured=false); only the DECISIONS "
              "are a snapshot.")
    return 0


def _cmd_foundry_arena(args: argparse.Namespace) -> int:
    load_dotenv_file(args.env_file)
    workload = args.workload or DEFAULT_ARENA_WORKLOAD
    pricing_path = args.pricing or DEFAULT_FLEET_PRICING
    try:
        tasks = load_arena_tasks(workload)
        pricing = PricingTable.from_yaml(pricing_path)
    except (OSError, ValueError, KeyError) as exc:
        print(f"foundry arena: {exc}")
        return 1
    if not tasks:
        print(f"foundry arena: no prompt-bearing tasks in {workload}")
        return 1

    if not args.live:
        print("foundry arena: real head-to-head needs live calls. Re-run with --live once")
        print("  `cost-router foundry status` shows credentialed: yes (az login / Entra ID).")
        return 2

    config = FoundryConfig.from_env()
    if not config.credentialed:
        print("foundry arena: not credentialed — set AZURE_AI_FOUNDRY_* in .env, then `az login`.")
        return 1

    slate = FleetSlate()
    fleet = FoundryFleet.from_config(config, max_output_tokens=args.max_output_tokens)
    try:
        outcomes = run_live_arena(fleet, tasks, slate, pricing)
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"foundry arena: {exc}")
        return 1

    report = arena_report(outcomes, pricing)
    if args.ledger is not None:
        ledger = MeasuredArenaLedger(path=args.ledger, pricing=pricing)
        for outcome in outcomes:
            ledger.record(outcome)
        ledger.flush()
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
        )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    _print_arena_report(report, slate)
    return 0


def _print_arena_report(report: dict, slate: FleetSlate) -> None:
    labels = report["labels"]
    print("Azure AI Foundry — live arena (one problem, four ways)")
    print(f"  tasks     : {report['tasks']}   measured: {_yn(labels['measured'])}   "
          f"cost basis: {labels['cost_basis']}   accuracy: {labels['accuracy']}")
    print(f"  fleet     : cheapest={slate.cheapest}  premium={slate.premium}  "
          f"router={slate.router}")
    print(f"  ensemble  : {' + '.join(slate.ensemble)}")
    print("")
    header = f"  {'arm':9s} {'cost (real $)':>14s} {'avg latency':>12s}  billing"
    print(header)
    print(f"  {'-' * 9} {'-' * 14:>14s} {'-' * 11:>12s}  {'-' * 16}")
    billing = {
        "cheapest": "single-call",
        "premium": "single-call",
        "ensemble": "sum-all-fanout",
        "router": "winner-only",
    }
    for arm in ("cheapest", "premium", "ensemble", "router"):
        totals = report["arm_totals"][arm]
        print(f"  {arm:9s} {totals['total_cost_usd']:>14.6f} "
              f"{totals['avg_latency_ms']:>10.0f}ms  {billing[arm]}")
    print("")
    mix = ", ".join(f"{m}×{n}" for m, n in report["router_model_mix"].items())
    print(f"  router picked      : {mix}")
    print(f"  router vs premium  : {report['router_vs_premium_savings_pct']:.1f}% cheaper "
          f"(real usage, list-price basis)")
    print("  note: cost + latency are MEASURED; per-answer accuracy is ungraded "
          "(plug a grader to score correctness).")


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


def _compact_models(approach: dict[str, object]) -> str:
    models = [str(m) for m in (approach.get("models") or [])]
    key = approach.get("approach")
    if key == "router":
        return " → ".join(models) if models else "—"
    if key == "ensemble":
        head = models[0] if models else "?"
        return f"{len(models)} models ({head} +{len(models) - 1})" if len(models) > 1 else head
    chosen = approach.get("chosen_model")
    return str(chosen) if chosen else (models[0] if models else "—")


def format_compare_text(payload: dict[str, object]) -> str:
    """Render one task's head-to-head arena as an aligned CLI table."""

    arenas = payload["arenas"]  # type: ignore[index]
    task_id = payload["default"]  # type: ignore[index]
    arena = arenas[task_id]  # type: ignore[index]
    approaches = arena["approaches"]
    labels = {a["approach"]: a["label"] for a in approaches}

    lines = [
        "one problem, four ways   (measured = false)",
        f"task  {task_id}   class={arena['class']}   difficulty={arena['difficulty']}",
    ]
    lines += _format_problem_block(arena.get("problem"))
    lines += [
        "",
        f"{'approach':<19} {'model(s)':<28} {'cost':>11} {'latency*':>11}  result",
        f"{'-' * 19} {'-' * 28} {'-' * 11} {'-' * 11}  {'-' * 6}",
    ]
    winners = arena["winners"]
    axes = (("cost", "$"), ("latency", "@"))
    for a in approaches:
        marks = "".join(tag for axis, tag in axes if winners.get(axis) == a["approach"])
        result = "✓ pass" if a["passed"] else "✗ fail"
        lines.append(
            f"{a['label']:<19} {_compact_models(a):<28} "
            f"${a['cost_usd']:>10.6f} {a['latency_ms']:>9.0f}ms  {result} {marks}".rstrip()
        )
    acc = winners["accuracy"]
    acc_label = f"{len(acc)} of {len(approaches)} pass" if acc else "none pass"
    lines += [
        "",
        (
            f"winners   cost: {labels.get(winners['cost'], winners['cost'])}"
            f"   latency: {labels.get(winners['latency'], winners['latency'])}"
            f"   accuracy: {acc_label}"
        ),
        "note      latency is an illustrative projection (measured = false), not wall-clock.",
        "          $ = cheapest   @ = fastest   (accuracy is pass/fail per approach)",
    ]
    return "\n".join(lines)


def _format_problem_block(problem: dict[str, object] | None) -> list[str]:
    """Render the readable problem statement (title + prompt + acceptance)."""

    if not problem:
        return []
    title = str(problem.get("title") or "").strip()
    prompt = str(problem.get("prompt") or "").strip()
    acceptance = str(problem.get("acceptance") or "").strip()
    indent = " " * 10
    out: list[str] = []
    if title:
        out.append(f"problem   {title}")
    for line in textwrap.wrap(prompt, width=72) or []:
        out.append(indent + line)
    if acceptance:
        for i, line in enumerate(textwrap.wrap(acceptance, width=64)):
            out.append(indent + ("expect: " if i == 0 else "        ") + line)
    return out


def _cmd_compare(args: argparse.Namespace) -> int:
    payload = bundled_compare(task_id=args.task)
    if args.task and args.task not in payload["arenas"]:
        known = ", ".join(payload["arenas"])
        print(f"unknown task {args.task!r}; available: {known}")
        return 2
    if args.json:
        print(json.dumps(payload["arenas"][payload["default"]], ensure_ascii=False, indent=2))
        return 0
    print(format_compare_text(payload))
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
    if args.command == "ledger" and not getattr(args, "ledger_command", None):
        print("usage: cost-router ledger replay --ledger PATH")
        return 0
    if args.command == "experiment" and not getattr(args, "experiment_command", None):
        print("usage: cost-router experiment [list|run <name>]")
        return 0
    if args.command == "metrics" and not getattr(args, "metrics_command", None):
        print("usage: cost-router metrics [history --store PATH | emit <name>]")
        return 0
    if args.command == "foundry" and not getattr(args, "foundry_command", None):
        print("usage: cost-router foundry [status | live [--live] [--store PATH]]")
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
