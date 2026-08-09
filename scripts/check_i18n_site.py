#!/usr/bin/env python3
"""Post-build checker for the mkdocs-static-i18n site (03F Phase F1).

Runs against a freshly built site directory and enforces the URL contract the
i18n scaffold promises today, then reports "soft" checks that only become
meaningful once English translations land and the default language flips (F4).

Hard checks (any failure exits non-zero — these gate CI):
  * URL contract — no ``/en/`` or ``/ko/`` language-prefixed pages exist. The
    Korean default renders at the site root; English is ``build: false`` so it
    must emit no output at all.
  * Language coverage — every ``docs/ko/**/*.md`` source page has a built HTML
    page at its expected ROOT url (no language prefix).
  * Internal links — every local ``<a href>`` in the built HTML resolves to a
    file or directory that exists inside the site.

Soft checks (reported, never fail — TODO(flip) skeletons filled in at F4):
  * anchors — in-page ``#fragment`` link targets exist on their own page.
  * edit-links — the theme "edit this page" URL points at the real source path
    (no edit affordance is rendered today, so this is informational).
  * language-alternates — hreflang alternates are emitted per page (cross-
    language en<->ko validation only matters once en builds).
  * redirects — the redirect map is populated (empty until pages move at flip).

Usage:  python scripts/check_i18n_site.py <site-dir>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_KO = REPO_ROOT / "docs" / "ko"
MKDOCS_YML = REPO_ROOT / "mkdocs.yml"


def _base_path() -> str:
    """Return the URL base path from mkdocs ``site_url`` (e.g. ``/repo/``).

    The 404 page and any other site-absolute links are emitted with this prefix,
    which maps to the site root on disk. Stripping it lets absolute links resolve
    against the built tree. Falls back to ``/`` if site_url is absent.
    """
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

# Language folders that must NOT appear as a top-level URL segment in the built
# site while ko is the root default and en is build:false.
FORBIDDEN_LANG_SEGMENTS = ("en", "ko")

HREF_RE = re.compile(r'href\s*=\s*"([^"]*)"', re.IGNORECASE)
ID_RE = re.compile(r'\b(?:id|name)\s*=\s*"([^"]+)"', re.IGNORECASE)
HREFLANG_RE = re.compile(r'hreflang\s*=\s*"([^"]+)"', re.IGNORECASE)

EXTERNAL_PREFIXES = ("http://", "https://", "//", "mailto:", "tel:",
                     "javascript:", "data:")


def _expected_output(rel_md: Path) -> str:
    """Map a docs/ko-relative markdown path to its directory-URL output path.

    ``index.md`` -> ``index.html``; ``x.md`` -> ``x/index.html``;
    ``dir/index.md`` -> ``dir/index.html``. Mirrors mkdocs use_directory_urls.
    """
    parts = list(rel_md.parent.parts)
    if rel_md.stem == "index":
        parts.append("index.html")
    else:
        parts.extend([rel_md.stem, "index.html"])
    return "/".join(parts)


def check_no_language_prefix(site: Path) -> list[str]:
    """Hard — no built page lives under a top-level ``en/`` or ``ko/`` folder."""
    failures: list[str] = []
    for segment in FORBIDDEN_LANG_SEGMENTS:
        candidate = site / segment
        if candidate.is_dir():
            html = sorted(str(p.relative_to(site)) for p in candidate.rglob("*.html"))
            if html:
                sample = ", ".join(html[:5])
                failures.append(
                    "URL contract: found "
                    + str(len(html))
                    + " page(s) under forbidden /"
                    + segment
                    + "/ prefix (e.g. "
                    + sample
                    + ")"
                )
    return failures


def check_ko_pages_at_root(site: Path) -> list[str]:
    """Hard — every ko source page has a built HTML at its root URL."""
    failures: list[str] = []
    sources = sorted(DOCS_KO.rglob("*.md")) if DOCS_KO.is_dir() else []
    if not sources:
        return ["language coverage: no source pages found under docs/ko/"]
    for md in sources:
        rel = md.relative_to(DOCS_KO)
        out = _expected_output(rel)
        if not (site / out).is_file():
            failures.append(
                "language coverage: docs/ko/"
                + rel.as_posix()
                + " has no built page at /"
                + out
            )
    return failures


def _resolve_link(html_path: Path, site: Path, href: str, base: str) -> Path | None:
    """Resolve a local href to a filesystem path, or None if it is external."""
    target = href.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return None
    lowered = target.lower()
    if lowered.startswith(EXTERNAL_PREFIXES):
        return None
    if target.startswith("/"):
        # Site-absolute: strip the site_url base path, then resolve at root.
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


def check_internal_links(site: Path) -> list[str]:
    """Hard — every local <a href> resolves to a real file or page directory."""
    base = _base_path()
    failures: list[str] = []
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
                # Points outside the built site tree — treat as broken.
                where = html_path.relative_to(site).as_posix()
                failures.append("internal link: " + where + " -> " + href
                                + " escapes the site root")
                continue
            if not _link_exists(dest):
                where = html_path.relative_to(site).as_posix()
                failures.append("internal link: " + where + " -> " + href
                                + " does not resolve")
    return failures


def soft_anchors(site: Path) -> tuple[int, int]:
    """Soft — same-page #fragment targets exist. Returns (checked, missing)."""
    checked = 0
    missing = 0
    for html_path in sorted(site.rglob("*.html")):
        text = html_path.read_text(encoding="utf-8", errors="ignore")
        ids = set(ID_RE.findall(text))
        for href in HREF_RE.findall(text):
            if not href.startswith("#") or href == "#":
                continue
            checked += 1
            if href[1:] not in ids:
                missing += 1
    return checked, missing


