"""Tests for the offline HTTP routing service (:mod:`router.server`)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from router.offline import load_workload
from router.server import RouterService, make_server

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = ROOT / "samples" / "telemetry" / "mixed-coding-workload.sample.jsonl"

PLACEHOLDER_MODELS = {
    "mini-fast",
    "swift-coder",
    "balanced-pro",
    "deep-reasoner",
    "premium-max",
}

SAMPLE_TASK = {
    "task_id": "t-0001",
    "class": "generate",
    "difficulty": "easy",
    "tokens": {"input": 1232, "cached": 448, "output": 418, "reasoning": 168},
}


@pytest.fixture()
def service() -> RouterService:
    return RouterService()


def _post(service: RouterService, path: str, payload: dict) -> tuple[int, dict]:
    response = service.dispatch("POST", path, json.dumps(payload).encode("utf-8"))
    return response.status, response.payload


def test_healthz_reports_offline(service: RouterService) -> None:
    response = service.dispatch("GET", "/healthz")
    assert response.status == 200
    assert response.payload["status"] == "ok"
    assert response.payload["offline"] is True
    assert response.payload["version"] == "0.1.0"


def test_policy_lists_candidates_per_class(service: RouterService) -> None:
    response = service.dispatch("GET", "/policy")
    assert response.status == 200
    assert response.payload["version"] == 1
    classes = response.payload["classes"]
    assert set(classes) == {"plan", "generate", "test", "validate", "repo_patch"}
    generate = classes["generate"]
    assert [c["rank"] for c in generate] == list(range(len(generate)))
    assert all(c["model"] in PLACEHOLDER_MODELS for c in generate)


def test_route_synth_returns_trace_with_cost(service: RouterService) -> None:
    status, payload = _post(service, "/route", {"task": SAMPLE_TASK, "synth": True})
    assert status == 200
    trace = payload["trace"]
    assert trace["task_id"] == "t-0001"
    assert trace["chosen"] in PLACEHOLDER_MODELS
    assert trace["cost_usd"] > 0.0


def test_route_is_deterministic(service: RouterService) -> None:
    first = _post(service, "/route", {"task": SAMPLE_TASK, "synth": True})
    second = _post(service, "/route", {"task": SAMPLE_TASK, "synth": True})
    assert first == second


def test_route_pricing_none_disables_cost(service: RouterService) -> None:
    status, payload = _post(
        service, "/route", {"task": SAMPLE_TASK, "synth": True, "pricing": "none"}
    )
    assert status == 200
    assert payload["trace"]["cost_usd"] is None


def test_route_accepts_explicit_signals(service: RouterService) -> None:
    signals = {
        "mini-fast": {"applies": True, "compiles": True, "tests_pass": True, "lint_pass": True},
    }
    status, payload = _post(service, "/route", {"task": SAMPLE_TASK, "signals": signals})
    assert status == 200
    assert payload["trace"]["chosen"] == "mini-fast"


def test_batch_route_matches_known_synth_totals(service: RouterService) -> None:
    tasks = list(load_workload(WORKLOAD).values())
    status, payload = _post(service, "/batch-route", {"tasks": tasks, "synth": True})
    assert status == 200
    assert len(payload["traces"]) == 100
    summary = payload["summary"]
    assert summary["tasks"] == 100
    assert summary["accepted"] == 100
    assert summary["coverage"] == 1.0
    assert summary["total_cost_usd"] == 1.659167
    assert summary["mode_counts"] == {"ordered": 74, "compare": 26}
    assert summary["reason_counts"] == {
        "clean-first": 19,
        "escalated": 55,
        "compared": 18,
        "tie-broken": 8,
    }


def test_batch_route_only_uses_placeholder_models(service: RouterService) -> None:
    tasks = list(load_workload(WORKLOAD).values())
    _, payload = _post(service, "/batch-route", {"tasks": tasks, "synth": True})
    chosen = {trace["chosen"] for trace in payload["traces"]}
    assert chosen <= PLACEHOLDER_MODELS


def test_unknown_route_is_404(service: RouterService) -> None:
    assert service.dispatch("GET", "/nope").status == 404


def test_wrong_method_is_405(service: RouterService) -> None:
    assert service.dispatch("POST", "/healthz").status == 405
    assert service.dispatch("GET", "/route").status == 405


def test_invalid_json_is_400(service: RouterService) -> None:
    response = service.dispatch("POST", "/route", b"{not json")
    assert response.status == 400
    assert "error" in response.payload


def test_missing_task_is_400(service: RouterService) -> None:
    status, payload = _post(service, "/route", {"synth": True})
    assert status == 400
    assert "task" in payload["error"]


def test_batch_missing_tasks_is_400(service: RouterService) -> None:
    status, payload = _post(service, "/batch-route", {"synth": True})
    assert status == 400
    assert "tasks" in payload["error"]


def test_unknown_pricing_mode_is_400(service: RouterService) -> None:
    status, payload = _post(service, "/route", {"task": SAMPLE_TASK, "pricing": "live"})
    assert status == 400
    assert "pricing" in payload["error"]


def test_loopback_server_round_trip() -> None:
    httpd = make_server("127.0.0.1", 0)
    host, port = httpd.server_address[0], httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/healthz", timeout=5) as resp:
            assert resp.status == 200
            health = json.loads(resp.read())
        assert health["status"] == "ok"

        body = json.dumps({"task": SAMPLE_TASK, "synth": True}).encode("utf-8")
        request = urllib.request.Request(
            f"http://{host}:{port}/route", data=body, method="POST"
        )
        with urllib.request.urlopen(request, timeout=5) as resp:
            assert resp.status == 200
            trace = json.loads(resp.read())["trace"]
        assert trace["chosen"] in PLACEHOLDER_MODELS

        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(f"http://{host}:{port}/missing", timeout=5)
        assert excinfo.value.code == 404
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
