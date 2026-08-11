#!/usr/bin/env python3
"""Post-build checker for the bilingual mkdocs-static-i18n site (03F Phase F4).

Runs against a freshly built ``_site`` after the production flip: English is the
default locale served at the site root, Korean is served under ``/ko/``. The
checker enforces the §12 CI-acceptance contract that ``mkdocs build --strict``
alone cannot prove — locale pairing, redirects, anchors, language alternates,
locale-scoped search, unintended-Hangul leakage, and both static demos.

Any failure exits non-zero and gates the docs workflow.

Contract enforced (all hard):
  * URL contract — ``index.html`` (en root) and ``ko/index.html`` exist; no
    ``en/`` language directory is emitted.
  * Language attribute — root pages declare ``<html lang="en">``; ``/ko/`` pages
    declare ``<html lang="ko">``.
  * Locale pairing — every public content page has an EN/KO counterpart, except
    the two declared exceptions: ``lab-notebook/devlog`` (Korean-only archive,
    kept in the Korean nav per the operator's decision) and the
    ``lab-notebook/story-arc-en`` redirect stub (English-only, legacy URL).
  * Redirects — every legacy URL in the inventory (``story-arc-en``) resolves to
    its canonical target.
  * Internal links — every local ``<a href>`` resolves inside the site.
  * Anchors — every same-page ``#fragment`` link resolves to a real id.
  * Canonical / hreflang — each content page self-canonicalises (absolute URL
    with the repository project prefix); translated pairs carry reciprocal
    ``hreflang=en``/``hreflang=ko`` alternates that resolve to the counterpart.
  * Sitemap — every ``<loc>`` carries the project prefix; both locales appear.
  * Search behaviour — the combined search index partitions by locale: English
    reader entries live at root URLs, Korean entries under ``ko/``; no Korean
    text leaks into a root (English) search entry and no location is duplicated.
  * Unintended Hangul — no English reader page leaks Korean text in its article
    body (the locale-neutral technical demos are exempt by policy).
  * Static demos — ``demo/`` (en) and ``ko/demo/`` (ko) both render with the
    correct ``<html lang>``, an EN<->KO switch link, a self canonical, and their
    locale-neutral machine JSON payloads.

Divergence from spec §12 (documented, operator-approved): the Korean ``devlog``
archive is intentionally kept as an indexed Korean-only page inside the Korean
nav/search/sitemap (decision "(b)"), rather than a ``noindex`` page absent from
nav/search/sitemap. It has no English counterpart and no English content, so it
cannot leak Hangul into an English page. This checker treats it as a declared
Korean-only exception rather than a hidden archive.

Usage:  python scripts/check_i18n_site.py <site-dir>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
MKDOCS_YML = REPO_ROOT / "mkdocs.yml"

# Content pages that are legitimately single-locale.
KO_ONLY_PAGES = {"lab-notebook/devlog"}          # operator decision (b)
# Redirect stubs (English-only legacy URLs) — verified by check_redirects, and
# excluded from pairing / Hangul / canonical content checks.
REDIRECT_PAGES = {"lab-notebook/story-arc-en"}
REDIRECT_TARGETS = {"lab-notebook/story-arc-en": "lab-notebook/story-arc"}

# Directories that are infrastructure, not reader content pages.
INFRA_TOP = ("assets", "search")
DEMO_PAGES = {"demo", "ko/demo"}

HREF_RE = re.compile(r'href\s*=\s*"([^"]*)"', re.IGNORECASE)
ID_RE = re.compile(r'\b(?:id|name)\s*=\s*"([^"]+)"', re.IGNORECASE)
HTML_LANG_RE = re.compile(r'<html[^>]*\blang\s*=\s*"([^"]+)"', re.IGNORECASE)
CANONICAL_RE = re.compile(
    r'<link[^>]*\brel\s*=\s*"canonical"[^>]*\bhref\s*=\s*"([^"]+)"'
    r'|<link[^>]*\bhref\s*=\s*"([^"]+)"[^>]*\brel\s*=\s*"canonical"',
    re.IGNORECASE,
)
ALTERNATE_RE = re.compile(r'<link[^>]*\brel\s*=\s*"alternate"[^>]*>', re.IGNORECASE)
HREFLANG_ATTR_RE = re.compile(r'\bhreflang\s*=\s*"([^"]+)"', re.IGNORECASE)
HREF_ATTR_RE = re.compile(r'\bhref\s*=\s*"([^"]+)"', re.IGNORECASE)
REFRESH_RE = re.compile(
    r'http-equiv\s*=\s*"refresh"[^>]*content\s*=\s*"[^"]*url=([^"\']+)', re.IGNORECASE
)
ARTICLE_RE = re.compile(r"<article\b[^>]*>(.*?)</article>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
EXTERNAL_PREFIXES = ("http://", "https://", "//", "mailto:", "tel:",
                     "javascript:", "data:")

# -- static-demo language consistency ---------------------------------------
# Reader-prose surfaces of each static demo that must be single-language. The
# other machine JSON payloads (healthz/policy/replay/regression/fanout-sweep/
# compare) and the sealed ``published.json`` snapshot are pure numbers and
# identifiers with no reader prose, so they are language-neutral by construction
# and are not scanned.
DEMO_PROSE_JSON = ("experiments.json", "metrics-history.json")
# The EN<->KO switch affordance legitimately shows the *other* locale's label in
# its own script (``한국어`` on the English demo, ``English`` on the Korean one),
# so the switch anchor is removed before the per-locale language assertions.
DEMO_SWITCH_RE = re.compile(r'<a\b[^>]*\brel\s*=\s*"alternate"[^>]*>.*?</a>',
                            re.IGNORECASE | re.DOTALL)
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>",
                             re.IGNORECASE | re.DOTALL)
HEAD_RE = re.compile(r"<head\b[^>]*>.*?</head>", re.IGNORECASE | re.DOTALL)


def _base_path() -> str:
    """Return the URL base path from mkdocs ``site_url`` (e.g. ``/repo/``)."""
    if not MKDOCS_YML.is_file():
        return "/"
    for line in MKDOCS_YML.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("site_url:"):
            url = stripped.split(":", 1)[1].strip()
            path = urlparse(url).path
            if not path.endswith("/"):
                path = path + "/"
            return path or "/"
    return "/"


def _site_url() -> str:
    if not MKDOCS_YML.is_file():
        return ""
    for line in MKDOCS_YML.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("site_url:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def _page_key(html_path: Path, site: Path) -> str | None:
    """Return the locale-inclusive page key for an ``index.html`` (dir URL),
    e.g. ``manual/install`` or ``ko/manual/install`` or ``""`` for the root.
    Returns None for non-index HTML (404.html, sitemap, etc.)."""
    rel = html_path.relative_to(site).as_posix()
    if rel == "index.html":
        return ""
    if rel.endswith("/index.html"):
        return rel[: -len("/index.html")]
    return None


def _iter_pages(site: Path):
    """Yield (key, html_path) for every directory-URL page, skipping infra."""
    for html_path in sorted(site.rglob("index.html")):
        key = _page_key(html_path, site)
        if key is None:
            continue
        top = key.split("/", 1)[0]
        if top in INFRA_TOP:
            continue
        if key.startswith("ko/") and key.split("/")[1:2] == ["assets"]:
            continue
        yield key, html_path


def _is_redirect(html_path: Path) -> bool:
    return bool(REFRESH_RE.search(html_path.read_text(encoding="utf-8", errors="ignore")))


def _norm(key: str) -> tuple[bool, str]:
    """Normalise a page key to (is_korean, english_relative_key).

    The Korean root is ``ko`` and Korean sub-pages are ``ko/...``; both map onto
    the English-relative key so counterparts compare directly (``ko`` -> ``""``).
    """
    if key == "ko":
        return True, ""
    if key.startswith("ko/"):
        return True, key[len("ko/"):]
    return False, key


def _resolve_link(html_path: Path, site: Path, href: str, base: str) -> Path | None:
    """Resolve a local href to a filesystem path, or None if external."""
    target = href.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return None
    if target.lower().startswith(EXTERNAL_PREFIXES):
        return None
    if target.startswith("/"):
        if base != "/" and target.startswith(base):
            rel = target[len(base):]
        else:
            rel = target.lstrip("/")
        return site / rel
    return html_path.parent / target


def _link_exists(dest: Path) -> bool:
    if dest.is_dir():
        return (dest / "index.html").is_file()
    return dest.exists()


# --------------------------------------------------------------------------- #
# Hard checks
# --------------------------------------------------------------------------- #

def check_url_contract(site: Path) -> list[str]:
    out: list[str] = []
    if not (site / "index.html").is_file():
        out.append("URL contract: missing English root index.html")
    if not (site / "ko" / "index.html").is_file():
        out.append("URL contract: missing Korean ko/index.html")
    en_dir = site / "en"
    if en_dir.is_dir():
        pages = sorted(str(p.relative_to(site)) for p in en_dir.rglob("*.html"))
        if pages:
            out.append("URL contract: found " + str(len(pages))
                       + " page(s) under forbidden /en/ prefix (e.g. "
                       + ", ".join(pages[:5]) + ")")
    return out


def check_lang_attributes(site: Path) -> list[str]:
    out: list[str] = []
    for key, html_path in _iter_pages(site):
        text = html_path.read_text(encoding="utf-8", errors="ignore")
        m = HTML_LANG_RE.search(text)
        if not m:
            out.append("lang: " + (key or "<root>") + " has no <html lang>")
            continue
        lang = m.group(1).lower()
        expected = "ko" if key == "ko" or key.startswith("ko/") else "en"
        if lang != expected:
            out.append("lang: " + (key or "<root>") + " declares lang="
                       + lang + " (expected " + expected + ")")
    return out


def check_locale_pairs(site: Path) -> list[str]:
    """Every content page has an EN/KO counterpart, minus declared exceptions."""
    out: list[str] = []
    en_keys: set[str] = set()
    ko_keys: set[str] = set()
    for key, html_path in _iter_pages(site):
        if key in DEMO_PAGES:
            continue
        is_ko, rel = _norm(key)
        if is_ko:
            ko_keys.add(rel)
        else:
            if _is_redirect(html_path):
                continue
            en_keys.add(rel)

    for key in sorted(en_keys):
        if key in KO_ONLY_PAGES or key in REDIRECT_PAGES:
            continue
        if key not in ko_keys:
            out.append("pair: English page '" + (key or "<root>")
                       + "' has no Korean counterpart under /ko/")
    for key in sorted(ko_keys):
        if key in KO_ONLY_PAGES:
            continue
        if key in REDIRECT_PAGES:
            continue
        if key not in en_keys:
            out.append("pair: Korean page '/ko/" + key
                       + "' has no English counterpart at the site root")
    # The declared Korean-only page must actually be Korean-only.
    for ko_only in KO_ONLY_PAGES:
        if not (site / "ko" / ko_only / "index.html").is_file():
            out.append("pair: declared Korean-only page '" + ko_only
                       + "' is missing under /ko/")
        if (site / ko_only / "index.html").is_file():
            out.append("pair: declared Korean-only page '" + ko_only
                       + "' unexpectedly has an English page at the root")
    return out


def check_redirects(site: Path) -> list[str]:
    out: list[str] = []
    base = _base_path()
    for stub, target in REDIRECT_TARGETS.items():
        path = site / stub / "index.html"
        if not path.is_file():
            out.append("redirect: legacy URL '" + stub + "' is missing")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        m = REFRESH_RE.search(text)
        if not m:
            out.append("redirect: '" + stub + "' has no meta-refresh")
            continue
        dest = m.group(1).strip()
        # Accept absolute (canonical https) or root-relative targets that point
        # at the expected target page.
        want_tail = target.rstrip("/") + "/"
        if want_tail not in dest.rstrip("/") + "/":
            out.append("redirect: '" + stub + "' points to '" + dest
                       + "', expected to contain '" + want_tail + "'")
        # The target page must exist in the built site.
        if not (site / target / "index.html").is_file():
            out.append("redirect: target page '" + target + "' does not exist")
        if base not in dest and not dest.startswith(("http://", "https://")):
            out.append("redirect: '" + stub + "' target '" + dest
                       + "' lacks the project prefix " + base)
    return out


def check_internal_links(site: Path) -> list[str]:
    base = _base_path()
    out: list[str] = []
    for html_path in sorted(site.rglob("*.html")):
        text = html_path.read_text(encoding="utf-8", errors="ignore")
        for href in HREF_RE.findall(text):
            dest = _resolve_link(html_path, site, href, base)
            if dest is None:
                continue
            resolved = dest.resolve()
            try:
                resolved.relative_to(site.resolve())
            except ValueError:
                where = html_path.relative_to(site).as_posix()
                out.append("link: " + where + " -> " + href + " escapes site root")
                continue
            if not _link_exists(dest):
                where = html_path.relative_to(site).as_posix()
                out.append("link: " + where + " -> " + href + " does not resolve")
    return out


def check_anchors(site: Path) -> list[str]:
    out: list[str] = []
    for html_path in sorted(site.rglob("*.html")):
        text = html_path.read_text(encoding="utf-8", errors="ignore")
        ids = set(ID_RE.findall(text))
        for href in HREF_RE.findall(text):
            if not href.startswith("#") or href == "#":
                continue
            if href[1:] not in ids:
                where = html_path.relative_to(site).as_posix()
                out.append("anchor: " + where + " -> " + href + " has no target")
    return out


def _canonical(text: str) -> str | None:
    m = CANONICAL_RE.search(text)
    if not m:
        return None
    return (m.group(1) or m.group(2) or "").strip()


def _alternates(text: str) -> dict[str, str]:
    alts: dict[str, str] = {}
    for tag in ALTERNATE_RE.findall(text):
        lang = HREFLANG_ATTR_RE.search(tag)
        href = HREF_ATTR_RE.search(tag)
        if lang and href:
            alts[lang.group(1).lower()] = href.group(1).strip()
    return alts


def check_canonical_hreflang(site: Path) -> list[str]:
    out: list[str] = []
    base = _base_path()
    site_url = _site_url()
    for key, html_path in _iter_pages(site):
        if key in DEMO_PAGES or key in REDIRECT_PAGES:
            continue
        is_ko, rel = _norm(key)
        if not is_ko and _is_redirect(html_path):
            continue
        text = html_path.read_text(encoding="utf-8", errors="ignore")
        canon = _canonical(text)
        page_url = site_url.rstrip("/") + "/" + (key + "/" if key else "")
        if not canon:
            out.append("canonical: " + (key or "<root>") + " has no canonical link")
        else:
            if base not in canon:
                out.append("canonical: " + (key or "<root>")
                           + " canonical '" + canon + "' lacks project prefix")
            if canon.rstrip("/") != page_url.rstrip("/"):
                out.append("canonical: " + (key or "<root>")
                           + " is not self-canonical (got '" + canon + "')")
        alts = _alternates(text)
        # Korean-only archive: only a ko self-alternate is required; the plugin
        # may emit an en alternate pointing at the site root (accepted).
        if rel in KO_ONLY_PAGES:
            if "ko" not in alts:
                out.append("hreflang: Korean-only '" + key + "' lacks ko alternate")
            continue
        if "en" not in alts or "ko" not in alts:
            out.append("hreflang: " + (key or "<root>")
                       + " missing en/ko alternate(s) (have: "
                       + ",".join(sorted(alts)) + ")")
            continue
        # Reciprocal alternate must resolve to the counterpart page.
        for lang in ("en", "ko"):
            dest = _resolve_link(html_path, site, alts[lang], base)
            if dest is not None and not _link_exists(dest):
                out.append("hreflang: " + (key or "<root>") + " " + lang
                           + " alternate '" + alts[lang] + "' does not resolve")
    return out


def check_sitemap(site: Path) -> list[str]:
    out: list[str] = []
    base = _base_path()
    sm = site / "sitemap.xml"
    if not sm.is_file():
        return ["sitemap: sitemap.xml is missing"]
    text = sm.read_text(encoding="utf-8", errors="ignore")
    locs = re.findall(r"<loc>([^<]+)</loc>", text)
    if not locs:
        return ["sitemap: no <loc> entries"]
    missing_prefix = [u for u in locs if base not in u]
    if missing_prefix:
        out.append("sitemap: " + str(len(missing_prefix))
                   + " URL(s) lack the project prefix (e.g. " + missing_prefix[0] + ")")
    has_root = any(u.rstrip("/").endswith(base.rstrip("/")) for u in locs)
    has_ko = any((base + "ko/") in u or u.rstrip("/").endswith(base.rstrip("/") + "/ko")
                 for u in locs)
    if not has_root:
        out.append("sitemap: no English root URL present")
    if not has_ko:
        out.append("sitemap: no Korean (/ko/) URL present")
    return out


def check_search(site: Path) -> list[str]:
    """Search behaviour: English reader entries at root URLs, Korean under ko/;
    no Korean text leaks into a root entry; no duplicate locations."""
    out: list[str] = []
    index = site / "search" / "search_index.json"
    if not index.is_file():
        return ["search: search/search_index.json is missing"]
    try:
        data = json.loads(index.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ["search: index is not valid JSON (" + str(exc) + ")"]
    docs = data.get("docs", [])
    if not docs:
        return ["search: index has no documents"]
    root_entries = [d for d in docs if not d.get("location", "").startswith("ko/")]
    ko_entries = [d for d in docs if d.get("location", "").startswith("ko/")]
    if not root_entries:
        out.append("search: no English (root) entries")
    if not ko_entries:
        out.append("search: no Korean (ko/) entries")
    leaks = []
    for d in root_entries:
        blob = (d.get("title", "") + " " + d.get("text", ""))
        if len(HANGUL_RE.findall(blob)) > 3:
            leaks.append(d.get("location", "?"))
    if leaks:
        out.append("search: " + str(len(leaks))
                   + " English (root) entry/entries carry Korean text "
                   + "(Korean search would return English URLs) e.g. " + leaks[0])
    locs = [d.get("location", "") for d in docs]
    dups = sorted({loc for loc in locs if locs.count(loc) > 1})
    if dups:
        out.append("search: " + str(len(dups))
                   + " duplicate location(s) (fallback/redirect duplicates) e.g. "
                   + dups[0])
    return out


def check_hangul_leak(site: Path) -> list[str]:
    """No English reader page leaks Korean text in its article body."""
    out: list[str] = []
    for key, html_path in _iter_pages(site):
        if key.startswith("ko/") or key == "ko":
            continue
        if key in DEMO_PAGES or key in REDIRECT_PAGES:
            continue
        if _is_redirect(html_path):
            continue
        text = html_path.read_text(encoding="utf-8", errors="ignore")
        m = ARTICLE_RE.search(text)
        body = m.group(1) if m else text
        body = TAG_RE.sub(" ", body)
        hits = HANGUL_RE.findall(body)
        if hits:
            out.append("hangul: English page '" + (key or "<root>") + "' leaks "
                       + str(len(hits)) + " Korean character(s) in its body")
    return out


def check_demos(site: Path) -> list[str]:
    """Both static demos render with correct lang, switch link, canonical, JSON."""
    out: list[str] = []
    specs = {
        "demo": ("en", "ko", "../ko/demo/"),
        "ko/demo": ("ko", "en", "../../demo/"),
    }
    for key, (lang, _other, switch) in specs.items():
        index = site / key / "index.html"
        if not index.is_file():
            out.append("demo: '" + key + "/' is missing (index.html not built)")
            continue
        text = index.read_text(encoding="utf-8", errors="ignore")
        m = HTML_LANG_RE.search(text)
        if not m or m.group(1).lower() != lang:
            out.append("demo: '" + key + "/' lang is "
                       + (m.group(1) if m else "<none>") + " (expected " + lang + ")")
        if 'rel="alternate"' not in text or switch not in text:
            out.append("demo: '" + key + "/' has no EN<->KO switch link to '"
                       + switch + "'")
        if not _canonical(text):
            out.append("demo: '" + key + "/' has no canonical link")
        if not (site / key / "healthz.json").is_file():
            out.append("demo: '" + key + "/' is missing machine JSON (healthz.json)")
    return out


def _demo_visible_text(html: str) -> str:
    """Reader-visible prose of a demo page: drop ``<head>``, ``<script>``,
    ``<style>``, the EN<->KO switch anchor, then every tag, and collapse
    whitespace. Shared code, identifiers and numbers live in stripped scripts or
    are ASCII, so what remains is the translatable body copy."""
    html = HEAD_RE.sub(" ", html)
    html = DEMO_SWITCH_RE.sub(" ", html)
    html = SCRIPT_STYLE_RE.sub(" ", html)
    html = TAG_RE.sub(" ", html)
    return re.sub(r"\s+", " ", html).strip()


def check_demo_languages(site: Path) -> list[str]:
    """Each static demo must render in exactly one language.

    Three assertions per surface, across both delivery paths (the demo
    ``index.html`` and the runtime-fetched reader-prose JSON):
      * the English demo carries no Korean (the switch label is excluded);
      * the Korean demo actually carries Korean (not English copied into it);
      * the English and Korean demos differ (real per-locale branching, not the
        same body written to both paths).

    Code, identifiers, model names and CLI commands are ASCII, so they never
    trip the Hangul assertions and stay shared across locales by design. This is
    the check the earlier structural ``check_demos`` could not make: it verified
    markers (lang attr, switch link, canonical, JSON presence) but never the
    body language, so a locale-neutral body passed silently.
    """
    out: list[str] = []
    en_dir, ko_dir = site / "demo", site / "ko" / "demo"
    en_index, ko_index = en_dir / "index.html", ko_dir / "index.html"
    if not en_index.is_file() or not ko_index.is_file():
        # check_demos already reports a missing demo; nothing more to assert.
        return out

    en_html = en_index.read_text(encoding="utf-8", errors="ignore")
    ko_html = ko_index.read_text(encoding="utf-8", errors="ignore")

    # (1) English demo index.html carries no Korean (switch label excluded).
    en_hits = HANGUL_RE.findall(DEMO_SWITCH_RE.sub(" ", en_html))
    if en_hits:
        out.append("demo-lang: English demo 'demo/index.html' leaks "
                   + str(len(en_hits)) + " Korean character(s) in its body")

    # (2) Korean demo index.html actually carries Korean.
    if not HANGUL_RE.search(DEMO_SWITCH_RE.sub(" ", ko_html)):
        out.append("demo-lang: Korean demo 'ko/demo/index.html' has no Korean "
                   "text (English copied into the Korean locale?)")

    # (3) The two demo bodies must differ — identical visible prose means the
    #     locale branch never ran (the same screen was served to both paths).
    if _demo_visible_text(en_html) == _demo_visible_text(ko_html):
        out.append("demo-lang: 'demo/' and 'ko/demo/' render identical body "
                   "text (locale branching absent — same screen)")

    # (4) Runtime-fetched reader-prose JSON obeys the same contract.
    for name in DEMO_PROSE_JSON:
        en_json, ko_json = en_dir / name, ko_dir / name
        if not en_json.is_file() or not ko_json.is_file():
            out.append("demo-lang: reader JSON '" + name + "' missing in a demo")
            continue
        en_txt = en_json.read_text(encoding="utf-8", errors="ignore")
        ko_txt = ko_json.read_text(encoding="utf-8", errors="ignore")
        en_j = HANGUL_RE.findall(en_txt)
        if en_j:
            out.append("demo-lang: English demo '" + name + "' leaks "
                       + str(len(en_j)) + " Korean character(s)")
        if not HANGUL_RE.search(ko_txt):
            out.append("demo-lang: Korean demo '" + name + "' has no Korean text")
        if en_txt == ko_txt:
            out.append("demo-lang: '" + name + "' is identical across locales "
                       "(reader prose not branched)")
    return out


CHECKS = [
    ("url-contract", check_url_contract),
    ("lang", check_lang_attributes),
    ("locale-pairs", check_locale_pairs),
    ("redirects", check_redirects),
    ("internal-links", check_internal_links),
    ("anchors", check_anchors),
    ("canonical/hreflang", check_canonical_hreflang),
    ("sitemap", check_sitemap),
    ("search", check_search),
    ("hangul-leak", check_hangul_leak),
    ("demos", check_demos),
    ("demo-languages", check_demo_languages),
]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_i18n_site.py <site-dir>", file=sys.stderr)
        return 2
    site = Path(argv[1])
    if not site.is_dir():
        print("check_i18n_site: site dir not found: " + str(site), file=sys.stderr)
        return 2

    all_failures: list[str] = []
    summary: list[str] = []
    for name, fn in CHECKS:
        failures = fn(site)
        all_failures += failures
        status = "OK" if not failures else (str(len(failures)) + " FAIL")
        summary.append("  [" + status + "] " + name)

    if all_failures:
        print("i18n site check (post-flip): " + str(len(all_failures))
              + " failure(s):\n")
        for line in all_failures:
            print("  - " + line)
        print("\nper-check:")
        for line in summary:
            print(line)
        return 1

    print("i18n site check (post-flip): OK")
    for line in summary:
        print(line)
    print("  note: 'lab-notebook/devlog' is an operator-approved Korean-only "
          "page (decision b); it is indexed in the Korean nav/search/sitemap and "
          "has no English counterpart by design.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
