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

    # Absolute injected paths would break project-Pages sub-path hosting.
    for absolute in (
        '"/healthz.json"',
        '"/policy.json"',
        '"/replay-synth.json"',
        '"/replay-curated.json"',
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