def soft_language_alternates(site: Path) -> tuple[int, int]:
    """Soft — count pages that emit an hreflang alternate. (checked, without)."""
    checked = 0
    without = 0
    for html_path in sorted(site.rglob("*.html")):
        checked += 1
        text = html_path.read_text(encoding="utf-8", errors="ignore")
        if not HREFLANG_RE.search(text):
            without += 1
    return checked, without


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_i18n_site.py <site-dir>", file=sys.stderr)
        return 2
    site = Path(argv[1])
    if not site.is_dir():
        print("check_i18n_site: site dir not found: " + str(site), file=sys.stderr)
        return 2

    hard_failures: list[str] = []
    hard_failures += check_no_language_prefix(site)
    hard_failures += check_ko_pages_at_root(site)
    hard_failures += check_internal_links(site)

    ko_pages = sum(1 for _ in DOCS_KO.rglob("*.md")) if DOCS_KO.is_dir() else 0

    if hard_failures:
        print("i18n site check: " + str(len(hard_failures)) + " hard failure(s):")
        print("")
        for line in hard_failures:
            print("  - " + line)
        return 1

    # Soft checks — reported for visibility, never fail the build (F1 scope).
    anchors_checked, anchors_missing = soft_anchors(site)
    alt_checked, alt_without = soft_language_alternates(site)

    print("i18n site check: OK")
    print("  hard: no /en//ko/ prefix, " + str(ko_pages)
          + " ko pages at root URL, internal links resolve")
    print("  soft [anchors]: " + str(anchors_checked)
          + " same-page fragment link(s), " + str(anchors_missing) + " missing")
    print("  soft [language-alternates]: " + str(alt_checked) + " page(s), "
          + str(alt_without) + " without an hreflang tag")
    # TODO(flip): the two checks below only carry signal once docs/en is
    # populated and the default language flips (03F Phase F4).
    print("  soft [edit-links]: TODO(flip) — no edit affordance rendered yet; "
          "verify edit_uri resolves per language at flip")
    print("  soft [redirects]: TODO(flip) — redirect_maps empty until pages "
          "move at the URL cutover")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
