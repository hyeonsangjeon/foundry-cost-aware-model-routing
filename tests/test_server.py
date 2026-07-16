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


def test_dashboard_autoruns_in_hero_mode(service: RouterService) -> None:
    html = service.dispatch("GET", "/").payload
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    # cost-router hero --serve opens ?run=1 so the before/after animates on load.
    assert "URLSearchParams" in script
    assert 'q.get("run")' in script
    # auto-run is chained after loadPolicy() so MODEL_ORDER is ready first.
    assert "loadPolicy().then(" in script


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


def test_dashboard_shows_three_way_strategy_comparison(service: RouterService) -> None:
    html = service.dispatch("GET", "/").payload
    # P1: three labeled strategies, each with its own cost + coverage element.
    for label in ("all-mini", "all-premium", "cost-aware mix"):
        assert label in html
    for cost_id in ('id="miniVal"', 'id="premVal"', 'id="afterVal"'):
        assert cost_id in html
    for cov_id in ('id="miniCov"', 'id="premCov"', 'id="mixCov"'):
        assert cov_id in html
    # coverage pills carry a shared style with an ok/warn split.
    assert ".covpill" in html
    assert ".covpill.warn" in html
    # a takeaway sentence states the conclusion.
    assert 'id="takeaway"' in html


def test_dashboard_shows_cost_coverage_frontier(service: RouterService) -> None:
    html = service.dispatch("GET", "/").payload
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    # A cost x coverage scatter makes the trade-off frontier explicit: only the
    # cost-aware mix reaches the top-left (full coverage, low cost) corner.
    assert 'id="frontier"' in html
    assert "trade-off frontier" in html
    assert "renderFrontier" in script
    # rendered from the same strategies payload and wired into the replay run.
    assert "s.strategies" in script
    assert "renderFrontier(s)" in script
    # it draws an inline SVG scatter (no external chart lib) with a both-win zone.
    assert "<svg" in script and "<circle" in script
    assert "both-win zone" in script


def test_regression_endpoint_returns_coverage_cliff(service: RouterService) -> None:
    response = service.dispatch("GET", "/regression")
    assert response.status == 200
    payload = response.payload
    # seed policy keeps full coverage; the naive cost-cut candidate collapses.
    assert payload["base"]["coverage"] == pytest.approx(1.0)
    assert payload["base"]["routed_total_usd"] == pytest.approx(1.659167, abs=1e-6)
    assert payload["candidate"]["coverage"] == pytest.approx(0.67)
    assert payload["candidate"]["routed_total_usd"] == pytest.approx(0.727969, abs=1e-6)
    assert payload["coverage_delta"] == pytest.approx(-0.33)
    assert payload["measured"] is False
    # it is a GET-only route.
    assert service.dispatch("POST", "/regression").status == 405


def test_dashboard_shows_coverage_cliff_panel(service: RouterService) -> None:
    html = service.dispatch("GET", "/").payload
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    # A dedicated policy-A/B panel visualizes the coverage cliff from experiment 03.
    assert 'id="cliffPanel"' in html
    assert "Coverage cliff" in html
    for element_id in ('id="cliffBaseBar"', 'id="cliffCandBar"', 'id="cliffDrop"'):
        assert element_id in html
    # rendered from the /regression endpoint and wired into the replay run.
    assert "renderCliff" in script
    assert "regression:" in script  # EP fallback map carries the route
    assert "fetch(EP.regression)" in script


