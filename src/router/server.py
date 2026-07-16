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
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .dashboard import DASHBOARD_HTML
from .pipeline import (
    batch_route_payload,
    bundled_coverage_cliff,
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
    "/route",
    "/batch-route",
}
_PRICING_OFF = {"none", "off", "disabled", "false"}
_PRICING_DEFAULT = {"illustrative", "default", "sample", "on", "true"}
_TRUTHY = {"1", "true", "yes", "on"}


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
    ) -> None:
        self.policy = policy or load_policy()
        if pricing is not None:
            self.pricing: PricingTable | None = pricing
        else:
            try:
                self.pricing = load_default_pricing()
            except FileNotFoundError:
                self.pricing = None

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
        if method == "POST" and route == "/route":
            return self.route(body)
        if method == "POST" and route == "/batch-route":
            return self.batch_route(body)
        if route in _KNOWN_ROUTES:
            return _error(405, f"method {method} not allowed for {route}")
        return _error(404, f"not found: {route}")

    # -- helpers ----------------------------------------------------------

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


def _error(status: int, message: str) -> ServiceResponse:
    return ServiceResponse(status, {"error": message})


def _query_flag(path: str, name: str) -> bool:
    values = parse_qs(urlsplit(path).query).get(name, ["false"])
    return str(values[0]).strip().lower() in _TRUTHY


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
) -> int:
    """Run the offline routing service until interrupted."""

    httpd = make_server(host, port, service=service, policy_path=policy_path)
    bound_host, bound_port = httpd.server_address[0], httpd.server_address[1]
    print(f"cost-router serving on http://{bound_host}:{bound_port} (offline)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
