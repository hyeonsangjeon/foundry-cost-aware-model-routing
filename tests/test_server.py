"""Tests for the offline HTTP routing service (:mod:`router.server`)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from router.offline import load_workload
from router.pipeline import load_policy
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
    # every candidate carries its vendor-neutral tier/role description
    assert all(c["tier"] and c["role"] for c in generate)


def test_policy_serves_model_catalog(service: RouterService) -> None:
    catalog = service.dispatch("GET", "/policy").payload["catalog"]
    assert [c["model"] for c in catalog] == [
        "mini-fast",
        "swift-coder",
        "balanced-pro",
        "deep-reasoner",
        "premium-max",
    ]
    assert all({"model", "tier", "reasoning", "role"} <= set(c) for c in catalog)


def test_dashboard_explains_model_tiers(service: RouterService) -> None:
    html = service.dispatch("GET", "/").payload
    assert "Model tiers" in html
    assert "tiertag" in html


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


def test_dashboard_serves_offline_html(service: RouterService) -> None:
    for route in ("/", "/dashboard"):
        response = service.dispatch("GET", route)
        assert response.status == 200
        assert response.media_type.startswith("text/html")
        assert "<!DOCTYPE html>" in response.payload
        assert "cost-router" in response.payload
        assert "labels.measured=false" in response.payload


def test_dashboard_has_no_external_references(service: RouterService) -> None:
    html = service.dispatch("GET", "/").payload
    # offline + public-scope: no CDN/font/script origins of any kind.
    for needle in ("http://", "https://", "//cdn", "src=\"//"):
        assert needle not in html


def test_dashboard_inline_script_is_well_formed(service: RouterService, tmp_path) -> None:
    html = service.dispatch("GET", "/").payload
    match = re.search(r"<script>(.*)</script>", html, re.S)
    assert match, "dashboard must contain an inline <script> block"
    script = match.group(1)
    # A '\"' collapsed by Python triple-quote escaping corrupts a JS attribute
    # into an empty-string concat like: title="" + var. Guard against that class.
    assert '="" +' not in script
    assert '="">' not in script
    # If a JS engine is available, do a real syntax check too.
    node = shutil.which("node")
    if node:
        js = tmp_path / "dashboard.js"
        js.write_text(script, encoding="utf-8")
        proc = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr


def test_dashboard_rounds_away_false_precision(service: RouterService) -> None:
    html = service.dispatch("GET", "/").payload
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    # P1.1: six-decimal dollars read as fake precision — must not appear anywhere.
    assert "toFixed(6)" not in script
    # totals use a 2-decimal formatter; sub-cent values fall back to 4.
    assert "toFixed(2)" in script
    assert "usdSmart" in script and "usdAvg" in script


def test_dashboard_shows_workload_mix_caveat(service: RouterService) -> None:
    html = service.dispatch("GET", "/").payload
    # P1.2: caveat sits next to the headline, not only in the footer.
    assert "Savings depend on workload mix" in html
    assert 'id="mixCaveat"' in html
    # honesty labels must remain intact.
    assert "labels.measured=false" in html
    assert "offline projection over synthetic data" in html


def test_dashboard_has_coverage_guard_affordances(service: RouterService) -> None:
    html = service.dispatch("GET", "/").payload
    # P2.4: a coverage < 100% run must be able to flip to a warning state.
    assert 'id="covNote"' in html
    assert "coverage dropped" in html
    assert ".covnote" in html  # warning style is defined
    assert ".v.warn" in html   # coverage KPI can turn red


def test_coverage_state_warns_below_full(service: RouterService, tmp_path) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    html = service.dispatch("GET", "/").payload
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    fn = re.search(r"function coverageState\(cov\) \{.*?\n\}", script, re.S)
    assert fn, "coverageState function must be present"
    program = fn.group(0) + (
        "\nconst full = coverageState(1);"
        "\nconst low = coverageState(0.9);"
        "\nif (full.warn !== false) throw new Error('full should not warn');"
        "\nif (low.warn !== true) throw new Error('low should warn');"
        "\nif (!/coverage dropped/.test(low.note)) throw new Error('missing note');"
        "\nconsole.log('ok');\n"
    )
    js = tmp_path / "cov.js"
    js.write_text(program, encoding="utf-8")
    proc = subprocess.run([node, str(js)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


def test_replay_curated_reports_before_after(service: RouterService) -> None:
    response = service.dispatch("GET", "/replay?synth=false")
    assert response.status == 200
    summary = response.payload["summary"]
    assert summary["tasks"] == 5
    assert summary["total_cost_usd"] == 0.055038
    assert summary["baseline_total_usd"] == 0.127136
    assert summary["delta_usd"] == 0.072098
    assert summary["measured"] is False
    assert summary["baseline_total_usd"] > summary["total_cost_usd"]


def test_replay_synth_matches_known_totals(service: RouterService) -> None:
    response = service.dispatch("GET", "/replay?synth=true")
    payload = response.payload
    assert len(payload["traces"]) == 100
    summary = payload["summary"]
    assert summary["tasks"] == 100
    assert summary["total_cost_usd"] == 1.659167
    assert summary["baseline_total_usd"] == 2.226910
    assert summary["delta_usd"] == 0.567743
    assert summary["measured"] is False
    chosen = {trace["chosen"] for trace in payload["traces"]}
    assert chosen <= PLACEHOLDER_MODELS


def test_replay_defaults_to_curated(service: RouterService) -> None:
    assert service.dispatch("GET", "/replay").payload["summary"]["tasks"] == 5


def test_replay_includes_aggregated_breakdown(service: RouterService) -> None:
    summary = service.dispatch("GET", "/replay?synth=true").payload["summary"]
    breakdown = summary["breakdown"]
    assert set(breakdown) == {"by_class", "by_model", "mode_cost_usd", "reason_counts"}

    by_class = breakdown["by_class"]
    assert set(by_class) == {"plan", "generate", "test", "validate", "repo_patch"}
    # per-class routed/baseline costs reconcile with the top-line totals
    assert round(sum(c["routed_usd"] for c in by_class.values()), 6) == summary["total_cost_usd"]
    assert (
        round(sum(c["baseline_usd"] for c in by_class.values()), 6)
        == summary["baseline_total_usd"]
    )
    for bucket in by_class.values():
        assert bucket["saved_usd"] == round(bucket["baseline_usd"] - bucket["routed_usd"], 6)

    by_model = breakdown["by_model"]
    assert set(by_model) <= PLACEHOLDER_MODELS
    assert sum(m["tasks"] for m in by_model.values()) == summary["tasks"]
    assert sum(breakdown["reason_counts"].values()) == summary["tasks"]


def test_replay_uses_injected_policy() -> None:
    candidate = ROOT / "samples" / "policy" / "candidate.example.yaml"
    injected = RouterService(policy=load_policy(candidate))
    seeded = RouterService()
    injected_total = injected.dispatch("GET", "/replay?synth=true").payload["summary"][
        "total_cost_usd"
    ]
    seeded_total = seeded.dispatch("GET", "/replay?synth=true").payload["summary"][
        "total_cost_usd"
    ]
    assert injected_total != seeded_total


def test_wrong_method_is_405(service: RouterService) -> None:
    assert service.dispatch("POST", "/healthz").status == 405
    assert service.dispatch("GET", "/route").status == 405
    assert service.dispatch("POST", "/replay").status == 405


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
