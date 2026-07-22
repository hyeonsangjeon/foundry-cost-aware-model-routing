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
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import __version__
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
        report = {
            "tasks": data.get("tasks"),
            "arm_totals": data.get("arm_totals"),
            "router_model_mix": data.get("router_model_mix"),
            "router_vs_premium_savings_pct": data.get("router_vs_premium_savings_pct"),
            "labels": labels,
            "captured_at": data.get("captured_at"),
        }
        return {"report": report, "fleet": data.get("resource")}

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
