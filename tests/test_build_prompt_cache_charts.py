"""Unit tests for :mod:`scripts.build_prompt_cache_charts`.

The two prompt-cache charts are generated from the sealed runs, which are
gitignored. What is tracked is the small aggregate bundle plus the four rendered
SVGs, so these tests lock the half of the pipeline that CI can actually run:
rendering from the tracked bundle must reproduce the committed SVGs byte for
byte (no hand-edited chart can survive), the figures the charts draw must equal
the figures the explainer page publishes in its tables (chart and prose cannot
drift apart), and the English assets must carry no Korean.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = REPO_ROOT / "scripts" / "build_prompt_cache_charts.py"
_ASSET_DIR = REPO_ROOT / "docs" / "assets" / "prompt-cache"
_PAGES = {
    "en": REPO_ROOT / "docs" / "en" / "manual" / "prompt-cache-observed.md",
    "ko": REPO_ROOT / "docs" / "ko" / "manual" / "prompt-cache-observed.md",
}

_spec = importlib.util.spec_from_file_location("build_prompt_cache_charts", _MODULE_PATH)
assert _spec and _spec.loader
charts = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = charts
_spec.loader.exec_module(charts)

HANGUL = re.compile(r"[가-힣]")
BUNDLE = json.loads(charts.BUNDLE_PATH.read_text(encoding="utf-8"))
NAMES = [name for name, _ in charts.CHARTS]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("locale", ["en", "ko"])
def test_committed_svg_matches_generator(name: str, locale: str) -> None:
    # The committed asset must equal a fresh render of the tracked bundle, so a
    # chart can always be regenerated and never drifts by hand.
    render = dict(charts.CHARTS)[name]
    committed = (_ASSET_DIR / f"{name}.{locale}.svg").read_text(encoding="utf-8")
    assert committed == render(BUNDLE, locale)


@pytest.mark.parametrize("name", NAMES)
def test_english_chart_has_no_hangul(name: str) -> None:
    text = (_ASSET_DIR / f"{name}.en.svg").read_text(encoding="utf-8")
    assert not HANGUL.search(text), f"{name}.en.svg leaks Korean"


@pytest.mark.parametrize("name", NAMES)
def test_korean_chart_is_korean(name: str) -> None:
    # Guard the premise of the check above: the ko asset really is localised.
    text = (_ASSET_DIR / f"{name}.ko.svg").read_text(encoding="utf-8")
    assert HANGUL.search(text), f"{name}.ko.svg lost its Korean"


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("locale", ["en", "ko"])
def test_charts_are_accessible(name: str, locale: str) -> None:
    text = (_ASSET_DIR / f"{name}.{locale}.svg").read_text(encoding="utf-8")
    assert '<title id="chart-title">' in text
    assert '<desc id="chart-desc">' in text
    assert 'aria-labelledby="chart-title chart-desc"' in text


def test_render_is_deterministic() -> None:
    # Byte-stability is what lets the committed assets be a regression target.
    for name, render in charts.CHARTS:
        for locale in ("en", "ko"):
            assert render(BUNDLE, locale) == render(BUNDLE, locale)


@pytest.mark.parametrize("locale", ["en", "ko"])
def test_repeat_progression_matches_the_published_table(locale: str) -> None:
    # Chart A draws the first table of section 3-5. Every value it renders must
    # appear in the page, so the picture cannot say something the prose does not.
    page = _PAGES[locale].read_text(encoding="utf-8")
    for exp, repeats in BUNDLE["repeat_progression"].items():
        drawn = [f"{charts.pct(repeats[rep]):.2f}" for rep in charts.REPEATS]
        row = "| " + (exp if locale == "en" else exp)
        assert any(
            all(value in line for value in drawn)
            for line in page.splitlines()
            if line.startswith(row)
        ), f"experiment {exp} repeat ratios {drawn} are not in the {locale} page"


@pytest.mark.parametrize("locale", ["en", "ko"])
def test_grok_slice_matches_the_published_prose(locale: str) -> None:
    # Chart B draws the Grok-slice comparison; the same four numbers are stated
    # in the section 3-3 table and its paragraph.
    page = _PAGES[locale].read_text(encoding="utf-8")
    for exp, arms in BUNDLE["grok_slice"].items():
        for arm, part in arms.items():
            value = f"{charts.pct(part):.2f}%"
            assert value in page, f"exp {exp} {arm} {value} is not in the {locale} page"


def test_bundle_carries_no_prompt_or_response_text() -> None:
    # The bundle is a public asset derived from a sealed run; it must hold only
    # aggregates. Anything but ints under the two data blocks is a leak.
    for block in ("repeat_progression", "grok_slice"):
        for group in BUNDLE[block].values():
            for part in group.values():
                assert all(isinstance(v, int) for v in part.values()), block


def test_every_experiment_is_labelled_void_where_it_should_be() -> None:
    # Experiment 11 is VOID and every reader-facing surface must say so.
    for locale in ("en", "ko"):
        for name in NAMES:
            text = (_ASSET_DIR / f"{name}.{locale}.svg").read_text(encoding="utf-8")
            marker = "(VOID)" if locale == "en" else "(무효)"
            assert marker in text, f"{name}.{locale}.svg does not label experiment 11"