def test_render_cliff_sets_bars_and_delta(service: RouterService, tmp_path) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    html = service.dispatch("GET", "/").payload
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    render = re.search(r"function renderCliff\(r\) \{.*?\n\}", script, re.S)
    assert render, "renderCliff must be present"
    program = (
        "const els = {};\n"
        "function $(id){ if(!els[id]) els[id]={style:{}}; return els[id]; }\n"
        "function usd(n){ return '$' + Number(n).toFixed(2); }\n"
        "function pct(n){ return (n*100).toFixed(1) + '%'; }\n"
        + render.group(0) + "\n"
        "renderCliff({base:{coverage:1.0,routed_total_usd:1.659167},"
        "candidate:{coverage:0.67,routed_total_usd:0.727969},coverage_delta:-0.33});\n"
        "if (els.cliffBaseBar.style.width !== '100.0%') throw new Error('base bar');\n"
        "if (els.cliffCandBar.style.width !== '67.0%') throw new Error('cand bar');\n"
        "if (els.cliffBaseCov.textContent !== '100.0%') throw new Error('base cov');\n"
        "if (els.cliffCandCov.textContent !== '67.0%') throw new Error('cand cov');\n"
        "if (els.cliffDrop.textContent.indexOf('33') < 0) throw new Error('drop pts');\n"
        "if (els.cliffTakeaway.textContent.indexOf('dropped work') < 0)"
        " throw new Error('takeaway');\n"
        "if (els.cliffPanel.hidden !== false) throw new Error('panel must reveal');\n"
        "console.log('ok');\n"
    )
    js = tmp_path / "cliff.js"
    js.write_text(program, encoding="utf-8")
    proc = subprocess.run([node, str(js)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


def test_dashboard_headline_names_the_mechanism(service: RouterService) -> None:
    html = service.dispatch("GET", "/").payload
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    # P3: headline names cheap-first + selective escalation, not just the %.
    assert "cheap-first routing" in script
    assert "needed the top" in script
    # count comes from the run's top-tier usage, not a hard-coded number.
    assert "MODEL_ORDER" in script and "by_model" in script


def test_dashboard_states_cheap_vs_premium_volume_split(service: RouterService) -> None:
    html = service.dispatch("GET", "/").payload
    # P2: usage panel carries a split line filled from real counts.
    assert 'id="usageSplit"' in html
    assert "renderUsageSplit" in html
    assert "Cheap tiers carried the volume" in html


def test_dashboard_run_button_is_reentrancy_safe(service: RouterService) -> None:
    html = service.dispatch("GET", "/").payload
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    # Bug fix: rapid clicks must not stack runs, and the button must always
    # re-enable even if rendering throws (try/finally).
    assert "let running = false" in script
    assert "if (running) return" in script
    assert "} finally {" in script
    assert "btn.disabled = false" in script


def test_render_strategies_wires_costs_coverage_and_takeaway(
    service: RouterService, tmp_path
) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    html = service.dispatch("GET", "/").payload
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    set_cov = re.search(r"function setCov\(id, cov\) \{.*?\n\}", script, re.S)
    render = re.search(r"function renderStrategies\(s\) \{.*?\n\}", script, re.S)
    assert set_cov and render, "setCov + renderStrategies must be present"
    program = (
        "const els = {};\n"
        "function $(id){ if(!els[id]) els[id]={style:{}}; return els[id]; }\n"
        "function usd(n){ return '$' + Number(n).toFixed(2); }\n"
        "function pct(n){ return (n*100).toFixed(1) + '%'; }\n"
        "function coverageState(cov){ return {warn: cov < 1, "
        "note: cov < 1 ? 'coverage dropped' : ''}; }\n"
        + set_cov.group(0) + "\n" + render.group(0) + "\n"
        "renderStrategies({strategies:{all_mini:{total_cost_usd:0.187913,coverage:0.22},"
        "all_premium:{total_cost_usd:2.226910,coverage:1},"
        "mix:{total_cost_usd:1.659167,coverage:1}},coverage:1,"
        "baseline_total_usd:2.226910,total_cost_usd:1.659167});\n"
        "if (els.premVal.textContent !== '$2.23') throw new Error('prem cost');\n"
        "if (els.miniVal.textContent !== '$0.19') throw new Error('mini cost');\n"
        "if (els.premBar.style.width !== '100%') throw new Error('prem scale');\n"
        "if (els.miniCov.className.indexOf('warn') < 0) throw new Error('mini must warn');\n"
        "if (els.premCov.className.indexOf('ok') < 0) throw new Error('prem must be ok');\n"
        "if (els.mixCov.className.indexOf('ok') < 0) throw new Error('mix must be ok');\n"
        "if (!/22.0%/.test(els.takeaway.textContent)) throw new Error('takeaway coverage');\n"
        "console.log('ok');\n"
    )
    js = tmp_path / "strat.js"
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


def test_replay_synth_includes_spotlight(service: RouterService) -> None:
    summary = service.dispatch("GET", "/replay?synth=true").payload["summary"]
    spot = summary["spotlight"]
    # The auto spotlight is the accepted task with the widest naive/routed gap.
    assert spot["task_id"] == "t-0078"
    assert spot["class"] == "validate"
    assert spot["chosen_model"] == "mini-fast"
    assert spot["naive_model"] == "deep-reasoner"
    assert spot["accepted"] is True
    assert spot["naive_usd"] > spot["routed_usd"] > 0.0
    assert spot["ratio"] == pytest.approx(24.09, abs=0.1)
    assert spot["chosen_model"] in PLACEHOLDER_MODELS
    assert spot["naive_model"] in PLACEHOLDER_MODELS


def test_replay_curated_includes_spotlight(service: RouterService) -> None:
    summary = service.dispatch("GET", "/replay?synth=false").payload["summary"]
    spot = summary["spotlight"]
    assert spot["task_id"] == "t-0005"
    assert spot["accepted"] is True
    assert spot["ratio"] > 1.0
    # ratio reconciles with the two costs it is derived from.
    assert spot["ratio"] == pytest.approx(spot["naive_usd"] / spot["routed_usd"], abs=0.01)


def test_dashboard_shows_spotlight_panel(service: RouterService) -> None:
    html = service.dispatch("GET", "/").payload
    # A dedicated spotlight panel with both arms and the ratio element.
    assert 'id="spotlightPanel"' in html
    for element_id in (
        'id="spotMeta"',
        'id="spotRoutedModel"',
        'id="spotRoutedCost"',
        'id="spotNaiveModel"',
        'id="spotNaiveCost"',
        'id="spotRatio"',
    ):
        assert element_id in html
    # rendered from the replay summary's spotlight field.
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert "renderSpotlight" in script
    assert "s.spotlight" in script


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


# -- experiments & metrics endpoints (web app + historical dashboard) --------

def test_experiments_endpoint_lists_cards_with_metrics(service: RouterService) -> None:
    payload = service.dispatch("GET", "/experiments").payload
    cards = payload["experiments"]
    names = {card["name"] for card in cards}
    assert {"hero", "curated", "ensemble", "limits"} <= names
    ensemble = next(card for card in cards if card["name"] == "ensemble")
    metrics = ensemble["metrics"]
    assert metrics["ensemble_tax_usd"] == pytest.approx(0.364011, abs=1e-6)
    assert metrics["tax_ratio"] == pytest.approx(3.741, abs=1e-3)
    assert metrics["measured"] is False
    assert metrics["recorded_at"] is None  # pure projection, no clock
    assert ensemble["reproducible"] is True
    assert {check["name"] for check in ensemble["checks"]} == {"coverage", "savings", "tasks"}
    assert "all_ensemble" in ensemble["strategies"] or ensemble["strategies"] == {}


def test_experiments_endpoint_is_get_only(service: RouterService) -> None:
    assert service.dispatch("POST", "/experiments").status == 405


def test_experiment_detail_runs_and_records(service: RouterService) -> None:
    response = service.dispatch("GET", "/experiment?name=ensemble")
    assert response.status == 200
    metrics = response.payload["metrics"]
    assert metrics["experiment"] == "ensemble"
    assert metrics["recorded_at"] is not None  # live run stamps the clock
    assert response.payload["result"]["ok"] is True


def test_experiment_detail_missing_name_is_400(service: RouterService) -> None:
    assert service.dispatch("GET", "/experiment").status == 400


def test_experiment_detail_unknown_name_is_404(service: RouterService) -> None:
    assert service.dispatch("GET", "/experiment?name=nope").status == 404


def test_metrics_history_seeds_one_row_per_experiment(service: RouterService) -> None:
    payload = service.dispatch("GET", "/metrics/history").payload
    history = payload["history"]
    experiments = {row["experiment"] for row in history}
    assert {"hero", "curated", "ensemble", "limits"} <= experiments
    # deterministic seed timestamps so the static export is reproducible.
    assert all(row["recorded_at"].startswith("2026-01-") for row in history)
    assert "latest" in payload


def test_metrics_history_grows_after_a_live_run(service: RouterService) -> None:
    before = len(service.dispatch("GET", "/metrics/history").payload["history"])
    service.dispatch("GET", "/experiment?name=ensemble")
    after = service.dispatch("GET", "/metrics/history").payload["history"]
    assert len(after) == before + 1
    assert after[-1]["experiment"] == "ensemble"


def test_metrics_history_filters_by_experiment(service: RouterService) -> None:
    payload = service.dispatch("GET", "/metrics/history?experiment=hero").payload
    assert [row["experiment"] for row in payload["history"]] == ["hero"]


def test_metrics_store_persists_live_runs(tmp_path) -> None:
    from router.metrics import JsonlMetricsStore

    store = JsonlMetricsStore(tmp_path / "history.jsonl")
    service = RouterService(metrics_store=store)
    service.dispatch("GET", "/experiment?name=curated")
    assert len(store.history()) == 1
    assert store.history()[0]["experiment"] == "curated"


def test_dashboard_shows_experiments_and_history_panels(service: RouterService) -> None:
    html = service.dispatch("GET", "/").payload
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert 'id="experimentsPanel"' in html
    assert 'id="historyPanel"' in html
    assert 'id="expTabs"' in html
    assert 'id="histBody"' in html
    # wired to the metrics endpoints and invoked on load.
    assert "loadExperiments" in script
    assert "loadHistory" in script
    assert "experiments:" in script  # EP fallback map carries the routes
    assert "metricsHistory:" in script
