"""Tests for the static-site export (:mod:`scripts/build_static_site.py`).

The export is what we host on GitHub Pages under a project sub-path
(``…/foundry-cost-aware-model-routing/demo/``). The single most important
invariant is that the injected endpoint map uses **relative** paths — an
absolute ``/healthz.json`` would resolve to the domain root and break the demo
on project Pages. These tests lock that in.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "build_static_site.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_static_site", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("static-site")
    _load_builder().build(out)
    return out


def test_export_writes_all_files(site: Path) -> None:
    for name in (
        "index.html",
        "healthz.json",
        "policy.json",
        "replay-synth.json",
        "replay-curated.json",
        "regression.json",
        "fanout-sweep.json",
        "compare.json",
        "experiments.json",
        "metrics-history.json",
    ):
        assert (site / name).is_file(), f"missing {name}"


def test_injected_endpoints_are_relative(site: Path) -> None:
    html = (site / "index.html").read_text(encoding="utf-8")
    assert "window.__ENDPOINTS__" in html

    # Relative (no leading slash) so it works at any mount point.
    assert 'health: "healthz.json"' in html
    assert 'policy: "policy.json"' in html
    assert '"replay-synth.json"' in html
    assert '"replay-curated.json"' in html
    assert 'regression: "regression.json"' in html
    assert 'fanoutSweep: "fanout-sweep.json"' in html
    assert 'compare: "compare.json"' in html
    assert 'experiments: "experiments.json"' in html
    assert 'metricsHistory: "metrics-history.json"' in html

    # Absolute injected paths would break project-Pages sub-path hosting.
    for absolute in (
        '"/healthz.json"',
        '"/policy.json"',
        '"/replay-synth.json"',
        '"/replay-curated.json"',
        '"/regression.json"',
        '"/fanout-sweep.json"',
        '"/compare.json"',
        '"/experiments.json"',
        '"/metrics-history.json"',
    ):
        assert absolute not in html, f"endpoint must be relative, found {absolute}"


def test_endpoint_map_injected_before_dashboard_script(site: Path) -> None:
    html = (site / "index.html").read_text(encoding="utf-8")
    # The injected map must be set before the dashboard module reads it.
    assert html.index("window.__ENDPOINTS__") < html.index("const EP =")


def test_exported_json_is_valid_and_carries_spotlight(site: Path) -> None:
    for name in ("healthz.json", "policy.json"):
        json.loads((site / name).read_text(encoding="utf-8"))

    for name in ("replay-synth.json", "replay-curated.json"):
        payload = json.loads((site / name).read_text(encoding="utf-8"))
        spotlight = payload["summary"]["spotlight"]
        assert spotlight is not None
        assert spotlight["task_id"]
        assert spotlight["ratio"] > 1.0


def test_exported_regression_carries_coverage_cliff(site: Path) -> None:
    payload = json.loads((site / "regression.json").read_text(encoding="utf-8"))
    # The seed policy keeps full coverage; the naive cost-cut candidate collapses
    # to 67% — the honest coverage cliff the dashboard panel visualizes.
    assert payload["base"]["coverage"] == pytest.approx(1.0)
    assert payload["candidate"]["coverage"] == pytest.approx(0.67)
    assert payload["coverage_delta"] == pytest.approx(-0.33)
    assert payload["measured"] is False


def test_exported_fanout_sweep_carries_the_dial(site: Path) -> None:
    payload = json.loads((site / "fanout-sweep.json").read_text(encoding="utf-8"))
    # Four notches on the dial; coverage flat, ensemble tax collapsing to zero —
    # the honest experiment 05-vs-06 story the sweep panel visualizes.
    assert payload["measured"] is False
    rows = payload["rows"]
    assert {row["fanout_tasks"] for row in rows} == {6, 5, 1, 0}
    assert all(row["coverage"] == pytest.approx(1.0) for row in rows)
    assert rows[0]["ensemble_tax_usd"] == pytest.approx(0.364011, abs=1e-6)
    assert rows[-1]["ensemble_tax_usd"] == pytest.approx(0.0)


def test_exported_compare_carries_the_arena(site: Path) -> None:
    payload = json.loads((site / "compare.json").read_text(encoding="utf-8"))
    # The head-to-head "one problem, four ways" payload the arena panel renders:
    # a task menu plus every task's four approaches, default = the instructive one.
    assert payload["labels"]["measured"] is False
    assert payload["default"] == "t-0003"
    arena = payload["arenas"]["t-0003"]
    by = {a["approach"]: a for a in arena["approaches"]}
    assert [a["approach"] for a in arena["approaches"]] == [
        "cheapest",
        "premium",
        "ensemble",
        "router",
    ]
    # winner-only router vs sum-of-all ensemble — the honest cost gap on one task
    assert by["router"]["cost_usd"] == pytest.approx(0.032793, abs=1e-6)
    assert by["ensemble"]["cost_usd"] == pytest.approx(0.179844, abs=1e-6)
    assert arena["winners"]["cost"] == "router"
    assert arena["winners"]["latency"] == "premium"
    assert set(arena["winners"]["accuracy"]) == {"premium", "ensemble", "router"}
    # the exported arena also carries the authored, readable problem statement
    assert arena["problem"]["title"] == "Patch parse_duration to accept combined units"
    assert arena["labels"]["problem_basis"] == "authored-synthetic"
    assert {t["task_id"]: t["title"] for t in payload["tasks"]}["t-0001"] == "slugify(title)"


def test_exported_experiments_carry_offline_metrics(site: Path) -> None:
    payload = json.loads((site / "experiments.json").read_text(encoding="utf-8"))
    cards = payload["experiments"]
    names = {card["name"] for card in cards}
    assert {"hero", "curated", "ensemble", "limits"} <= names
    ensemble = next(card for card in cards if card["name"] == "ensemble")
    metrics = ensemble["metrics"]
    assert metrics["measured"] is False
    # pure projection: no wall-clock timestamp in the static export.
    assert metrics["recorded_at"] is None
    assert metrics["ensemble_tax_usd"] == pytest.approx(0.364011, abs=1e-6)


def test_exported_history_is_deterministic(site: Path) -> None:
    payload = json.loads((site / "metrics-history.json").read_text(encoding="utf-8"))
    history = payload["history"]
    assert {row["experiment"] for row in history} >= {"hero", "curated", "ensemble", "limits"}
    # deterministic seed timestamps keep the Pages demo reproducible.
    assert all(row["recorded_at"].startswith("2026-01-") for row in history)
    assert all(row["measured"] is False for row in history)
