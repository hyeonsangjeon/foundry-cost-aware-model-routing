"""Regeneration guard for the committed 03D Korean charts.

The 03D dashboard commits three Korean SVGs (``arm-cost-comparison.svg``,
``cost-vs-quality-scatter.svg``, ``backend-distribution.svg``) plus a tracked,
tenant-masked ``published.json``. ``test_localize_03d_svgs`` already proves the
English ``.en.svg`` siblings are a faithful ``localize()`` of the Korean source —
but nothing proved the Korean source itself still matches the generator. A
hand-edited ko chart, or a ``published.json`` that drifted from the renderer,
would have slipped through.

This test closes that gap: it runs the real ``--charts-only`` render path
(``write_charts`` reading the tracked bundle) into a temp dir and asserts the
output equals the committed Korean SVGs byte for byte. Offline — the render path
reads only ``published.json`` and never touches the sealed run or Azure.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = REPO_ROOT / "scripts" / "build_03d_dashboard.py"
_COMMITTED_DIR = REPO_ROOT / "docs" / "assets" / "03d"

_spec = importlib.util.spec_from_file_location("build_03d_dashboard", _MODULE_PATH)
assert _spec and _spec.loader
dash = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dash
_spec.loader.exec_module(dash)

# The tracked bundle the public --charts-only path re-renders from. Captured from
# the module's original OUT_DIR before any test monkeypatches it.
_BUNDLE = json.loads(dash.BUNDLE_PATH.read_text(encoding="utf-8"))

# The three committed Korean charts (the base .svg, which the ko pages embed and
# localize_03d_svgs turns into the .en.svg siblings).
_KO_CHARTS = (
    "arm-cost-comparison.svg",
    "cost-vs-quality-scatter.svg",
    "backend-distribution.svg",
)


def _render_into(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Run the real write_charts (the --charts-only render) into a temp dir."""
    tmp_path.mkdir(parents=True, exist_ok=True)  # main() mkdirs OUT_DIR; mirror it
    monkeypatch.setattr(dash, "OUT_DIR", tmp_path)
    written = dash.write_charts(_BUNDLE)
    return {p.name: p.read_text(encoding="utf-8") for p in written}


@pytest.mark.parametrize("name", _KO_CHARTS)
def test_committed_ko_svg_matches_charts_only_render(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The committed Korean chart must equal a fresh --charts-only render of the
    # tracked bundle, so no hand-edited chart (and no bundle drift) can survive.
    rendered = _render_into(tmp_path, monkeypatch)
    assert name in rendered, f"{name} is no longer produced by write_charts"
    committed = (_COMMITTED_DIR / name).read_text(encoding="utf-8")
    assert committed == rendered[name], (
        f"{name} has drifted from `build_03d_dashboard.py --charts-only`; "
        f"regenerate it instead of editing by hand"
    )


def test_charts_only_render_is_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Byte-stability is what lets the committed charts be a regression target.
    first = _render_into(tmp_path / "a", monkeypatch)
    second = _render_into(tmp_path / "b", monkeypatch)
    assert first == second


def test_render_covers_exactly_the_committed_charts() -> None:
    # If a chart is added or renamed, this list (and the committed set) must move
    # together — otherwise the regeneration guard above would silently skip it.
    committed = {p.name for p in _COMMITTED_DIR.glob("*.svg") if not p.name.endswith(".en.svg")}
    assert committed == set(_KO_CHARTS)
