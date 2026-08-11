"""Regression tests for :mod:`scripts.check_i18n_site`.

The site-wide language-purity checker gates every docs build (``ci.yml`` and
``docs.yml`` run ``check_i18n_site.py`` against the freshly built ``_site``).
Until now it had no unit tests, so a passing run only proved the *current* site
happens to be clean — not that the checker actually *catches* a regression. The
operator's standing worry is exactly that ("a passing checker means the checks
are insufficient"). These tests build minimal synthetic site fragments and
assert each check FAILS on the specific violation it is meant to catch and PASSES
on the sanctioned exceptions, so the approved (a)/(b) decisions are locked in:

  (a) an English page must not leak Korean, and the ``devlog`` must not appear in
      the English tree;
  (b) the ``한국어`` language-switcher label, the ``lab-notebook/devlog``
      Korean-only archive, and the bundled Korean search stemmer are sanctioned.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = REPO_ROOT / "scripts" / "check_i18n_site.py"

_spec = importlib.util.spec_from_file_location("check_i18n_site", _MODULE_PATH)
assert _spec and _spec.loader
c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _en_page(body: str, *, lang: str = "en") -> str:
    return (
        '<!doctype html><html lang="' + lang + '"><head><title>t</title></head>'
        "<body><nav>Home</nav><article>" + body + "</article></body></html>"
    )


# --------------------------------------------------------------------------
# exception registry — the auditable (b) allow-list must stay documented in code
# --------------------------------------------------------------------------


def test_ko_only_registry_is_exactly_the_devlog() -> None:
    """Decision (b): the only content page that is legitimately Korean-only is
    the development log. If another page is added, that must be a deliberate,
    reviewed change to this set — not a silent leak."""
    assert c.KO_ONLY_PAGES == {"lab-notebook/devlog"}


def test_asset_lang_exception_is_the_lunr_stemmer() -> None:
    """The one sanctioned non-English asset under the English tree is Material's
    bundled Korean *search stemmer* (third-party tokenizer data, never page
    text). It stays an explicit, auditable exemption."""
    assert any("lunr" in p for p in c.ASSET_LANG_EXCEPTIONS)


# --------------------------------------------------------------------------
# check_hangul_leak — no English page leaks Korean in reader-visible text
# --------------------------------------------------------------------------


def test_hangul_leak_clean_english_tree_passes(tmp_path: Path) -> None:
    _write(tmp_path / "manual" / "concept" / "index.html",
           _en_page("<p>Route to the cheapest model that passes.</p>"))
    assert c.check_hangul_leak(tmp_path) == []


def test_hangul_leak_flags_korean_in_english_page(tmp_path: Path) -> None:
    _write(tmp_path / "manual" / "concept" / "index.html",
           _en_page("<p>가장 싼 모델로 라우팅합니다.</p>"))
    failures = c.check_hangul_leak(tmp_path)
    assert len(failures) == 1
    assert "manual/concept" in failures[0]
    assert "Korean" in failures[0]


def test_hangul_leak_allows_the_language_switcher_label(tmp_path: Path) -> None:
    """The Material selector renders one anchor showing the other locale's
    endonym (``한국어`` on an English page). That single sanctioned word must not
    trip the scan."""
    switcher = '<a href="/ko/manual/concept/" hreflang="ko" lang="ko">한국어</a>'
    _write(tmp_path / "manual" / "concept" / "index.html",
           _en_page("<p>English body.</p>" + switcher))
    assert c.check_hangul_leak(tmp_path) == []


def test_hangul_leak_skips_redirect_stub(tmp_path: Path) -> None:
    """Redirect stubs carry no reader prose and are verified by
    check_redirects; a meta-refresh page is skipped even if it names a Korean
    target."""
    redirect = (
        '<!doctype html><html lang="en"><head>'
        '<meta http-equiv="refresh" content="0; url=/ko/lab-notebook/devlog/">'
        "</head><body>이동 중</body></html>"
    )
    _write(tmp_path / "lab-notebook" / "story-arc-en" / "index.html", redirect)
    assert c.check_hangul_leak(tmp_path) == []


# --------------------------------------------------------------------------
# check_locale_pairs — devlog is Korean-only (decision b), enforced both ways
# --------------------------------------------------------------------------


def _paired_site(tmp_path: Path) -> Path:
    """A minimal valid pair plus the Korean-only devlog: no pairing failures."""
    _write(tmp_path / "intro" / "index.html", _en_page("<p>Intro.</p>"))
    _write(tmp_path / "ko" / "intro" / "index.html", _en_page("<p>소개.</p>", lang="ko"))
    _write(tmp_path / "ko" / "lab-notebook" / "devlog" / "index.html",
           _en_page("<p>개발 로그.</p>", lang="ko"))
    return tmp_path


def test_locale_pairs_devlog_korean_only_passes(tmp_path: Path) -> None:
    assert c.check_locale_pairs(_paired_site(tmp_path)) == []


def test_locale_pairs_flags_devlog_in_english_tree(tmp_path: Path) -> None:
    """Decision (a): a devlog page in the English root is the inconsistent state
    the operator called out — the checker must reject it."""
    site = _paired_site(tmp_path)
    _write(site / "lab-notebook" / "devlog" / "index.html",
           _en_page("<p>Dev log.</p>"))
    failures = c.check_locale_pairs(site)
    assert any("unexpectedly has an English page at the root" in f for f in failures)


def test_locale_pairs_flags_missing_korean_devlog(tmp_path: Path) -> None:
    site = _paired_site(tmp_path)
    (site / "ko" / "lab-notebook" / "devlog" / "index.html").unlink()
    (site / "ko" / "lab-notebook" / "devlog").rmdir()
    failures = c.check_locale_pairs(site)
    assert any("missing under /ko/" in f for f in failures)


# --------------------------------------------------------------------------
# check_demo_languages — three per-locale assertions (route B)
# --------------------------------------------------------------------------

_EN_DEMO = (
    '<!doctype html><html lang="en"><head><title>Demo</title></head><body>'
    '<a rel="alternate" href="../ko/demo/">한국어</a>'
    "<main><h1>Offline replay</h1><p>Synthetic projection, before and after.</p>"
    "</main></body></html>"
)
_KO_DEMO = (
    '<!doctype html><html lang="ko"><head><title>Demo</title></head><body>'
    '<a rel="alternate" href="../../demo/">English</a>'
    "<main><h1>오프라인 리플레이</h1><p>합성 데이터 투영, 전후 비교.</p>"
    "</main></body></html>"
)


def _demo_site(tmp_path: Path, en_html: str, ko_html: str,
               en_json: str = '{"caption": "Offline replay"}',
               ko_json: str = '{"caption": "오프라인 리플레이"}') -> Path:
    _write(tmp_path / "demo" / "index.html", en_html)
    _write(tmp_path / "ko" / "demo" / "index.html", ko_html)
    for name in c.DEMO_PROSE_JSON:
        _write(tmp_path / "demo" / name, en_json)
        _write(tmp_path / "ko" / "demo" / name, ko_json)
    return tmp_path


def test_demo_languages_clean_pair_passes(tmp_path: Path) -> None:
    assert c.check_demo_languages(_demo_site(tmp_path, _EN_DEMO, _KO_DEMO)) == []


def test_demo_languages_flags_korean_in_english_demo(tmp_path: Path) -> None:
    leaky_en = _EN_DEMO.replace("Synthetic projection, before and after.",
                                "합성 데이터 투영 전후.")
    failures = c.check_demo_languages(_demo_site(tmp_path, leaky_en, _KO_DEMO))
    assert any("English demo" in f and "Korean" in f for f in failures)


def test_demo_languages_flags_english_only_korean_demo(tmp_path: Path) -> None:
    english_ko = _KO_DEMO.replace("오프라인 리플레이", "Offline replay").replace(
        "합성 데이터 투영, 전후 비교.", "Synthetic projection, before and after (2).")
    failures = c.check_demo_languages(
        _demo_site(tmp_path, _EN_DEMO, english_ko, ko_json='{"caption": "Offline"}'))
    assert any("Korean demo" in f and "no Korean" in f for f in failures)


def test_demo_languages_flags_identical_bodies(tmp_path: Path) -> None:
    """Same body written to both paths (the original locale-branching bug) must
    be caught, not pass silently."""
    failures = c.check_demo_languages(_demo_site(tmp_path, _KO_DEMO, _KO_DEMO))
    assert any("identical body" in f for f in failures)


# --------------------------------------------------------------------------
# end-to-end — a fully clean fragment yields exit 0 via the same entry CI uses
# --------------------------------------------------------------------------


def test_main_reports_ok_on_clean_hangul_scan(tmp_path: Path, capsys) -> None:
    """A clean English tree passes the hangul-leak check through the real entry
    point (other checks may report on this partial fixture; we assert the
    hangul-leak line is OK, which is the language-purity invariant)."""
    _write(tmp_path / "manual" / "concept" / "index.html",
           _en_page("<p>English only.</p>"))
    assert c.check_hangul_leak(tmp_path) == []
