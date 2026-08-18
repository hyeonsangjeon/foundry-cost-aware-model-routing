"""Offline HTTP service exposing the router pipeline.

Built on the standard library only (``http.server``): no third-party web
framework, no provider calls, no network egress. Every request is answered
deterministically from the local policy, the bundled illustrative pricing, and
either caller-supplied or synthesized offline check signals.

Endpoints
---------
``GET  /healthz``      -> liveness probe.
``GET  /policy``       -> policy version and ordered candidates per task class.
``POST /route``        -> route one task payload, return its trace.
``POST /batch-route``  -> route many task payloads, return traces + summary.

The request/response bodies are JSON. The request schema for ``/route`` is::

    {
      "task":    { "task_id": "t-x", "class": "generate", "tokens": {...} },
      "signals": { "<model>": { "applies": true, ... }, ... },   # optional
      "synth":   false,                                          # optional
      "pricing": "illustrative"                                  # optional
    }

When ``signals`` are omitted (or ``synth`` is true), deterministic offline
signals are synthesized for the task's policy candidates. ``/batch-route`` takes
``tasks`` (a list) and an optional ``signals`` object keyed by ``task_id``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .annotations import (
    historical_amount_showable,
    router_cost_disclosure,
    savings_claim_allowed,
)
from .cockpit import CockpitController, CockpitError
from .dashboard import DASHBOARD_HTML
from .experiment import (
    Experiment,
    ExperimentResult,
    list_experiments,
    load_experiment,
    run_experiment,
)
from .fleet import FleetRegistry
from .foundry_live import FoundryConfig
from .measure import (
    DEFAULT_N,
    MeasureCandidate,
    build_catalog,
    load_prompt_workload,
    replay_measure,
)
from .metrics import (
    ExperimentMetrics,
    JsonlMetricsStore,
    extract_experiment_metrics,
    record_experiment_metrics,
)
from .pipeline import (
    batch_route_payload,
    bundled_compare,
    bundled_coverage_cliff,
    bundled_fanout_sweep,
    find_samples_root,
    load_default_pricing,
    load_policy,
    policy_summary,
    route_payload,
    run_bundled_replay,
)
from .pricing import PricingTable

_KNOWN_ROUTES = {
    "/",
    "/dashboard",
    "/healthz",
    "/policy",
    "/replay",
    "/regression",
    "/fanout-sweep",
    "/compare",
    "/route",
    "/batch-route",
    "/experiments",
    "/experiment",
    "/metrics/history",
    "/fleet",
    "/fleet/run",
}
_PRICING_OFF = {"none", "off", "disabled", "false"}
_PRICING_DEFAULT = {"illustrative", "default", "sample", "on", "true"}
_TRUTHY = {"1", "true", "yes", "on"}
# When the requested port is busy, try this many higher ports before giving up.
_PORT_FALLBACK_TRIES = 10
# Deterministic baseline timestamps for the seeded metrics history, so the
# historical dashboard is populated out of the box and the static export is
# reproducible. Live experiment runs append real-time entries on top.
_HISTORY_EPOCH = "2026-01-{day:02d}T00:00:00Z"


@dataclass(frozen=True)
class ServiceResponse:
    """A status code, a payload, and the media type used to encode it.

    ``application/json`` payloads are ``json.dumps``-ed; any other media type
    treats ``payload`` as already-rendered text/bytes (used for the dashboard).
    """

    status: int
    payload: Any
    media_type: str = "application/json"


class RouterService:
    """Stateless offline routing service.

    The policy and pricing tables are loaded once at construction so that every
    request is served without touching the filesystem again.
    """

    def __init__(
        self,
        *,
        policy: Any | None = None,
        pricing: PricingTable | None = None,
        metrics_store: JsonlMetricsStore | None = None,
        cockpit_token: str | None = None,
        run_plan: Any | None = None,
        run_config: Any | None = None,
        client_factory: Any | None = None,
    ) -> None:
        self.policy = policy or load_policy()
        if pricing is not None:
            self.pricing: PricingTable | None = pricing
        else:
            try:
                self.pricing = load_default_pricing()
            except FileNotFoundError:
                self.pricing = None
        self.metrics_store = metrics_store
        self._experiment_runs: list[tuple[Experiment, ExperimentResult, ExperimentMetrics]] | None
        self._experiment_runs = None
        self._history: list[dict[str, Any]] | None = None
        self._samples_root = find_samples_root()
        self._fleet: FleetRegistry | None = None
        # Cockpit (Phase C): only enabled when a session token is set (i.e. via
        # `cost-router dashboard --live`). The public/static build leaves it None,
        # so every /cockpit/* route 404s and no live surface ships.
        self.cockpit_token = cockpit_token
        self._cockpit_progress: dict[str, dict[str, Any]] = {}
        # 03C: when a ResolvedRunPlan is bound (dashboard --config), the cockpit
        # becomes a control surface over that exact plan — preview, approval,
        # run, abort, and snapshot all key on the single server-side plan_hash.
        # Without a bound plan the run route stays fail-closed (no ad-hoc config).
        self._run_plan = run_plan
        self._run_config = run_config
        self._client_factory = client_factory
        self._cockpit_controller: CockpitController | None = None
        if run_plan is not None and run_config is not None:
            # The controller loads pricing from the plan's OWN pinned rate card
            # (never the server's bundled illustrative table), so an unpriced
            # backend fails closed instead of silently pricing off a default.
            self._cockpit_controller = CockpitController(
                run_plan,
                run_config,
                client_factory=client_factory,
            )

    # -- endpoint handlers ------------------------------------------------

    def healthz(self) -> ServiceResponse:
        return ServiceResponse(
            200,
            {
                "status": "ok",
                "service": "cost-router",
                "version": __version__,
                "offline": True,
            },
        )

    def policy_view(self) -> ServiceResponse:
        return ServiceResponse(200, policy_summary(self.policy))

    def dashboard(self) -> ServiceResponse:
        return ServiceResponse(200, DASHBOARD_HTML, media_type="text/html; charset=utf-8")

    def replay(self, path: str) -> ServiceResponse:
        synth = _query_flag(path, "synth")
        report = run_bundled_replay(policy=self.policy, synth=synth)
        return ServiceResponse(200, {"traces": report.traces, "summary": report.summary})

    def regression(self) -> ServiceResponse:
        return ServiceResponse(200, bundled_coverage_cliff())

    def fanout_sweep(self) -> ServiceResponse:
        return ServiceResponse(200, bundled_fanout_sweep())

    def compare_view(self, path: str) -> ServiceResponse:
        """Head-to-head "one problem, four ways" payload for the WOW demo.

        Returns the task menu plus every curated task's arena (cheapest /
        premium / ensemble / cost-aware router with cost, accuracy, and an
        illustrative latency projection), so the web app can switch problems
        client-side with no round-trip. Offline and deterministic;
        ``measured = false``.
        """

        task = _query_value(path, "task")
        return ServiceResponse(200, bundled_compare(task_id=task or None))

    # -- experiments & metrics -------------------------------------------

    def experiments_view(self) -> ServiceResponse:
        """List every experiment with its offline metrics for the web app.

        Each card carries the normalized :class:`ExperimentMetrics` (cost,
        coverage, and the ensemble fan-out tax), the reproducibility checks, and
        the strategy arms — enough for the dashboard to render per-experiment
        statistics on click without a second round-trip. Deterministic;
        ``recorded_at`` is null because this is a pure projection, not a
        timestamped recording.
        """

        cards = [
            self._experiment_card(exp, result, metrics)
            for exp, result, metrics in self._runs()
        ]
        return ServiceResponse(200, {"experiments": cards})

    def experiment_view(self, path: str) -> ServiceResponse:
        """Run one experiment by name and record it into the metrics history.

        Unlike ``/experiments`` this is the "real-time" action: it stamps the
        run with the current time, appends it to the in-memory history (and the
        file-backed store when configured), and returns the full result plus the
        metrics snapshot. Offline and deterministic apart from the timestamp.
        """

        name = _query_value(path, "name")
        if not name:
            return _error(400, "missing required query parameter 'name'")
        try:
            experiment = load_experiment(name)
        except (OSError, ValueError) as exc:
            return _error(404, str(exc))
        result = run_experiment(experiment)
        metrics = record_experiment_metrics(result, store=self.metrics_store)
        self._history_rows().append(metrics.to_dict())
        return ServiceResponse(
            200,
            {"result": result.to_dict(), "metrics": metrics.to_dict()},
        )

    def metrics_history_view(self, path: str) -> ServiceResponse:
        """Return the recorded experiment runs for the historical dashboard."""

        name = _query_value(path, "experiment")
        rows = self._history_rows()
        if name:
            rows = [row for row in rows if row.get("experiment") == name]
        latest: dict[str, dict[str, Any]] = {}
        for row in self._history_rows():
            latest[str(row.get("experiment"))] = row
        return ServiceResponse(200, {"history": list(rows), "latest": latest})

    # -- fleet (model registry & selection) -------------------------------

    def fleet_view(self) -> ServiceResponse:
        """Return the model catalog, current slate, and live-call readiness.

        Drives the dashboard's fleet panel: the operator picks which deployed
        model plays each arm (router/cheapest/premium/ensemble). Redacted and
        network-free — ``credentialed`` reflects only whether a live run *could*
        be made from the terminal; the web path never egresses.
        """

        registry = self._fleet_registry()
        payload = {
            "source": registry.source,
            "models": registry.catalog_view(),
            "roles": registry.role_assignments(),
            "credentialed": FoundryConfig.from_env().credentialed,
            "recorded_available": self._recorded_arena_path().is_file(),
        }
        return ServiceResponse(200, payload)

    def fleet_run(self, body: bytes) -> ServiceResponse:
        """Validate a selected slate and return the recorded arena reference.

        The offline dashboard never makes paid calls, so this replays the
        committed *measured* snapshot — honestly relabeled ``provenance =
        recorded`` / ``measured = false`` (a captured measurement, not a fresh
        one) — and hands back the selected slate plus the exact terminal command
        that would MEASURE that slate live. Selecting a different slate does not
        change the recorded numbers (they are the captured reference fleet);
        that is called out in ``note`` and ``recorded_fleet``.
        """

        parsed = _load_json_object(body)
        if isinstance(parsed, ServiceResponse):
            return parsed
        roles = parsed.get("roles") or {}
        if not isinstance(roles, dict):
            return _error(400, "'roles' must be an object of role -> model name(s)")
        registry = self._fleet_registry()
        ensemble = roles.get("ensemble")
        try:
            registry = registry.with_roles(
                router=roles.get("router"),
                cheapest=roles.get("cheapest"),
                premium=roles.get("premium"),
                ensemble=list(ensemble) if isinstance(ensemble, list) else None,
            )
            slate = registry.slate()
        except (ValueError, KeyError) as exc:
            return _error(400, str(exc))
        recorded = self._recorded_arena_report()
        if recorded is None:
            return _error(404, "no recorded arena snapshot is bundled to replay")
        return ServiceResponse(
            200,
            {
                "mode": "recorded",
                "slate": {
                    "router": slate.router,
                    "cheapest": slate.cheapest,
                    "premium": slate.premium,
                    "ensemble": list(slate.ensemble),
                },
                "roles": registry.role_assignments(),
                "report": recorded["report"],
                "recorded_fleet": recorded["fleet"],
                "live_command": _fleet_live_command(registry),
                "note": (
                    "Offline: the arena below is the committed MEASURED snapshot, "
                    "honestly relabeled recorded (measured=false). It reflects the "
                    "captured reference fleet, not your selection. Run the command "
                    "above to measure YOUR selected slate live (measured=true)."
                ),
            },
        )

    # -- cockpit (Phase C, live-run control surface) ----------------------

    def _cockpit_authed(self, path: str) -> bool:
        """A /cockpit/* request is authorised only with the exact session token."""

        if not self.cockpit_token:
            return False
        token = _query_value(path, "token")
        return bool(token) and token == self.cockpit_token

    def _cockpit_candidates(self) -> list[MeasureCandidate]:
        slate = self._fleet_registry().slate()
        return [
            MeasureCandidate(model=dep, deployment=dep, provider=slate.provider_for(dep))
            for dep in slate.ensemble
        ]

    def _cockpit_workload_path(self, path: str) -> Path:
        # 03C: a bound plan is the sole workload authority — the browser cannot
        # point the cockpit at an arbitrary filesystem path via ?workload=.
        if self._cockpit_controller is not None:
            return self._run_config.resolve_path(self._run_plan.workload_path)
        wl = _query_value(path, "workload")
        if wl:
            return Path(wl)
        return self._samples_root / "samples" / "telemetry" / "curated-arena-live.sample.jsonl"

    def cockpit_status(self) -> ServiceResponse:
        """Connection panel (C2): masked Foundry status + fleet slate + pricing.

        Reuses :meth:`FoundryConfig.status` (already redacted — no secret leaves)
        and the fleet slate, so the browser shows exactly what is wired and what
        is missing, with zero credential input fields. When a plan is bound it
        also publishes the single server-side ``plan_hash`` so preview, approval,
        and replay can all be checked against the same value.
        """

        registry = self._fleet_registry()
        slate = registry.slate()
        payload: dict[str, Any] = {
            "foundry": FoundryConfig.from_env().status(),
            "fleet": {
                "source": registry.source,
                "roles": registry.role_assignments(),
                "ensemble": list(slate.ensemble),
            },
            "pricing_loaded": self.pricing is not None,
            "measured": False,
        }
        if self._cockpit_controller is not None:
            payload["plan_bound"] = True
            payload["plan_hash"] = self._cockpit_controller.plan_hash
        else:
            payload["plan_bound"] = False
        return ServiceResponse(200, payload)

    def cockpit_plan(self) -> ServiceResponse:
        """The bound plan's parity fields (03C): everything every surface agrees on.

        Keyed by ``plan_hash`` so preview, approval, run, and replay bind to the
        one server-side plan — the browser never supplies plan content.
        """

        if self._cockpit_controller is None:
            return _error(400, "no run plan bound; start with `dashboard --config <file>`")
        return ServiceResponse(200, self._cockpit_controller.parity())

    def cockpit_preview(self) -> ServiceResponse:
        """The human-approval preview (03C): planned_cells + base/max attempts.

        Never collapses retry-dependent outbound calls into an exact count.
        """

        if self._cockpit_controller is None:
            return _error(400, "no run plan bound; start with `dashboard --config <file>`")
        return ServiceResponse(200, self._cockpit_controller.preview())

    def cockpit_catalog(self, path: str) -> ServiceResponse:
        """Pre-flight catalog (C4/B4): prompts, validation, candidates, cost — no calls."""

        # 03C: a bound plan prices its own workload/candidates and fails closed on
        # an unpriced resolved backend — never off the generic default.
        if self._cockpit_controller is not None:
            try:
                return ServiceResponse(200, self._cockpit_controller.preflight())
            except CockpitError as exc:
                return _error(400, str(exc))
        if self.pricing is None:
            return _error(503, "no pricing table loaded; set FOUNDRY_PRICING_PATH")
        workload_path = self._cockpit_workload_path(path)
        try:
            workload = load_prompt_workload(workload_path)
        except (OSError, ValueError) as exc:
            return _error(400, f"workload load failed: {exc}")
        if not workload:
            return _error(400, f"no prompt-bearing tasks in {workload_path}")
        candidates = self._cockpit_candidates()
        if not candidates:
            return _error(400, "no candidates in the fleet ensemble slate")
        n = _query_int(path, "n", DEFAULT_N)
        catalog = build_catalog(workload, candidates, n=n, pricing=self.pricing)
        catalog["workload_path"] = str(workload_path)
        return ServiceResponse(200, catalog)

    def cockpit_run(self, body: bytes) -> ServiceResponse:
        """Run gate (C4): validate every gate; the paid sweep runs only past them.

        With a bound plan (03C) the gate is plan-hash approval + an idempotency
        key, enforced by :class:`CockpitController` — a stale approval, a missing
        key, a budget-reservation refusal, or an unpriced backend all fail closed
        before any dispatch, and the start response never claims ``measured``.

        Without a bound plan the legacy fleet path returns an honest
        ``ran=false`` with the reason — the paid leaf is operator-gated and never
        runs in CI.
        """

        parsed = _load_json_object(body)
        if isinstance(parsed, ServiceResponse):
            return parsed
        if self._cockpit_controller is not None:
            return self._cockpit_run_planned(parsed)
        approve = bool(parsed.get("approve"))
        budget = parsed.get("budget_usd")
        experiment = str(parsed.get("experiment") or "cockpit")
        config = FoundryConfig.from_env()
        gates = {
            "approved": approve,
            "credentialed": config.credentialed,
            "budget_set": isinstance(budget, (int, float)) and budget is not None,
        }
        if not all(gates.values()):
            reason = self._cockpit_refusal(gates)
            return ServiceResponse(
                200,
                {"ran": False, "gates": gates, "reason": reason, "measured": False},
            )
        return self._cockpit_launch(
            parsed, experiment=experiment, budget=float(budget), config=config
        )

    def _cockpit_run_planned(self, parsed: Mapping[str, Any]) -> ServiceResponse:
        """03C run gate: plan-hash approval + idempotency, fail-closed before spend."""

        controller = self._cockpit_controller
        assert controller is not None
        if not bool(parsed.get("approve")):
            return ServiceResponse(
                200,
                {
                    "ran": False,
                    "reason": "not approved — approve the reviewed plan_hash to spend.",
                    "measured": False,
                },
            )
        plan_hash = parsed.get("plan_hash")
        idempotency_key = parsed.get("idempotency_key")
        try:
            run = controller.approve_and_start(
                plan_hash=plan_hash if plan_hash is None else str(plan_hash),
                idempotency_key=(
                    None if idempotency_key is None else str(idempotency_key)
                ),
                inline=False,
            )
        except CockpitError as exc:
            # Stale plan_hash, missing key, active-run lock, budget refusal, or an
            # unpriced backend: all fail closed with an honest reason, no spend.
            return ServiceResponse(
                200, {"ran": False, "reason": str(exc), "measured": False}
            )
        response = controller.start_response(run)
        response["ran"] = True
        # The start response NEVER claims measured=true; that is only ever earned
        # after completion + a clean snapshot replay (polled via /cockpit/snapshot).
        return ServiceResponse(200, response)

    def cockpit_abort(self, body: bytes) -> ServiceResponse:
        """Abort a live run through the shared 03B durable gate (03C)."""

        if self._cockpit_controller is None:
            return _error(400, "no run plan bound; abort requires a bound cockpit run")
        parsed = _load_json_object(body)
        if isinstance(parsed, ServiceResponse):
            return parsed
        run_id = str(parsed.get("run_id") or "")
        try:
            return ServiceResponse(200, self._cockpit_controller.abort(run_id))
        except CockpitError as exc:
            return _error(404, str(exc))

    @staticmethod
    def _cockpit_refusal(gates: Mapping[str, bool]) -> str:
        if not gates["credentialed"]:
            return ("not credentialed — set AZURE_AI_FOUNDRY_* in .env and run "
                    "`az login`; the cockpit reads Entra creds from the environment.")
        if not gates["budget_set"]:
            return "no budget cap — set budget_usd from the dry-run estimate before running."
        if not gates["approved"]:
            return "not approved — the operator must click 'approve & run' to spend."
        return "blocked."

    def _cockpit_launch(
        self, parsed: Mapping[str, Any], *, experiment: str, budget: float,
        config: FoundryConfig,
    ) -> ServiceResponse:
        """Refused: the plan-less cockpit route does not run measured sweeps.

        This is the pre-03C route, reached only when ``self._cockpit_controller is
        None``. It used to seal a snapshot under ``results/measured/`` from a client
        built with nothing but a :class:`FoundryConfig` — no request cap, no
        transport cutoffs, and a ``benchmark_mode`` left at its default, so the
        provider scope-out gate saw a smoke on every dispatch and the fleet's
        ``provider: foundry`` models could carry a measured cost.

        It is refused rather than wired because it has no plan to be wired *from*,
        and the supported route already exists: bind a plan and
        :class:`~router.cockpit.CockpitController` handles the sweep instead, with
        the plan-hash approval, idempotency key and spend ledger this one never had.
        """

        from .measure import unsupported_measured_route_refusal

        return ServiceResponse(
            200,
            {
                "ran": False,
                "measured": False,
                "reason": unsupported_measured_route_refusal(
                    "cockpit run (no plan bound)",
                    successor="the plan-bound cockpit — start the dashboard with "
                    "--config so a ResolvedRunPlan is bound",
                ),
            },
        )

    def cockpit_progress(self, path: str) -> ServiceResponse:
        """Latest streamed progress for a run (C5). Empty until a run starts."""

        run_id = _query_value(path, "run") or ""
        if self._cockpit_controller is not None:
            return ServiceResponse(
                200, {"run_id": run_id, "progress": self._cockpit_controller.progress(run_id)}
            )
        return ServiceResponse(
            200, {"run_id": run_id, "progress": self._cockpit_progress.get(run_id)}
        )

    def cockpit_snapshot(self, path: str) -> ServiceResponse:
        """Render a committed snapshot by REPLAYING it (C6) — the replay is the check."""

        run = _query_value(path, "run")
        if not run:
            return _error(400, "pass ?run=<snapshot dir>")
        # 03C: a bound cockpit replays its own run by id (no arbitrary FS path),
        # and an unverified replay withholds the cost amount itself (03Z-b).
        if self._cockpit_controller is not None:
            try:
                return ServiceResponse(200, self._cockpit_controller.snapshot(run))
            except CockpitError as exc:
                return _error(404, str(exc))
            except (OSError, ValueError, KeyError) as exc:
                return _error(400, f"snapshot replay failed: {exc}")
        run_dir = Path(run)
        try:
            report = replay_measure(run_dir)
        except (OSError, ValueError, KeyError) as exc:
            return _error(400, f"snapshot replay failed: {exc}")
        summary = report.recomputed_summary if isinstance(report.recomputed_summary, dict) else {}
        labels = summary.get("labels", {}) if isinstance(summary, dict) else {}
        return ServiceResponse(
            200,
            {
                "run": str(run_dir),
                "ok": report.ok,
                "summary_matches": report.summary_matches,
                "summary": summary,
                "measured": bool(labels.get("measured")),
            },
        )

    def route(self, body: bytes) -> ServiceResponse:
        parsed = _load_json_object(body)
        if isinstance(parsed, ServiceResponse):
            return parsed
        task = parsed.get("task")
        if not isinstance(task, dict):
            return _error(400, "request body must include a 'task' object")
        try:
            pricing = self._resolve_pricing(parsed)
            trace = route_payload(
                task,
                signals=parsed.get("signals"),
                synth=bool(parsed.get("synth", False)),
                policy=self.policy,
                pricing=pricing,
            )
        except (ValueError, KeyError) as exc:
            return _error(400, str(exc))
        return ServiceResponse(200, {"trace": trace})

    def batch_route(self, body: bytes) -> ServiceResponse:
        parsed = _load_json_object(body)
        if isinstance(parsed, ServiceResponse):
            return parsed
        tasks = parsed.get("tasks")
        if not isinstance(tasks, list) or not all(isinstance(item, dict) for item in tasks):
            return _error(400, "request body must include a 'tasks' list of task objects")
        try:
            pricing = self._resolve_pricing(parsed)
            result = batch_route_payload(
                tasks,
                signals_by_task=parsed.get("signals"),
                synth=bool(parsed.get("synth", False)),
                policy=self.policy,
                pricing=pricing,
            )
        except (ValueError, KeyError) as exc:
            return _error(400, str(exc))
        return ServiceResponse(200, result)

    # -- dispatch ---------------------------------------------------------

    def dispatch(self, method: str, path: str, body: bytes = b"") -> ServiceResponse:
        route = path.split("?", 1)[0].rstrip("/") or "/"
        if method == "GET" and route in ("/", "/dashboard"):
            return self.dashboard()
        if method == "GET" and route == "/healthz":
            return self.healthz()
        if method == "GET" and route == "/policy":
            return self.policy_view()
        if method == "GET" and route == "/replay":
            return self.replay(path)
        if method == "GET" and route == "/regression":
            return self.regression()
        if method == "GET" and route == "/fanout-sweep":
            return self.fanout_sweep()
        if method == "GET" and route == "/compare":
            return self.compare_view(path)
        if method == "GET" and route == "/experiments":
            return self.experiments_view()
        if method == "GET" and route == "/experiment":
            return self.experiment_view(path)
        if method == "GET" and route == "/metrics/history":
            return self.metrics_history_view(path)
        if method == "GET" and route == "/fleet":
            return self.fleet_view()
        if method == "POST" and route == "/route":
            return self.route(body)
        if method == "POST" and route == "/batch-route":
            return self.batch_route(body)
        if method == "POST" and route == "/fleet/run":
            return self.fleet_run(body)
        if route.startswith("/cockpit/"):
            # Cockpit is inert unless a session token is set (dashboard --live).
            # The public/static build leaves it None, so these 404 and no live
            # surface ships. When enabled, every route needs the exact token.
            if not self.cockpit_token:
                return _error(404, f"not found: {route}")
            if not self._cockpit_authed(path):
                return _error(403, "cockpit requires a valid ?token=")
            if method == "GET" and route == "/cockpit/status":
                return self.cockpit_status()
            if method == "GET" and route == "/cockpit/plan":
                return self.cockpit_plan()
            if method == "GET" and route == "/cockpit/preview":
                return self.cockpit_preview()
            if method == "GET" and route == "/cockpit/catalog":
                return self.cockpit_catalog(path)
            if method == "GET" and route == "/cockpit/progress":
                return self.cockpit_progress(path)
            if method == "GET" and route == "/cockpit/snapshot":
                return self.cockpit_snapshot(path)
            if method == "POST" and route == "/cockpit/run":
                return self.cockpit_run(body)
            if method == "POST" and route == "/cockpit/abort":
                return self.cockpit_abort(body)
            return _error(404, f"not found: {route}")
        if route in _KNOWN_ROUTES:
            return _error(405, f"method {method} not allowed for {route}")
        return _error(404, f"not found: {route}")

    # -- helpers ----------------------------------------------------------

    def _fleet_registry(self) -> FleetRegistry:
        """Load (and cache) the bundled fleet registry, falling back to the in-code default."""

        if self._fleet is None:
            fleet_path = self._samples_root / "samples" / "fleet" / "foundry-5series.fleet.yaml"
            if fleet_path.is_file():
                self._fleet = FleetRegistry.from_yaml(fleet_path)
            else:
                self._fleet = FleetRegistry.default()
        return self._fleet

    def _recorded_arena_path(self) -> Path:
        return self._samples_root / "samples" / "responses" / "foundry-arena-measured.json"

    def _recorded_arena_report(self) -> dict[str, Any] | None:
        """Load the committed measured arena snapshot, relabeled honestly as recorded."""

        path = self._recorded_arena_path()
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        labels = dict(data.get("labels") or {})
        labels.update({"measured": False, "provenance": "recorded", "captured_from": "live"})
        # The router arm's stored amount omits the Model Router input-token
        # markup, so this publisher never republishes a savings figure with it.
        disclosure = router_cost_disclosure(root=self._samples_root)
        savings = data.get("router_vs_premium_savings_pct")
        arm_totals = self._publishable_arm_totals(data.get("arm_totals"), disclosure)
        report = {
            "tasks": data.get("tasks"),
            "arm_totals": arm_totals,
            "router_model_mix": data.get("router_model_mix"),
            "router_vs_premium_savings_pct": (
                savings if savings_claim_allowed(disclosure) else None
            ),
            "router_cost_disclosure": disclosure,
            "labels": labels,
            "captured_at": data.get("captured_at"),
        }
        return {"report": report, "fleet": data.get("resource")}

    @staticmethod
    def _publishable_arm_totals(
        arm_totals: Any, disclosure: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        """Withhold Router-derived amounts no verified annotation vouches for.

        With a valid annotation the amount is republished as historical output.
        Without one we cannot say which bytes produced it, so the affected arms
        carry ``None`` instead of a number a consumer might render as fact.
        Direct-model arms are never touched.
        """

        if not isinstance(arm_totals, Mapping):
            return arm_totals
        published = {arm: dict(totals) for arm, totals in arm_totals.items()}
        if historical_amount_showable(disclosure):
            return published
        for arm in disclosure.get("affected_arms") or ("router",):
            if arm in published:
                published[arm]["total_cost_usd"] = None
                published[arm]["cost_withheld"] = True
        return published

    def _resolve_pricing(self, body: dict[str, Any]) -> PricingTable | None:
        mode = body.get("pricing", "illustrative")
        if mode is None:
            return None
        key = str(mode).strip().lower()
        if key in _PRICING_OFF:
            return None
        if key in _PRICING_DEFAULT:
            return self.pricing
        raise ValueError(f"unknown pricing mode {mode!r}; use 'illustrative' or 'none'")

    def _runs(self) -> list[tuple[Experiment, ExperimentResult, ExperimentMetrics]]:
        """Run every experiment once and cache the (experiment, result, metrics) triples."""

        if self._experiment_runs is None:
            runs: list[tuple[Experiment, ExperimentResult, ExperimentMetrics]] = []
            for experiment in list_experiments():
                result = run_experiment(experiment)
                runs.append((experiment, result, extract_experiment_metrics(result)))
            self._experiment_runs = runs
        return self._experiment_runs

    def _history_rows(self) -> list[dict[str, Any]]:
        """Return the metrics history, seeding one deterministic row per experiment."""

        if self._history is None:
            seeded: list[dict[str, Any]] = []
            for index, (_exp, result, _metrics) in enumerate(self._runs(), start=1):
                stamped = extract_experiment_metrics(
                    result, recorded_at=_HISTORY_EPOCH.format(day=index)
                )
                seeded.append(stamped.to_dict())
            self._history = seeded
        return self._history

    @staticmethod
    def _experiment_card(
        experiment: Experiment,
        result: ExperimentResult,
        metrics: ExperimentMetrics,
    ) -> dict[str, Any]:
        summary = result.report.summary
        return {
            "name": experiment.name,
            "title": experiment.title,
            "summary": experiment.summary,
            "source": "synth" if experiment.synth else "fixture",
            "reproducible": result.ok,
            "metrics": metrics.to_dict(),
            "checks": [check.to_dict() for check in result.checks],
            "strategies": summary.get("strategies", {}),
            "spotlight": result.spotlight.to_dict() if result.spotlight else None,
        }


def _error(status: int, message: str) -> ServiceResponse:
    return ServiceResponse(status, {"error": message})


def _fleet_live_command(registry: FleetRegistry) -> str:
    """Two lines: persist this selection, then measure it live from the terminal."""

    roles = registry.role_assignments()
    ensemble = ",".join(roles["ensemble"])
    select = (
        "cost-router models select"
        f" --router {roles['router']}"
        f" --cheapest {roles['cheapest']}"
        f" --premium {roles['premium']}"
        f" --ensemble {ensemble}"
    )
    return select + "\ncost-router foundry arena --fleet .foundry-fleet.local.yaml --live"


def _query_flag(path: str, name: str) -> bool:
    values = parse_qs(urlsplit(path).query).get(name, ["false"])
    return str(values[0]).strip().lower() in _TRUTHY


def _query_value(path: str, name: str) -> str | None:
    values = parse_qs(urlsplit(path).query).get(name)
    return values[0].strip() if values and values[0].strip() else None


def _query_int(path: str, name: str, default: int) -> int:
    raw = _query_value(path, name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _load_json_object(body: bytes) -> dict[str, Any] | ServiceResponse:
    if not body:
        return _error(400, "request body must be a non-empty JSON object")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        return _error(400, f"invalid JSON: {exc}")
    if not isinstance(parsed, dict):
        return _error(400, "request body must be a JSON object")
    return parsed


class _RouterRequestHandler(BaseHTTPRequestHandler):
    """Adapts :class:`RouterService` onto the stdlib HTTP server."""

    service: RouterService
    server_version = "cost-router"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler name
        self._respond("GET")

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler name
        self._respond("POST")

    def _respond(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length > 0 else b""
        result = self.service.dispatch(method, self.path, body)
        if result.media_type.startswith("application/json"):
            data = json.dumps(result.payload).encode("utf-8")
        elif isinstance(result.payload, bytes):
            data = result.payload
        else:
            data = str(result.payload).encode("utf-8")
        self.send_response(result.status)
        self.send_header("Content-Type", result.media_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:  # noqa: D401 - silence default logging
        """Suppress the noisy default request logging."""


def make_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    service: RouterService | None = None,
    policy_path: str | None = None,
) -> ThreadingHTTPServer:
    """Build (but do not start) a threaded HTTP server bound to ``host:port``.

    The policy is resolved once here (``policy_path`` > ``COST_ROUTER_POLICY`` >
    bundled seed). Requests can never pick a different policy file.
    """

    if service is None:
        service = RouterService(policy=load_policy(policy_path))
    handler = type("RouterRequestHandler", (_RouterRequestHandler,), {"service": service})
    return ThreadingHTTPServer((host, port), handler)


def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    service: RouterService | None = None,
    policy_path: str | None = None,
    open_hint: str | None = None,
) -> int:
    """Run the offline routing service until interrupted.

    If ``port`` is already in use, the next few ports are tried automatically so
    a stale server never crashes the command with a traceback; the actually
    bound URL is printed. ``open_hint`` (e.g. ``"/?run=1"``) adds an
    "open this URL" line for the auto-running dashboard.
    """

    if service is None:
        service = RouterService(policy=load_policy(policy_path))
    httpd = _bind_with_fallback(host, port, service)
    if httpd is None:
        print(
            f"cost-router: port {port} and the next {_PORT_FALLBACK_TRIES} are busy on "
            f"{host}. Free one, or pass a different port: cost-router serve --port <N>.",
            flush=True,
        )
        return 1
    bound_host, bound_port = httpd.server_address[0], httpd.server_address[1]
    if bound_port != port:
        print(f"cost-router: port {port} was busy — using {bound_port} instead.", flush=True)
    print(f"cost-router serving on http://{bound_host}:{bound_port} (offline)", flush=True)
    if open_hint:
        print(f"open http://{bound_host}:{bound_port}{open_hint}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


def _bind_with_fallback(host: str, port: int, service: RouterService) -> ThreadingHTTPServer | None:
    """Bind on ``port`` or the next few ports; return ``None`` if all are busy."""

    for candidate in range(port, port + _PORT_FALLBACK_TRIES + 1):
        try:
            return make_server(host, candidate, service=service)
        except OSError:  # address already in use, etc.
            continue
    return None
