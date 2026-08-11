"""Unit tests for :mod:`scripts.localize_root_404`.

mkdocs-static-i18n rebuilds each language and mkdocs core rewrites the root
``404.html`` every time, so the last language (ko) clobbers the English 404.
The post-build script reconstructs an English 404 from the English home page.
These tests lock the language-purity and internal-consistency invariants the
operator required: the 404 is English, does not self-canonicalize, and has no
dangling in-page anchors (skip link / TOC) after the body swap.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = REPO_ROOT / "scripts" / "localize_root_404.py"

_spec = importlib.util.spec_from_file_location("localize_root_404", _MODULE_PATH)
assert _spec and _spec.loader
r404 = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = r404
_spec.loader.exec_module(r404)

HANGUL = re.compile(r"[\uac00-\ud7a3]")
ID_RE = re.compile(r'\bid="([^"]+)"')
HREF_RE = re.compile(r'href="(#[^"]*)"')

# A compact stand-in for the built English home page: correct lang, an
# English title/canonical, a skip link + secondary TOC pointing at home
# headings, the ko language-switcher endonym, and the md-content article.
HOME_HTML = """<!doctype html>
<html lang="en">
<head>
<title>Home - Foundry cost-aware model routing</title>
<link rel="canonical" href="https://example.github.io/foundry-cost-aware-model-routing/">
</head>
<body>
<a href="#foundry-cost-aware-model-routing" class="md-skip">Skip to content</a>
<nav class="md-nav md-nav--primary">
  <a href="/foundry-cost-aware-model-routing/manual/">Manual</a>
</nav>
<div class="md-sidebar md-sidebar--secondary">
  <nav class="md-nav md-nav--secondary" data-md-component="toc">
    <ul class="md-nav__list" data-md-component="toc">
      <li><a href="#check-it" class="md-nav__link">Check it</a>
        <nav class="md-nav"><ul><li><a href="#sub" class="md-nav__link">Sub</a></li></ul></nav>
      </li>
    </ul>
  </nav>
</div>
<a class="md-select__link" hreflang="ko">\ud55c\uad6d\uc5b4</a>
<main>
  <article class="md-content__inner md-typeset">
    <h1 id="foundry-cost-aware-model-routing">Home</h1>
    <h2 id="check-it">Check it</h2>
    <p>Body.</p>
  </article>
</main>
</body></html>"""


def _dangling(html: str) -> list[str]:
    ids = set(ID_RE.findall(html))
    return [h for h in HREF_RE.findall(html) if h != "#" and h[1:] not in ids]


def test_output_is_english_and_titled() -> None:
    out = r404.build_404(HOME_HTML)
    assert '<html lang="en">' in out
    assert "<title>404 - Not found - Foundry cost-aware model routing</title>" in out
    assert "404 - Page not found" in out


def test_no_self_canonical() -> None:
    assert 'rel="canonical"' not in r404.build_404(HOME_HTML)


def test_no_dangling_in_page_anchors() -> None:
    out = r404.build_404(HOME_HTML)
    # Body headings removed -> TOC removed and skip link retargeted.
    assert r404.SECONDARY_NAV_MARKER not in out
    assert 'id="not-found-404"' in out
    assert 'href="#not-found-404"' in out
    assert _dangling(out) == []


def test_home_link_uses_project_base() -> None:
    out = r404.build_404(HOME_HTML)
    assert 'href="/foundry-cost-aware-model-routing/"' in out


def test_switcher_endonym_preserved() -> None:
    # The ko language switcher is a sanctioned (b) exception, not a leak.
    assert "\ud55c\uad6d\uc5b4" in r404.build_404(HOME_HTML)


def test_only_endonym_hangul_remains() -> None:
    out = r404.build_404(HOME_HTML)
    # The single endonym is 3 syllables; nothing else Korean should survive.
    assert len(HANGUL.findall(out)) == 3


def test_nested_secondary_nav_fully_removed() -> None:
    # The TOC contains a nested <nav>; balanced removal must drop the subtree.
    out = r404.build_404(HOME_HTML)
    assert "#sub" not in out and "#check-it" not in out


def test_missing_article_raises() -> None:
    with pytest.raises(SystemExit):
        r404.build_404("<html lang='en'><head><title>x</title></head><body></body></html>")
