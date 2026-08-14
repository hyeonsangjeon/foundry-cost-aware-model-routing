"""``cost-router`` command-line entry point.

Subcommands are thin wrappers over :mod:`router.pipeline`, so they share the
exact orchestration used by the sample scripts and the eval summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from .annotations import router_amount_text, router_cost_disclosure, savings_claim_allowed
from .baseline import single_call_summary
from .doctor import (
    ROUTING_MODE_API_VERSION,
    DoctorInputs,
    az_cli_available,
    evaluate_deployment_modes,
    run_doctor,
)
from .experiment import (
    format_experiment_list,
    format_experiment_text,
    list_experiments,
    load_experiment,
    run_experiment,
)
from .fleet import (
    LOCAL_FLEET_PATH,
    ROLE_LABELS,
    SINGLE_ROLES,
    FleetRegistry,
    save_fleet,
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
    DEFAULT_API_VERSION,
    AzureModelRouterClient,
    FoundryConfig,
    RecordedRouterClient,
    TransportTimeouts,
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
from .measure import (
    DEFAULT_N,
    DEFAULT_SNAPSHOT_ROOT,
    AzureMeasureClient,
    MeasureCandidate,
    MeasuredContract,
    RetryPolicy,
    build_catalog,
    build_publish_bundle,
    estimate_dry_run,
    evaluate_prereg,
    format_catalog,
    format_dry_run_table,
    load_prompt_workload,
    make_run_id,
    publish_bundle_json,
    replay_measure,
    run_measure,
    verify_contract,
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
from .pricing import PricingTable, format_usd, format_usd_avg
from .rate_card import RateCardError, RateCardV2
from .run_plan import (
    DEFAULT_LOCAL_CONFIG,
    SUPPORTED_LOCALES,
    ApprovalError,
    LocalRunConfig,
    PlanError,
    check_approval,
    execute_benchmark,
    resolve_run_plan,
    write_local_config,
)

# Bundled recorded provider-usage snapshot: replayed offline so `foundry live`
# demonstrates the measured scoring path with no credentials (measured=false).
DEFAULT_USAGE_FIXTURE = Path("samples/responses/model-router-usage.sample.json")

# Bundled recorded single-call *choices* snapshot: illustrative task->model picks
# replayed offline so `foundry router` demos the exp-07 comparison (measured=false).
DEFAULT_CHOICES_FIXTURE = Path("samples/responses/model-router-choices.sample.json")

# Live arena defaults: prompt-bearing curated workload + real fleet list prices.
DEFAULT_ARENA_WORKLOAD = Path("samples/telemetry/curated-arena-live.sample.jsonl")
DEFAULT_FLEET_PRICING = Path("samples/pricing/foundry-5series.yaml")

# Env vars that point at a rate card (kept in sync with foundry_live's resolver),
# honoured by `measure` so estimates price the same fleet .env selects.
PRICING_ENV_VARS: tuple[str, ...] = ("FOUNDRY_PRICING_PATH", "COST_ROUTER_PRICING")


def _resolve_pricing_path(explicit: Path | None) -> Path:
    """Rate card: explicit ``--pricing`` > ``FOUNDRY_PRICING_PATH`` > bundled default."""

    if explicit is not None:
        return explicit
    for var in PRICING_ENV_VARS:
        value = os.environ.get(var)
        if value:
            return Path(value)
    return DEFAULT_FLEET_PRICING


def _warn_legacy_config(command: str) -> None:
    """Emit a documented deprecation notice for the standalone env/flag config path.

    BOLT-03A makes the canonical :class:`~router.run_plan.ResolvedRunPlan`
    (``cost-router benchmark plan``) the single source of truth for preview,
    approval, run, manifest, and replay. The legacy per-command environment/flag
    configuration still works, but it is deprecated: it carries independent
    resolution semantics the canonical plan now owns. Written to stderr so it
    never contaminates ``--json`` stdout or a captured summary.
    """

    print(
        f"note: `cost-router {command}` uses the legacy environment/flag config path, "
        "deprecated by BOLT-03A in favor of the canonical run plan "
        "(`cost-router config init` then `cost-router benchmark plan --config "
        ".foundry.local.yaml`). See docs/ko/manual/run-plan.md.",
        file=sys.stderr,
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
    serve.add_argument(
        "--locale", choices=SUPPORTED_LOCALES, default=None,
        help="reserved presentation locale (en|ko); no execution effect — i18n owns behavior",
    )
    serve.set_defaults(func=_cmd_serve)

    dashboard = subparsers.add_parser(
        "dashboard",
        help="Serve the dashboard; --live adds the token-gated operator cockpit.",
    )
    dashboard.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1)")
    dashboard.add_argument(
        "--port", type=int, default=0,
        help="bind port (default: a random free port, for --live isolation)",
    )
    dashboard.add_argument("--policy", type=Path, default=None, help="policy YAML to serve")
    dashboard.add_argument(
        "--config", type=Path, default=None,
        help="bind a ResolvedRunPlan (.foundry.local.yaml) as the cockpit's single "
        "source of truth for preview/approval/run/replay (03A resolver; --live only)",
    )
    dashboard.add_argument(
        "--env-file", type=Path, default=Path(".env"),
        help="dotenv to load before reading Foundry config (for --live status/run)",
    )
    dashboard.add_argument(
        "--live", action="store_true",
        help="enable the localhost-only, session-token-gated live cockpit "
        "(the paid run still needs credentials + the operator's approve button)",
    )
    dashboard.add_argument(
        "--locale", choices=SUPPORTED_LOCALES, default=None,
        help="reserved presentation locale (en|ko); no execution effect — i18n owns behavior",
    )
    dashboard.set_defaults(func=_cmd_dashboard)

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
    _build_models_parser(subparsers)
    _build_measure_parser(subparsers)
    _build_config_parser(subparsers)
    _build_benchmark_parser(subparsers)
    _build_doctor_parser(subparsers)
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
    measured = ledger_sub.add_parser(
        "measured-replay",
        help="Verify a MEASURED ledger's hash chain and replay its recorded costs.",
    )
    measured.add_argument("--ledger", type=Path, required=True)
    measured.set_defaults(func=_cmd_ledger_measured_replay)


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
        "--fleet",
        type=Path,
        default=None,
        help="fleet config (which deployment plays each arm); default: FOUNDRY_FLEET_PATH "
        "or the bundled sample. Build one with `cost-router models select`.",
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


def _cmd_dashboard(args: argparse.Namespace) -> int:
    import secrets

    from . import server

    if not args.live:
        port = args.port or 8000
        return server.serve(host=args.host, port=port, policy_path=args.policy)

    # Live cockpit (C1): localhost only, random free port, session-token URL. The
    # token gates every /cockpit/* route; without --live the cockpit routes 404
    # and the public build ships no live surface. The paid run still needs Entra
    # credentials + the operator's "approve & run" click (server-side gates). The
    # .env is loaded first so status/catalog/run read the operator's Foundry
    # config (endpoint, deployment, fleet, pricing) just like `measure run`.
    load_dotenv_file(args.env_file)
    host = args.host
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "cost-router: --live binds localhost only; using 127.0.0.1 instead of "
            f"{host!r}.",
            flush=True,
        )
        host = "127.0.0.1"
    token = secrets.token_urlsafe(24)
    # 03C: --config binds one ResolvedRunPlan (03A resolver) as the cockpit's
    # single source of truth — preview, approval, run, abort, and replay all key
    # on its plan_hash. Without --config the cockpit falls back to the legacy
    # ad-hoc config path, which is deprecated (it kept independent config
    # semantics the resolver now owns).
    run_plan = run_config = None
    config_arg = getattr(args, "config", None)
    if config_arg is not None:
        run_config, run_plan = _resolve_plan_or_error(
            args, label="dashboard", require_run_ready=False
        )
        if run_plan is None:
            return 2
        print(
            f"cost-router: cockpit bound to plan {run_plan.plan_hash} "
            f"({run_plan.config_source}).",
            flush=True,
        )
    else:
        print(
            "cost-router: DEPRECATED — running the live cockpit without --config "
            "uses the legacy ad-hoc config path. Bind a resolved plan with "
            "`--config <.foundry.local.yaml>` so preview/approval/run/replay share "
            "one plan_hash; the plan-less path will be removed.",
            flush=True,
        )
    service = server.RouterService(
        policy=load_policy(args.policy),
        cockpit_token=token,
        run_plan=run_plan,
        run_config=run_config,
    )
    port = args.port or (49152 + secrets.randbelow(16000))
    open_hint = f"/?cockpit=1&token={token}"
    print("cost-router: live cockpit enabled (localhost, token-gated).", flush=True)
    return server.serve(host=host, port=port, service=service, open_hint=open_hint)


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


def _cmd_ledger_measured_replay(args: argparse.Namespace) -> int:
    from .ledger import MeasuredJsonlLedger, verify_measured_records

    try:
        records = MeasuredJsonlLedger(args.ledger).read_all()
        report = verify_measured_records(records)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}")
        print("status: FAIL")
        return 1
    arms = {
        str(name).strip().lower()
        for record in records
        for name in (record.outcome.get("arms") or {})
    }
    # A replay that re-derives a Model Router amount asserts that amount is
    # sound. Without a valid annotation covering the router arm that assertion
    # cannot be made, so the replay fails closed instead of printing PASS.
    disclosure = router_cost_disclosure()
    affected = sorted(arms & {str(a).strip().lower() for a in disclosure["affected_arms"]})
    if affected and not disclosure["annotation_available"]:
        print(f"error: {disclosure['error']}")
        print("status: FAIL")
        return 1
    print(f"records: {report.records}")
    print(f"replayed: {report.replayed}")
    print("  → each recorded call cost re-derived from its usage × the pinned rate card")
    if affected:
        print(f"  → {', '.join(affected)} arm cost is {disclosure['label']}")
        print(f"     {disclosure['short']}")
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
            f"routed={format_usd(float(row.get('routed_usd', 0.0)))} "
            f"saved={float(row.get('delta_pct', 0.0)):.1%} "
            f"fanout_tax={format_usd(float(row.get('ensemble_tax_usd', 0.0)))} "
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
    _warn_legacy_config("foundry live")

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
    disclosure = summary.get("router_cost_disclosure") or router_cost_disclosure()
    print(f"Azure Model Router — measured usage  ({mode})")
    print(f"  tasks             : {summary['tasks']}")
    print(f"  routed cost†      : "
          f"{router_amount_text(disclosure, summary['total_cost_usd'], format_usd)}")
    print(f"  avg $/task†       : "
          f"{router_amount_text(disclosure, summary['avg_usd_per_task'], format_usd_avg)}")
    coverage = summary["coverage"]
    if coverage is None:
        print(f"  coverage          : ungraded ({labels['coverage_basis']} — "
              "usage is measured, correctness needs a grader)")
    else:
        cov_kind = "measured" if labels["coverage_measured"] else "projected"
        print(f"  coverage ({cov_kind}): {coverage:.1%}")
    print(f"  spend source      : {labels['spend_source']}")
    print(f"  provenance        : {labels['provenance']}")
    print(f"  measured          : {_yn(labels['measured'])}")
    print(f"  † {disclosure['short']}")
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

    proxy = single_call_summary(workload, signals, policy, pricing)

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
    print(f"  offline proxy pick    : {format_usd(proxy['total_cost_usd'])}   "
          f"coverage {proxy['coverage']:.1%}  (difficulty-tiered, illustrative)")
    print(f"  router choices        : {format_usd(arm['total_cost_usd'])}   "
          f"coverage {arm['coverage']:.1%}  (decisions: {labels['decisions']})")
    print(f"  Δ cost vs proxy       : {'+' if delta >= 0 else '-'}{format_usd(abs(delta))}")
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
    _warn_legacy_config("foundry arena")
    workload = args.workload or DEFAULT_ARENA_WORKLOAD
    pricing_path = args.pricing or DEFAULT_FLEET_PRICING
    try:
        tasks = load_arena_tasks(workload)
        pricing = PricingTable.from_yaml(pricing_path)
        registry = FleetRegistry.resolve(args.fleet)
        slate = registry.slate()
    except (OSError, ValueError, KeyError) as exc:
        print(f"foundry arena: {exc}")
        return 1
    if not tasks:
        print(f"foundry arena: no prompt-bearing tasks in {workload}")
        return 1

    if not args.live:
        print(f"foundry arena: fleet '{registry.source}'")
        print(f"  router={slate.router}  cheapest={slate.cheapest}  premium={slate.premium}")
        print(f"  ensemble={' + '.join(slate.ensemble)}")
        print("foundry arena: real head-to-head needs live calls. Re-run with --live once")
        print("  `cost-router foundry status` shows credentialed: yes (az login / Entra ID).")
        return 2

    config = FoundryConfig.from_env()
    if not config.credentialed:
        print("foundry arena: not credentialed — set AZURE_AI_FOUNDRY_* in .env, then `az login`.")
        return 1

    fleet = FoundryFleet.from_config(
        config, max_output_tokens=args.max_output_tokens, providers=slate.providers
    )
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
        appended = ledger.flush()
        from .ledger import verify_measured_ledger

        verified = verify_measured_ledger(args.ledger)
        status = "OK" if verified.ok else "FAIL"
        print(
            f"ledger: +{appended} measured row(s) → {args.ledger} "
            f"(hash-chain + cost-replay: {status})"
        )
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
    disclosure = report.get("router_cost_disclosure") or router_cost_disclosure()
    affected = set(disclosure.get("affected_arms") or ("router",))
    print("Azure AI Foundry — live arena (one problem, four ways)")
    print(f"  tasks     : {report['tasks']}   measured: {_yn(labels['measured'])}   "
          f"cost basis: {labels['cost_basis']}   accuracy: {labels['accuracy']}")
    print(f"  fleet     : cheapest={slate.cheapest}  premium={slate.premium}  "
          f"router={slate.router}")
    print(f"  ensemble  : {' + '.join(slate.ensemble)}")
    print("")
    header = f"  {'arm':9s} {'cost (list $)':>15s} {'avg latency':>12s}  billing"
    print(header)
    print(f"  {'-' * 9} {'-' * 15:>15s} {'-' * 11:>12s}  {'-' * 16}")
    billing = {
        "cheapest": "single-call",
        "premium": "single-call",
        "ensemble": "sum-all-fanout",
        "router": "winner-only",
    }
    for arm in ("cheapest", "premium", "ensemble", "router"):
        totals = report["arm_totals"][arm]
        if arm in affected:
            cell = router_amount_text(
                disclosure, totals["total_cost_usd"], format_usd, compact=True
            ) + "†"
        else:
            cell = format_usd(totals["total_cost_usd"]) + " "
        print(f"  {arm:9s} {cell:>15s} "
              f"{totals['avg_latency_ms']:>10.0f}ms  {billing[arm]}")
    print("")
    mix = ", ".join(f"{m}×{n}" for m, n in report["router_model_mix"].items())
    print(f"  router picked      : {mix}")
    savings = report.get("router_vs_premium_savings_pct")
    if savings is None or not savings_claim_allowed(disclosure):
        print(f"  router vs premium  : {disclosure['withheld']}")
    else:
        print(f"  router vs premium  : {savings:.1f}% cheaper "
              f"(real usage, list-price basis)")
    print(f"  † {disclosure['short']}")
    unaffected = disclosure.get("unaffected_arms") or []
    if unaffected:
        print(f"    unaffected (direct-model, never charged the markup): {', '.join(unaffected)}")
    print("  note: usage + latency are MEASURED; per-answer accuracy is ungraded "
          "(plug a grader to score correctness).")


def _build_models_parser(subparsers: argparse._SubParsersAction) -> None:
    models = subparsers.add_parser(
        "models",
        help="Register & select the fleet — which deployed model plays each arm.",
    )
    models_sub = models.add_subparsers(dest="models_command")

    def _fleet_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--fleet",
            type=Path,
            default=None,
            help="fleet config to load (default: FOUNDRY_FLEET_PATH or the bundled sample)",
        )

    listing = models_sub.add_parser("list", help="Show the model catalog and current slate.")
    _fleet_arg(listing)
    listing.add_argument("--json", action="store_true", help="print the catalog as JSON")
    listing.set_defaults(func=_cmd_models_list)

    show = models_sub.add_parser("show", help="Show the resolved slate (roles -> deployments).")
    _fleet_arg(show)
    show.add_argument("--json", action="store_true", help="print the slate as JSON")
    show.set_defaults(func=_cmd_models_show)

    select = models_sub.add_parser(
        "select",
        help="Pick which model plays each arm (interactive menu or flags); saves a local fleet.",
    )
    _fleet_arg(select)
    select.add_argument("--router", default=None, help="model name for the router (main) arm")
    select.add_argument("--cheapest", default=None, help="model name for the cheapest arm")
    select.add_argument("--premium", default=None, help="model name for the premium arm")
    select.add_argument(
        "--ensemble", default=None, help="comma-separated model names for the ensemble/fan-out arm"
    )
    select.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"where to save the selected fleet (default: {LOCAL_FLEET_PATH})",
    )
    select.add_argument(
        "--non-interactive",
        action="store_true",
        help="never prompt; apply flags/current values only",
    )
    select.add_argument("--json", action="store_true", help="also print the saved fleet as JSON")
    select.set_defaults(func=_cmd_models_select)


def _build_measure_parser(subparsers: argparse._SubParsersAction) -> None:
    measure = subparsers.add_parser(
        "measure",
        help="Measured live runs → fingerprinted snapshots + credential-free replay (BOLT).",
    )
    measure_sub = measure.add_subparsers(dest="measure_command")

    run = measure_sub.add_parser(
        "run",
        help="Dry-run cost table, then (with --live) a measured sweep into a §3 snapshot.",
    )
    run.add_argument("experiment", help="experiment id (labels the snapshot)")
    run.add_argument("--n", type=int, default=DEFAULT_N, help="repeats per cell")
    run.add_argument("--budget-usd", type=float, default=None, help="hard cost cap; halts")
    run.add_argument("--workload", type=Path, default=None, help="prompt-bearing JSONL")
    run.add_argument("--pricing", type=Path, default=None, help="rate card YAML")
    run.add_argument("--fleet", type=Path, default=None, help="fleet config for candidates")
    run.add_argument("--candidates", default=None, help="comma-separated models to measure")
    run.add_argument("--out-root", type=Path, default=DEFAULT_SNAPSHOT_ROOT, help="snapshot root")
    run.add_argument("--run-id", default=None, help="explicit run id")
    run.add_argument("--resume", default=None, metavar="RUN_ID", help="resume a run id")
    run.add_argument("--prereg", type=Path, default=None, help="prereg.md path")
    run.add_argument("--allow-no-prereg", action="store_true", help="bypass D8 prereg gate")
    run.add_argument("--region", default=None, help="Azure region label")
    run.add_argument("--max-output-tokens", type=int, default=2048, help="per-call completion cap")
    run.add_argument("--live", action="store_true", help="make REAL Azure calls")
    run.add_argument("--yes", action="store_true", help="skip dry-run confirmation")
    run.add_argument("--json", action="store_true", help="print summary as JSON")
    run.add_argument("--env-file", type=Path, default=Path(".env"), help="dotenv to load first")
    run.set_defaults(func=_cmd_measure_run)

    replay = measure_sub.add_parser(
        "replay",
        help="Recompute a snapshot's summary byte-for-byte from its traces (no credentials).",
    )
    replay.add_argument("--run", type=Path, required=True, help="snapshot run directory")
    replay.add_argument("--json", action="store_true", help="print the replay report as JSON")
    replay.set_defaults(func=_cmd_measure_replay)

    verify = measure_sub.add_parser(
        "verify",
        help="Check a measured snapshot against a range/floor contract (deterministic).",
    )
    verify.add_argument("--run", type=Path, required=True, help="snapshot run directory")
    verify.add_argument("--contract", type=Path, default=None, help="contract YAML (floors/bands)")
    verify.add_argument("--json", action="store_true", help="print the checks as JSON")
    verify.set_defaults(func=_cmd_measure_verify)

    catalog = measure_sub.add_parser(
        "catalog",
        help="Pre-flight: show every prompt, validation rule, candidate + cost — NO live calls.",
    )
    catalog.add_argument("experiment", nargs="?", default="(preview)", help="experiment id label")
    catalog.add_argument("--workload", type=Path, default=None, help="prompt-bearing JSONL")
    catalog.add_argument("--pricing", type=Path, default=None, help="rate card YAML")
    catalog.add_argument("--fleet", type=Path, default=None, help="fleet config for candidates")
    catalog.add_argument("--candidates", default=None, help="comma-separated models")
    catalog.add_argument("--n", type=int, default=DEFAULT_N, help="repeats per cell (for estimate)")
    catalog.add_argument("--budget-usd", type=float, default=None, help="budget cap to check")
    catalog.add_argument("--json", action="store_true", help="print the catalog as JSON")
    catalog.add_argument("--env-file", type=Path, default=Path(".env"), help="dotenv to load first")
    catalog.set_defaults(func=_cmd_measure_catalog)

    publish = measure_sub.add_parser(
        "publish",
        help="Turn a sealed snapshot into a public-mockup bundle (tenant rates masked).",
    )
    publish.add_argument("--run", type=Path, required=True, help="snapshot run directory")
    publish.add_argument(
        "--out", type=Path, default=None,
        help="write the bundle here (default: results/published/<exp>/<run-id>.json)",
    )
    publish.add_argument("--json", action="store_true", help="print the bundle to stdout")
    publish.set_defaults(func=_cmd_measure_publish)


def _measure_candidates(args: argparse.Namespace) -> tuple[list[MeasureCandidate], str]:
    """Resolve the candidate models to measure (explicit --candidates or fleet slate)."""

    if args.candidates:
        names = [name.strip() for name in str(args.candidates).split(",") if name.strip()]
        return [MeasureCandidate(model=name, deployment=name) for name in names], "flag"
    registry = FleetRegistry.resolve(args.fleet)
    slate = registry.slate()
    candidates = [
        MeasureCandidate(model=dep, deployment=dep, provider=slate.provider_for(dep))
        for dep in slate.ensemble
    ]
    return candidates, registry.source


def _redact_endpoint_host(endpoint: str | None) -> str | None:
    if not endpoint:
        return None
    from urllib.parse import urlsplit

    parts = urlsplit(endpoint)
    return f"{parts.scheme}://{parts.netloc}" if parts.netloc else "set"


def _git_head() -> str | None:
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        )
    except (OSError, ValueError):  # pragma: no cover - git absent
        return None
    head = out.stdout.strip()
    return head or None


def _cmd_measure_run(args: argparse.Namespace) -> int:
    load_dotenv_file(args.env_file)
    _warn_legacy_config("measure run")
    workload_path = args.workload or DEFAULT_ARENA_WORKLOAD
    pricing_path = _resolve_pricing_path(args.pricing)
    try:
        workload = load_prompt_workload(workload_path)
        pricing = PricingTable.from_yaml(pricing_path)
        candidates, source = _measure_candidates(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"measure run: {exc}")
        return 1
    if not workload:
        print(f"measure run: no prompt-bearing tasks in {workload_path}")
        return 1
    if not candidates:
        print("measure run: no candidates — set --candidates or a fleet with an ensemble slate.")
        return 1

    estimate = estimate_dry_run(workload, candidates, n=args.n, pricing=pricing)
    print(f"measure run: experiment '{args.experiment}'  fleet '{source}'")
    print(format_dry_run_table(estimate, budget_usd=args.budget_usd))
    print("")

    if not args.live:
        print("measure run: this printed ESTIMATES only — no live calls were made.")
        print("  Re-run with --live (and --budget-usd) once an operator approves the spend.")
        print("  `cost-router foundry status` must show credentialed: yes (az login / Entra ID).")
        return 2

    # --- live path (operator-gated; never exercised by CI/tests) --------------
    if args.budget_usd is None:  # pragma: no cover - live guard
        print("measure run --live: refusing without --budget-usd (set a cap from the estimate).")
        return 1
    config = FoundryConfig.from_env()
    if not config.credentialed:  # pragma: no cover - live guard
        print(
            "measure run --live: not credentialed; set AZURE_AI_FOUNDRY_* in .env, then `az login`."
        )
        return 1

    out_root = args.out_root
    run_id = args.resume or args.run_id or make_run_id()
    run_dir = out_root / args.experiment / run_id
    prereg_path = args.prereg or (out_root / args.experiment / "prereg.md")
    started = _utc_now()
    decision = evaluate_prereg(
        prereg_path, run_started_at=started, allow_no_prereg=args.allow_no_prereg
    )
    if not decision.allowed:  # pragma: no cover - live guard
        print(f"measure run --live: prereg gate blocked the run — {decision.note}")
        return 1
    if not args.yes and not _confirm_live(  # pragma: no cover - interactive
        estimate, args.budget_usd
    ):
        print("measure run --live: cancelled (no --yes confirmation).")
        return 1

    client = AzureMeasureClient(
        AzureModelRouterClient(config=config, max_output_tokens=args.max_output_tokens)
    )
    try:  # pragma: no cover - live path
        result = run_measure(
            workload, candidates, client=client, pricing=pricing,
            exp_id=args.experiment, run_dir=run_dir, run_id=run_id, n=args.n,
            budget_usd=args.budget_usd, retry=RetryPolicy(), prereg=decision,
            git_commit=_git_head(), endpoint=_redact_endpoint_host(config.endpoint),
            region=args.region, pricing_path=str(pricing_path),
            resume=bool(args.resume), now=started,
        )
    except (RuntimeError, ValueError, KeyError, OSError) as exc:
        print(f"measure run --live: {exc}")
        return 1
    if args.json:  # pragma: no cover - live path
        print(json.dumps(result.summary, indent=2, sort_keys=True, ensure_ascii=False))
    else:  # pragma: no cover - live path
        _print_measure_summary(result)
    return 0


def _cmd_measure_catalog(args: argparse.Namespace) -> int:
    load_dotenv_file(args.env_file)
    _warn_legacy_config("measure catalog")
    workload_path = args.workload or DEFAULT_ARENA_WORKLOAD
    pricing_path = _resolve_pricing_path(args.pricing)
    try:
        workload = load_prompt_workload(workload_path)
        pricing = PricingTable.from_yaml(pricing_path)
        candidates, source = _measure_candidates(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"measure catalog: {exc}")
        return 1
    if not workload:
        print(f"measure catalog: no prompt-bearing tasks in {workload_path}")
        return 1
    if not candidates:
        print("measure catalog: no candidates — set --candidates or a fleet with an ensemble.")
        return 1

    catalog = build_catalog(workload, candidates, n=args.n, pricing=pricing)
    if args.json:
        print(json.dumps(catalog, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    print(f"measure catalog: experiment '{args.experiment}'  workload '{workload_path}'  "
          f"fleet '{source}'")
    print(format_catalog(catalog, budget_usd=args.budget_usd))
    print("")
    print("measure catalog: preview only — no live calls. Run `measure run --live` to spend.")
    return 0


def _cmd_measure_replay(args: argparse.Namespace) -> int:
    try:
        report = replay_measure(args.run)
    except (OSError, ValueError, KeyError) as exc:
        print(f"measure replay: {exc}")
        print("status: FAIL")
        return 1
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
        return 0 if report.ok else 1
    print(f"measure replay: {args.run}")
    print(f"  summary byte-identical : {_yn(report.summary_matches)}")
    print(f"  file fingerprints match: {_yn(report.fingerprints_ok)}")
    print("  → each recorded call cost re-derived from its usage × the pinned rate card")
    if report.cost_mismatches:
        print(f"  cost mismatches        : {len(report.cost_mismatches)}")
    if report.fingerprint_issues:
        print(f"  fingerprint issues     : {', '.join(report.fingerprint_issues)}")
    print(f"status: {'PASS' if report.ok else 'FAIL'}")
    return 0 if report.ok else 1


def _cmd_measure_publish(args: argparse.Namespace) -> int:
    try:
        bundle = build_publish_bundle(args.run)
        text = publish_bundle_json(args.run)
    except (OSError, ValueError, KeyError) as exc:
        print(f"measure publish: {exc}")
        print("status: FAIL")
        return 1
    if args.json:
        print(text)
        return 0
    out = args.out
    if out is None:
        out = DEFAULT_SNAPSHOT_ROOT.parent / "published" / str(bundle["exp_id"]) / (
            str(bundle["run_id"]) + ".json"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(f"measure publish: {args.run}")
    print(f"  → wrote {out}")
    print(f"  measured={bundle['provenance']['measured']}  "
          f"n={bundle['n']}  commit={bundle['git_commit']}  "
          f"captured={bundle['captured_at']}")
    print("  tenant rate card masked — absolute unit prices not published.")
    print("  commit this bundle yourself once you have reviewed it.")
    return 0


def _cmd_measure_verify(args: argparse.Namespace) -> int:
    import yaml

    run_dir = args.run
    try:
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"measure verify: {exc}")
        return 1
    contract_data: dict = {}
    if args.contract is not None:
        try:
            contract_data = yaml.safe_load(args.contract.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError) as exc:
            print(f"measure verify: {exc}")
            return 1
    contract = MeasuredContract.from_dict(contract_data.get("expect", contract_data))
    checks = verify_contract(summary, contract, manifest=manifest)
    if args.json:
        print(json.dumps([c.to_dict() for c in checks], indent=2, ensure_ascii=False))
    else:
        print(f"measure verify: {run_dir}")
        for check in checks:
            print(f"  {'PASS' if check.ok else 'WARN/FAIL'}  {check.name}: {check.detail}")
    # Freshness is advisory (a warning), so it never fails the gate on its own.
    hard = [c for c in checks if c.name != "freshness"]
    ok = all(c.ok for c in hard)
    print(f"status: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def _print_measure_summary(result) -> None:  # pragma: no cover - live path
    summary = result.summary
    labels = summary["labels"]
    print("cost-router measure — measured snapshot")
    print(f"  snapshot : {result.run_dir}")
    print(f"  measured : {_yn(labels['measured'])}   partial: {_yn(labels['partial'])}   "
          f"accuracy: {labels['accuracy']}")
    print(f"  calls    : {summary['calls']}/{summary['attempts']} ok   tasks: {summary['tasks']}   "
          f"n: {summary['n']}")
    print(f"  cost     : {format_usd(summary['cost']['total_usd'])}  "
          f"(best {summary['cost']['best_model']} vs naive {summary['cost']['naive_model']}: "
          f"{summary['cost']['savings_pct']:.1f}% cheaper)")
    throttle = summary["throttle"]
    print(f"  throttle : 429×{throttle['http_429']}  retries {throttle['retries']}  "
          f"exhausted {throttle['throttle_exhausted']}")
    print("  replay   : cost-router measure replay --run " + str(result.run_dir))


def _confirm_live(estimate, budget_usd: float) -> bool:  # pragma: no cover - interactive
    import sys

    if not sys.stdin.isatty():
        return False
    reply = input(f"Proceed with LIVE calls (est {format_usd(estimate['est_total_usd'])}, "
                  f"cap {format_usd(budget_usd)})? [y/N] ").strip().lower()
    return reply in {"y", "yes"}


def _utc_now():
    from datetime import UTC, datetime

    return datetime.now(UTC)


def _resolve_fleet_registry(args: argparse.Namespace) -> FleetRegistry | None:
    """Load the fleet for a `models` command (honouring FOUNDRY_FLEET_PATH via .env)."""

    load_dotenv_file(Path(".env"))
    try:
        return FleetRegistry.resolve(args.fleet)
    except (OSError, ValueError, KeyError) as exc:
        print(f"models: {exc}")
        return None


def _print_slate(registry: FleetRegistry) -> None:
    names = registry.model_names()
    print("  current slate")
    for role in SINGLE_ROLES:
        assigned = getattr(registry, role)
        dep = registry.deployment_for(assigned) if assigned in names else "?"
        print(f"    {ROLE_LABELS[role]:<18}: {assigned or '(unassigned)'}  ->  {dep}")
    print(f"    {ROLE_LABELS['ensemble']:<18}: {' + '.join(registry.ensemble) or '(empty)'}")


def _fleet_source_path(registry: FleetRegistry) -> str:
    if registry.source and registry.source != "bundled default":
        return registry.source
    return "samples/fleet/foundry-5series.fleet.yaml"


def _print_models_list(registry: FleetRegistry) -> None:
    config = FoundryConfig.from_env()
    print(f"fleet  (source: {registry.source})   credentialed: {_yn(config.credentialed)}")
    print("")
    print(f"  {'#':>2}  {'name':<16} {'deployment':<18} {'tier':<9} {'surface':<8} roles")
    print(f"  {'-' * 2}  {'-' * 16} {'-' * 18} {'-' * 9} {'-' * 8} {'-' * 22}")
    for index, model in enumerate(registry.models, start=1):
        roles = ", ".join(registry.roles_for(model.name)) or "-"
        print(
            f"  {index:>2}  {model.name:<16} {model.deployment:<18} "
            f"{(model.tier or '-'):<9} {model.provider:<8} {roles}"
        )
    print("")
    _print_slate(registry)
    print("")
    print("select:   cost-router models select                       # interactive /model picker")
    print("          cost-router models select --premium <name> --ensemble a,b,c")
    print(f"run live: cost-router foundry arena --fleet {_fleet_source_path(registry)} --live")


def _cmd_models_list(args: argparse.Namespace) -> int:
    registry = _resolve_fleet_registry(args)
    if registry is None:
        return 1
    if args.json:
        payload = {
            "source": registry.source,
            "models": registry.catalog_view(),
            "roles": registry.role_assignments(),
            "credentialed": FoundryConfig.from_env().credentialed,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    _print_models_list(registry)
    return 0


def _cmd_models_show(args: argparse.Namespace) -> int:
    registry = _resolve_fleet_registry(args)
    if registry is None:
        return 1
    errors = registry.validation_errors()
    if args.json:
        slate = None if errors else registry.slate()
        payload = {
            "source": registry.source,
            "roles": registry.role_assignments(),
            "slate": None
            if slate is None
            else {
                "router": slate.router,
                "cheapest": slate.cheapest,
                "premium": slate.premium,
                "ensemble": list(slate.ensemble),
            },
            "valid": not errors,
            "errors": errors,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if not errors else 1
    if errors:
        print("models show: invalid fleet:")
        for error in errors:
            print(f"  - {error}")
        return 1
    _print_slate(registry)
    return 0


def _resolve_model_choice(
    raw: str, registry: FleetRegistry
) -> str | None:
    """Map a picker entry (number, name, or ``/model <x>``) to a catalog name."""

    text = raw.strip()
    if text.startswith("/model"):
        text = text[len("/model") :].strip()
    if not text:
        return None
    names = registry.model_names()
    if text.isdigit():
        index = int(text)
        if 1 <= index <= len(registry.models):
            return registry.models[index - 1].name
        raise ValueError(f"choice {index} is out of range 1..{len(registry.models)}")
    if text in names:
        return text
    raise ValueError(f"unknown model {text!r}")


def _interactive_select(registry: FleetRegistry) -> FleetRegistry | None:
    import sys

    if not sys.stdin.isatty():
        print(
            "models select: no interactive terminal — pass "
            "--router/--cheapest/--premium/--ensemble or --non-interactive."
        )
        return None
    print("pick a model for each arm — enter a number or name (blank keeps current):")
    print("")
    for index, model in enumerate(registry.models, start=1):
        extra = f" · {model.tier}" if model.tier else ""
        print(f"  {index}. {model.name}  ->  {model.deployment}{extra}")
    print("")
    changes: dict[str, object] = {}
    for role in SINGLE_ROLES:
        current = getattr(registry, role)
        try:
            raw = input(f"  {ROLE_LABELS[role]} [{current}]: ")
        except EOFError:
            return None
        choice = _resolve_model_choice(raw, registry)
        changes[role] = choice if choice is not None else current
    current_ensemble = ", ".join(registry.ensemble)
    try:
        raw = input(f"  {ROLE_LABELS['ensemble']} [{current_ensemble}]: ")
    except EOFError:
        return None
    text = raw.strip()
    if text.startswith("/model"):
        text = text[len("/model") :].strip()
    if text:
        members = [
            choice
            for part in text.split(",")
            if (choice := _resolve_model_choice(part, registry)) is not None
        ]
        changes["ensemble"] = members
    return registry.with_roles(**changes)


def _cmd_models_select(args: argparse.Namespace) -> int:
    registry = _resolve_fleet_registry(args)
    if registry is None:
        return 1
    flags_given = any(
        value is not None for value in (args.router, args.cheapest, args.premium, args.ensemble)
    )
    try:
        if flags_given or args.non_interactive:
            ensemble = None
            if args.ensemble is not None:
                ensemble = [part.strip() for part in args.ensemble.split(",") if part.strip()]
            registry = registry.with_roles(
                router=args.router,
                cheapest=args.cheapest,
                premium=args.premium,
                ensemble=ensemble,
            )
        else:
            picked = _interactive_select(registry)
            if picked is None:
                print("models select: aborted — nothing saved.")
                return 1
            registry = picked
    except (ValueError, KeyError) as exc:
        print(f"models select: {exc}")
        print(f"  available models: {', '.join(registry.model_names())}")
        return 1
    out = args.out or LOCAL_FLEET_PATH
    saved = save_fleet(registry, out)
    print(f"saved fleet -> {saved}")
    print("")
    _print_slate(registry)
    print("")
    print(f"run it live: cost-router foundry arena --fleet {saved} --live")
    if args.json:
        print(json.dumps(registry.to_dict(), indent=2, ensure_ascii=False))
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
        print("")
        print("booting the offline dashboard (Ctrl-C to stop) — auto-runs on open", flush=True)
    return server.serve(host=args.host, port=args.port, open_hint="/?run=1")


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
            f"{format_usd(a['cost_usd']):>11s} {a['latency_ms']:>9.0f}ms  {result} {marks}".rstrip()
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


# --------------------------------------------------------------------------- #
# Canonical run plan — config init, benchmark plan/smoke/run (BOLT-03A)
# --------------------------------------------------------------------------- #


def _add_locale_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--locale",
        choices=SUPPORTED_LOCALES,
        default=None,
        help="reserved presentation locale (en|ko); excluded from plan_hash — i18n owns behavior",
    )


def _build_config_parser(subparsers: argparse._SubParsersAction) -> None:
    config = subparsers.add_parser(
        "config",
        help="Canonical local run config — scaffold a placeholder .foundry.local.yaml.",
    )
    config_sub = config.add_subparsers(dest="config_command")

    init = config_sub.add_parser(
        "init",
        help="Write a placeholder .foundry.local.yaml from the committed template (no secrets).",
    )
    init.add_argument(
        "--output", type=Path, default=Path(DEFAULT_LOCAL_CONFIG),
        help=f"where to write the local config (default: {DEFAULT_LOCAL_CONFIG})",
    )
    init.add_argument(
        "--force", action="store_true", help="overwrite an existing file",
    )
    init.set_defaults(func=_cmd_config_init)


def _build_benchmark_parser(subparsers: argparse._SubParsersAction) -> None:
    benchmark = subparsers.add_parser(
        "benchmark",
        help="Resolve one canonical run plan, then preview/approve/run it (offline by default).",
    )
    benchmark_sub = benchmark.add_subparsers(dest="benchmark_command")

    plan = benchmark_sub.add_parser(
        "plan",
        help="Resolve + print the redacted plan and its deterministic plan_hash. Zero egress.",
    )
    _add_plan_args(plan)
    plan.set_defaults(func=_cmd_benchmark_plan)

    smoke = benchmark_sub.add_parser(
        "smoke",
        help="Wiring-only one-call check. Previews the plan; --live needs --approve-plan.",
    )
    _add_plan_args(smoke)
    _add_live_args(smoke)
    smoke.set_defaults(func=_cmd_benchmark_smoke)

    run = benchmark_sub.add_parser(
        "run",
        help="Full measured sweep. Previews the plan; --live needs --approve-plan.",
    )
    _add_plan_args(run)
    _add_live_args(run)
    run.set_defaults(func=_cmd_benchmark_run)


def _add_plan_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config", type=Path, default=Path(DEFAULT_LOCAL_CONFIG),
        help=f"canonical run config (default: {DEFAULT_LOCAL_CONFIG})",
    )
    parser.add_argument(
        "--budget-usd", type=float, default=None,
        help="override the config's budget_usd (CLI wins over YAML)",
    )
    parser.add_argument(
        "--max-output-tokens", type=int, default=None,
        help="override the config's benchmark.max_output_tokens (CLI wins over YAML)",
    )
    parser.add_argument("--json", action="store_true", help="print the resolved plan as JSON")
    _add_locale_arg(parser)


def _add_live_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--live", action="store_true",
        help="make REAL Azure calls (requires credentials AND a matching --approve-plan)",
    )
    parser.add_argument(
        "--approve-plan", default=None, metavar="PLAN_HASH",
        help="the plan_hash printed by `benchmark plan`; a stale/mismatched value is rejected",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="dotenv to load first")
    parser.add_argument("--region", default=None, help="Azure region label for the manifest")


def _plan_overrides(args: argparse.Namespace) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if getattr(args, "budget_usd", None) is not None:
        overrides["budget_usd"] = args.budget_usd
    if getattr(args, "max_output_tokens", None) is not None:
        overrides["max_output_tokens"] = args.max_output_tokens
    return overrides


def _cmd_config_init(args: argparse.Namespace) -> int:
    try:
        out = write_local_config(args.output, force=args.force)
    except PlanError as exc:
        print(f"config init: {exc}")
        return 1
    print(f"config init: wrote {out} (placeholder template — no secrets).")
    print("  Next: fill in your endpoint + local paths, set `template: false`, then")
    print(f"        cost-router benchmark plan --config {out}")
    return 0


def _resolve_plan_or_error(
    args: argparse.Namespace, *, label: str, require_run_ready: bool
):
    """Resolve a plan for a CLI command, printing a ``label:`` error on failure."""

    try:
        config = LocalRunConfig.from_yaml(args.config)
        plan = resolve_run_plan(
            config,
            cli_overrides=_plan_overrides(args),
            cli_locale=getattr(args, "locale", None),
            require_run_ready=require_run_ready,
        )
    except PlanError as exc:
        print(f"{label}: {exc}")
        return None, None
    return config, plan


def _print_plan(plan) -> None:
    """Print the full redacted plan, then the human-approval summary."""

    ex = plan.execution
    print(f"resolved run plan   ({plan.config_source})")
    print(f"  plan_hash         : {plan.plan_hash}")
    print(f"  live_ready        : {_yn(plan.live_ready)}")
    print(f"  run_mode          : {ex['run_mode']}")
    endpoint = ex["endpoint"]
    print(f"  endpoint          : {endpoint['data_plane'] or '(unset — template/placeholder)'} "
          f"[{endpoint['dialect']}, auth={endpoint['auth_mode']}, api={endpoint['api_version']}]")
    print("  arms              :")
    for arm in ex["arms"]:
        print(f"    - {arm['id']}  ({arm['kind']}, provider={arm['provider']}, "
              f"deployment={arm['deployment']})")
    workload = ex["workload"]
    print(f"  workload          : {workload['path']}  {workload['fingerprint']}")
    pricing = ex["pricing"]
    if pricing["rate_card_path"]:
        print(f"  rate card         : {pricing['rate_card_path']}  v{pricing['schema_version']} "
              f"{pricing['currency']}  {pricing['fingerprint']}")
    print(f"  authorization     : {pricing['authorization_basis']}"
          + (f"  (ceiling ${pricing['smoke_authorization_ceiling_usd']:.2f})"
             if pricing["smoke_authorization_ceiling_usd"] is not None else ""))
    print(f"  budget            : {format_usd(plan.budget_usd)}")
    print(f"  grader            : {ex['grader']['kind']} v{ex['grader']['version']}")
    print(f"  locale (display)  : {plan.locale}  (source={plan.presentation['locale_source']}; "
          "not in plan_hash)")
    _print_approval_view(plan)
    for warning in plan.warnings:
        print(f"  ⚠ {warning}")


def _print_approval_view(plan) -> None:
    view = plan.approval_view()
    print("  — approval summary —")
    print(f"    planned cells   : {view['planned_cells']}")
    print(f"    transport attempts / cell : base {view['base_transport_attempts']}, "
          f"max {view['max_transport_attempts']} "
          "(retries may dispatch anywhere in [base, max] — not an exact call count)")
    print(f"    worst-case reservation : {format_usd(view['worst_case_reservation_usd'])} "
          f"({plan.execution['budget']['reservation_basis']})")
    print(f"    approve with    : --approve-plan {plan.plan_hash}")


def _cmd_benchmark_plan(args: argparse.Namespace) -> int:
    _config, plan = _resolve_plan_or_error(args, label="benchmark plan", require_run_ready=False)
    if plan is None:
        return 1
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    _print_plan(plan)
    return 0


def _build_doctor_parser(subparsers: argparse._SubParsersAction) -> None:
    doctor = subparsers.add_parser(
        "doctor",
        help="Offline pre-flight checks before any paid call (never sends a prompt).",
    )
    _add_plan_args(doctor)
    doctor.add_argument(
        "--check-identity", action="store_true",
        help="run read-only live probes: Entra token acquisition, a data-plane "
             "models GET (RBAC), and management-plane deployment GETs (routing "
             "mode / model). These are the ONLY egress and NEVER an inference "
             "prompt. Off by default so doctor is fully offline.",
    )
    doctor.set_defaults(func=_cmd_doctor)


def _doctor_pricing_coverage(
    plan, config, *, rate_card_path: str | None
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...], tuple[str, ...]]:
    """Classify arms by what their pricing coverage can actually be proven to be.

    Returns ``(unpriced_direct, partial_direct, router_arm_ids)``.

    A ``direct`` arm bills under a model fixed at plan time, so its rate can be
    resolved now and a miss is a hard failure. A ``model_router`` arm's backend is
    chosen by the provider per prompt, so no pre-flight lookup can prove coverage
    — its arm/deployment name is never itself a pricing key.

    A pinned key is *necessary but not sufficient*: the v2 card prices cached and
    reasoning tokens from their own components, and a ``null`` component still
    fails the cell closed when tokens of that kind appear (this is exactly the
    ``cached: null`` hole that voided the first 03D run). Such arms come back as
    ``partial`` — not a failure, because whether it bites depends on the usage
    the run actually produces, but never reported as complete coverage either.
    """

    arms = plan.execution["arms"]
    routers = tuple(
        str(arm["id"]) for arm in arms if str(arm.get("kind")) == "model_router"
    )
    direct = [
        (str(arm["id"]), str(arm.get("requested_model") or arm.get("deployment") or ""))
        for arm in arms
        if str(arm.get("kind")) == "direct"
    ]
    all_unpriced = tuple(direct)
    if not rate_card_path:
        return all_unpriced, (), routers
    try:
        resolved = config.resolve_path(rate_card_path)
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
        schema = raw.get("schema_version")
        if schema is None or int(schema) < 2:
            # A v1 card fails *open* (PricingTable.rates_for falls back to a
            # default), so it can never answer a coverage question. Report the
            # direct arms as unverified rather than implying they are covered.
            return (), tuple(direct), routers
        card = RateCardV2.from_yaml(resolved)
    except (OSError, ValueError, RateCardError, yaml.YAMLError):
        # An unreadable card clears nothing; every direct arm stays unproven.
        return all_unpriced, (), routers

    unpriced: list[tuple[str, str]] = []
    partial: list[tuple[str, str]] = []
    for arm_id, model in direct:
        rates = card.rates_for(card.resolve_pricing_key(model))
        if rates is None:
            unpriced.append((arm_id, model))
            continue
        missing = [
            name for name in ("cached", "reasoning")
            if getattr(rates, name, None) is None
        ]
        if missing:
            partial.append((arm_id, f"{model} ({'/'.join(missing)} unpinned)"))
    return tuple(unpriced), tuple(partial), routers


def _doctor_inputs_from_plan(plan, config, *, deps_present: bool) -> DoctorInputs:
    ex = plan.execution
    endpoint = ex["endpoint"]
    pricing = ex["pricing"]
    view = plan.approval_view()
    rate_card_path = pricing.get("rate_card_path")
    rate_card_present = bool(rate_card_path)
    unpriced_direct, partial_direct, router_arms = _doctor_pricing_coverage(
        plan, config, rate_card_path=rate_card_path
    )
    deployments = [
        arm["deployment"] for arm in ex["arms"]
        if arm.get("deployment") and not _is_placeholder_value(arm["deployment"])
    ]
    workload_path = ex["workload"]["path"]
    artifacts = ex.get("artifacts") or {}
    privacy = ex.get("privacy") or {}
    local_root = artifacts.get("local_root")
    return DoctorInputs(
        run_mode=plan.run_mode,
        endpoint=endpoint.get("data_plane"),
        endpoint_kind=endpoint.get("dialect", ""),
        deployments=deployments,
        arms=list(ex["arms"]),
        workload_path=workload_path,
        workload_ok=Path(workload_path).is_file(),
        rate_card_present=rate_card_present,
        unpriced_direct_arms=unpriced_direct,
        partial_direct_arms=partial_direct,
        router_arm_ids=router_arms,
        authorization_ceiling_usd=pricing.get("smoke_authorization_ceiling_usd"),
        planned_cells=plan.planned_cells,
        base_transport_attempts=plan.base_transport_attempts,
        max_transport_attempts=plan.max_transport_attempts,
        output_token_ceiling=int(ex.get("request", {}).get("max_output_tokens", 0)),
        conservative_max_authorized_spend_usd=format_usd(
            view["worst_case_reservation_usd"]
        ).lstrip("$"),
        prereg_note=_doctor_prereg_note(plan),
        prereg_allowed=_doctor_prereg_allowed(plan),
        output_dir=local_root,
        output_dir_writable=_dir_writable(local_root),
        retain_raw_outputs=bool(privacy.get("retain_raw_outputs", False)),
        wiring_only=plan.run_mode != "benchmark",
        deps_present=deps_present,
        az_cli_present=az_cli_available(),
    )


def _is_placeholder_value(value: object) -> bool:
    text = str(value or "").strip().lower()
    return not text or text.startswith("<") or "placeholder" in text or "your-" in text


def _dir_writable(path: str | None) -> bool:
    if not path:
        return False
    target = Path(path)
    probe = target if target.exists() else target.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return os.access(probe, os.W_OK)


def _doctor_prereg_note(plan) -> str:
    prereg = plan.execution.get("preregistration") or {}
    if plan.run_mode == "benchmark":
        committed = prereg.get("commit") or prereg.get("committed_at")
        if committed:
            return f"preregistration committed ({committed})"
        return "benchmark requires a committed preregistration"
    return "smoke wiring-only; preregistration not required"


def _doctor_prereg_allowed(plan) -> bool:
    prereg = plan.execution.get("preregistration") or {}
    if plan.run_mode == "benchmark":
        return bool(prereg.get("commit") or prereg.get("committed_at"))
    return True


def _cmd_doctor(args: argparse.Namespace) -> int:
    config, plan = _resolve_plan_or_error(args, label="doctor", require_run_ready=False)
    if plan is None:
        return 1

    deps_present = _foundry_extra_present()
    inputs = _doctor_inputs_from_plan(plan, config, deps_present=deps_present)

    # All live probes are read-only and NEVER send an inference prompt: a token
    # acquisition, a data-plane models GET (RBAC), and management-plane deployment
    # GETs (routing mode / model). They are gated behind --check-identity so the
    # default doctor path (and CI) stays fully offline.
    token_probe = rbac_probe = deployment_probe = None
    routing_evidence: list[str] = []
    if getattr(args, "check_identity", False):
        token_probe = _doctor_token_probe(plan)
        rbac_probe = _doctor_rbac_probe(plan)
        deployment_probe = _doctor_deployment_probe(plan, evidence_out=routing_evidence)

    report = run_doctor(
        inputs, token_probe=token_probe, rbac_probe=rbac_probe,
        deployment_probe=deployment_probe,
    )

    if args.json:
        payload = {
            "ready": report.ready,
            "token_acquired": report.token_acquired,
            "data_plane_rbac_verified": report.data_plane_rbac_verified,
            "deployment_config_verified": report.deployment_config_verified,
            "routing_mode_evidence": routing_evidence,
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail,
                 "next_step": c.next_step}
                for c in report.checks
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(report.to_text())
        if routing_evidence:
            print("\nrouting-mode evidence (management-plane "
                  f"{ROUTING_MODE_API_VERSION}):")
            for line in routing_evidence:
                print(f"  {line}")
    return 0 if report.ready else 1


def _foundry_extra_present() -> bool:
    import importlib.util

    return all(
        importlib.util.find_spec(mod) is not None
        for mod in ("openai", "azure.identity")
    )


def _doctor_token_probe(plan):
    """Build a token probe from the ambient Azure identity (never sends a prompt)."""

    def probe() -> str:
        from azure.identity import DefaultAzureCredential

        scope = "https://cognitiveservices.azure.com/.default"
        token = DefaultAzureCredential().get_token(scope)
        return token.token

    return probe


def _doctor_rbac_probe(plan):
    """Prove data-plane RBAC with a read-only models GET (never an inference call).

    A 200 confirms the identity holds the data-plane role; 401/403 confirms it is
    absent; anything else (or a transport failure) is ``None`` — unknown, not OK.
    """

    endpoint = (plan.execution.get("endpoint") or {}).get("data_plane")
    api_version = (plan.execution.get("endpoint") or {}).get(
        "api_version", DEFAULT_API_VERSION
    )

    def probe() -> bool | None:
        if not endpoint:
            return None
        import httpx
        from azure.identity import DefaultAzureCredential

        token = DefaultAzureCredential().get_token(
            "https://cognitiveservices.azure.com/.default"
        ).token
        url = f"{endpoint.rstrip('/')}/openai/models?api-version={api_version}"
        try:
            resp = httpx.get(
                url, headers={"Authorization": f"Bearer {token}"}, timeout=30.0
            )
        except httpx.HTTPError:
            return None
        if resp.status_code == 200:
            return True
        if resp.status_code in (401, 403):
            return False
        return None

    return probe


def _doctor_deployment_probe(plan, *, evidence_out: list[str] | None = None):
    """Verify each arm's routing mode / model against the live management plane.

    Reads every arm's deployment with :data:`ROUTING_MODE_API_VERSION` (the only
    api-version that surfaces ``routing.mode``) and compares to the arm's approved
    ``expected`` evidence. Read-only; never an inference call. Returns ``True`` on
    a full match, ``False`` on a mismatch, ``None`` when any deployment (or the
    management resource id) is unreadable.
    """

    evidence = plan.execution.get("deployment_evidence") or {}
    resource_id = evidence.get("management_resource_id")
    arms = list(plan.execution.get("arms") or [])

    def probe() -> bool | None:
        if not resource_id or not arms:
            return None
        import httpx
        from azure.identity import DefaultAzureCredential

        token = DefaultAzureCredential().get_token(
            "https://management.azure.com/.default"
        ).token
        live: dict[str, Mapping[str, Any] | None] = {}
        for arm in arms:
            dep = arm.get("deployment")
            if not dep:
                continue
            url = (
                f"https://management.azure.com{resource_id}/deployments/{dep}"
                f"?api-version={ROUTING_MODE_API_VERSION}"
            )
            try:
                resp = httpx.get(
                    url, headers={"Authorization": f"Bearer {token}"}, timeout=30.0
                )
            except httpx.HTTPError:
                live[dep] = None
                continue
            live[dep] = resp.json().get("properties", {}) if resp.status_code == 200 else None
        ok, lines = evaluate_deployment_modes(arms, live)
        if evidence_out is not None:
            evidence_out.extend(lines)
        return ok

    return probe


def _cmd_benchmark_smoke(args: argparse.Namespace) -> int:
    return _benchmark_preview_or_dispatch(args, kind="smoke")


def _cmd_benchmark_run(args: argparse.Namespace) -> int:
    return _benchmark_preview_or_dispatch(args, kind="run")


# Diagnostic-only coverage threshold shown next to the live progress line. It mirrors
# the preregistration's grading-coverage floor (a required arm below this => void run,
# prereg-03d2), but the live display is DIAGNOSTIC: it exists so a detached run can be
# watched for a coverage collapse and aborted early. It never adjudicates the run and
# is not part of any config or plan_hash.
_DIAG_COVERAGE_GATE = 0.90


def _live_measure_client(plan, fconfig) -> AzureMeasureClient:
    """Build the live benchmark client with the plan's own transport cutoffs.

    The plan's ``retry`` timeouts are bound into ``plan_hash`` and sealed into
    the run manifest, so they must also reach the socket. Before this was
    wired, the client fell back to :class:`TransportTimeouts` defaults
    (read 90 / overall 120) and an operator-approved timeout change was a
    silent no-op that the sealed manifest still reported as applied.
    """

    return AzureMeasureClient(
        AzureModelRouterClient(
            config=fconfig,
            max_output_tokens=plan.execution["request"]["max_output_tokens"],
            timeouts=TransportTimeouts.from_retry(plan.execution.get("retry")),
        )
    )


def _benchmark_preview_or_dispatch(args: argparse.Namespace, *, kind: str) -> int:
    label = f"benchmark {kind}"
    live = bool(getattr(args, "live", False))
    config, plan = _resolve_plan_or_error(
        args, label=label, require_run_ready=live
    )
    if plan is None:
        return 1

    if kind == "run" and plan.run_mode != "benchmark":
        print(f"{label}: config run_mode is '{plan.run_mode}', not 'benchmark'. "
              "Use `benchmark smoke` for a wiring check, or set run_mode: benchmark.")
        return 1

    if not live:
        if args.json:
            print(json.dumps(plan.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
        else:
            _print_plan(plan)
            print("")
            print(f"{label}: PREVIEW only — no live calls were made (zero egress).")
            print(f"  Re-run with --live --approve-plan {plan.plan_hash} once an operator "
                  "approves the spend.")
            print("  `cost-router foundry status` must show credentialed: yes (az login).")
        return 2

    # --- live path (operator-gated; approval bound to the exact plan_hash) ----
    try:
        check_approval(plan, getattr(args, "approve_plan", None))
    except ApprovalError as exc:
        print(f"{label}: {exc}")
        return 1

    load_dotenv_file(args.env_file)
    fconfig = FoundryConfig.from_env()
    if not fconfig.credentialed:  # pragma: no cover - live guard
        print(f"{label} --live: not credentialed; set AZURE_AI_FOUNDRY_* in .env, then `az login`.")
        return 1
    client = _live_measure_client(plan, fconfig)  # pragma: no cover - live path
    out_root = Path(plan.execution["artifacts"]["local_root"])
    run_dir = out_root / kind / make_run_id()
    run_dir.mkdir(parents=True, exist_ok=True)  # pragma: no cover - live path
    progress_path = run_dir / "progress.json"  # pragma: no cover - live path
    print(  # pragma: no cover - live path
        f"{label} --live: dispatching plan_hash {plan.plan_hash} → {run_dir}", flush=True
    )

    def _live_progress(ev: Mapping[str, Any]) -> None:  # pragma: no cover - live path
        # Runtime-only progress surface (never fingerprinted; run dir is gitignored):
        # one flushed stdout line per finished cell for a detached-run log tail, plus
        # an atomically-rewritten progress.json for structured polling. The coverage
        # and per-arm pass figures are DIAGNOSTIC (abort aid), not an adjudication.
        done, total = ev.get("cells_done"), ev.get("cells_total")
        cov = ev.get("coverage")
        cov_txt = (
            f"cov {cov * 100:.1f}% [gate {_DIAG_COVERAGE_GATE * 100:.0f}%]"
            if isinstance(cov, (int, float))
            else "cov —"
        )
        arms = ev.get("arms") or {}
        arm_bits = []
        for arm in plan.arms:  # plan order; short label (router-cost -> cost)
            arm_id = str(arm.get("id", ""))
            short = arm_id.split("-", 1)[1] if "-" in arm_id else arm_id
            st = arms.get(str(arm.get("requested_model"))) or {}
            attempted = int(st.get("attempted", 0))
            arm_bits.append(
                f"{short} {int(st.get('passed', 0))}/{attempted}" if attempted else f"{short} —"
            )
        arm_txt = " · ".join(arm_bits)
        print(
            f"progress: {done}/{total} cells  ${ev.get('running_cost_usd')}  "
            f"429×{ev.get('throttles')}  fail×{ev.get('failures')}  {cov_txt}  "
            f"[{ev.get('event', '')}]\n         {arm_txt}",
            flush=True,
        )
        payload = {
            **dict(ev),
            "coverage_gate": _DIAG_COVERAGE_GATE,
            "coverage_note": (
                "diagnostic-only: mid-run coverage/pass are an abort aid, not a "
                "verdict; changing workload/arms/gates on these values violates prereg"
            ),
            "run_dir": str(run_dir),
            "plan_hash": plan.plan_hash,
        }
        tmp = progress_path.with_name("progress.json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(progress_path)

    try:  # pragma: no cover - live path
        result = execute_benchmark(
            config, plan, client=client, run_dir=run_dir, exp_id=kind,
            git_commit=_git_head(),
            region=args.region,
            progress=_live_progress,
        )
    except (PlanError, RuntimeError, ValueError, KeyError, OSError) as exc:  # pragma: no cover
        print(f"{label} --live: {exc}")
        return 1
    print(  # pragma: no cover - live path
        f"{label} --live: sealed snapshot {result.run_dir}  plan_hash {plan.plan_hash}"
    )
    return 0  # pragma: no cover


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
    if args.command == "config" and not getattr(args, "config_command", None):
        print(f"usage: cost-router config init [--output {DEFAULT_LOCAL_CONFIG}] [--force]")
        return 0
    if args.command == "benchmark" and not getattr(args, "benchmark_command", None):
        print("usage: cost-router benchmark [plan | smoke | run] --config PATH")
        return 0
    if args.command == "models" and not getattr(args, "models_command", None):
        args.fleet = None
        args.json = False
        return _cmd_models_list(args)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
