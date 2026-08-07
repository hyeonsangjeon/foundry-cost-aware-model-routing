#!/usr/bin/env python3
"""Post-build i18n site checker (03F scaffold).

Runs against a built MkDocs site directory (``_site`` in the Pages workflow,
``site`` in the CI docs job) and guards the Phase F1 contract:

    Standing up the ``mkdocs-static-i18n`` structure must not move, drop, or
    duplicate any public URL, and must never emit an ``/en/`` or ``/ko/`` path.

Five check categories are wired here. The **URL contract** is a hard gate that
is fully implemented and enforced today. The remaining four (internal links,
anchors, edit links, language alternates, redirects) are wired with working
skeletons that pass on the current single-language build; each carries a
``TODO(flip)`` marking the assertions that harden once translated pages and the
default->en cutover land (F2+/F4).

Usage::

    python scripts/check_i18n_site.py [SITE_DIR]   # default: site

Exits non-zero if any hard check fails.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
KO_DOCS = REPO_ROOT / "docs" / "ko"
EN_DOCS = REPO_ROOT / "docs" / "en"

# Language segments that must never appear as a built URL prefix while the site
# serves the default language (ko) at the root. The default-to-en flip (F4) will
# intentionally introduce /ko/, at which point this list is narrowed.
FORBIDDEN_URL_SEGMENTS = ("en", "ko")


@dataclass
class CheckOutcome:
    name: str
    hard: bool
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


class _LinkCollector(HTMLParser):
    """Collects href/src targets and element ids from an HTML page."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        for key in ("href", "src"):
            if a.get(key):
                self.links.append(a[key])
        if a.get("id"):
            self.ids.add(a["id"])
        if a.get("name") and tag == "a":
            self.ids.add(a["name"])


def _html_files(site: Path) -> list[Path]:
    return sorted(site.rglob("*.html"))


def _expected_root_urls() -> list[str]:
    """Every ko source page mapped to the root URL it must be served at.

    ``docs/ko/manual/install.md`` -> ``manual/install/index.html``;
    ``docs/ko/index.md`` -> ``index.html``. This is the folder-structure
    de-prefixing the plugin performs for the default language.
    """
    urls: list[str] = []
    for md in sorted(KO_DOCS.rglob("*.md")):
        rel = md.relative_to(KO_DOCS)
        if rel.name == "index.md":
            target = rel.parent / "index.html"
        else:
            target = rel.parent / rel.stem / "index.html"
        urls.append(str(target).replace("\\", "/"))
    return urls


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #
def check_url_contract(site: Path) -> CheckOutcome:
    """HARD: no /en/ or /ko/ prefix, and every ko page served at its root URL."""
    out = CheckOutcome("url-contract", hard=True)

    for seg in FORBIDDEN_URL_SEGMENTS:
        leaked = site / seg
        if leaked.is_dir():
            sample = [
                str(p.relative_to(site)) for p in list(leaked.rglob("*"))[:5] if p.is_file()
            ]
            out.failures.append(f"forbidden URL prefix '/{seg}/' present: {sample}")

    for url in _expected_root_urls():
        if not (site / url).is_file():
            out.failures.append(f"expected root URL missing: /{url}")

    out.notes.append(f"{len(_expected_root_urls())} ko pages verified at root URLs")
    return out


def check_internal_links(site: Path) -> CheckOutcome:
    """Relative link targets must resolve to a built file (mkdocs --strict-level)."""
    out = CheckOutcome("internal-links", hard=True)
    checked = 0
    for html in _html_files(site):
        parser = _LinkCollector()
        parser.feed(html.read_text(encoding="utf-8"))
        for raw in parser.links:
            href, _ = urldefrag(raw)
            if not href:
                continue
            parsed = urlparse(href)
            if parsed.scheme or parsed.netloc:  # external / mailto / tel
                continue
            if href.startswith("/"):  # absolute-from-root; skip in skeleton
                continue
            checked += 1
            target = (html.parent / href).resolve()
            if href.endswith("/"):
                target = target / "index.html"
            if not target.exists() and not target.with_suffix(".html").exists():
                out.failures.append(f"{html.relative_to(site)} -> broken '{raw}'")
    out.notes.append(f"{checked} relative links resolved")
    return out


def check_anchors(site: Path) -> CheckOutcome:
    """SOFT skeleton: same-page ``#fragment`` links should hit an existing id."""
    out = CheckOutcome("anchors", hard=False)
    checked = 0
    for html in _html_files(site):
        parser = _LinkCollector()
        parser.feed(html.read_text(encoding="utf-8"))
        for raw in parser.links:
            base, frag = urldefrag(raw)
            if frag and not base:  # purely in-page anchor
                checked += 1
                if frag not in parser.ids:
                    # TODO(flip): promote to a hard failure once translated
                    # pages are audited; some theme anchors are JS-generated.
                    out.notes.append(f"{html.relative_to(site)} #-> '{frag}' (unresolved id)")
    out.notes.append(f"{checked} in-page anchors scanned")
    return out


def check_edit_links(site: Path) -> CheckOutcome:
    """SOFT skeleton: edit links must map to a real source path under docs/.

    No ``content.action.edit`` button is rendered today, so there is nothing to
    verify. TODO(flip): when edit buttons are enabled, assert each target
    resolves under ``docs/ko/`` or ``docs/en/``.
    """
    out = CheckOutcome("edit-links", hard=False)
    edit_targets = 0
    for html in _html_files(site):
        parser = _LinkCollector()
        parser.feed(html.read_text(encoding="utf-8"))
        edit_targets += sum(1 for link in parser.links if "/edit/" in link)
    out.notes.append(f"{edit_targets} edit links rendered (0 expected in F1)")
    return out


def check_language_alternates(site: Path) -> CheckOutcome:
    """SOFT skeleton: hreflang alternates must be consistent.

    F1 builds a single language (ko), so the sitemap carries a ko self-alternate
    only and no /en/ alternate may appear. TODO(flip): assert every page exposes
    both en and ko alternates once both languages build.
    """
    out = CheckOutcome("language-alternates", hard=False)
    sitemap = site / "sitemap.xml"
    if sitemap.is_file():
        text = sitemap.read_text(encoding="utf-8")
        if 'hreflang="en"' in text:
            out.failures.append("sitemap advertises an 'en' alternate while en build is disabled")
        ko_alternates = text.count('hreflang="ko"')
        out.notes.append(f"sitemap ko self-alternates: {ko_alternates}")
    else:
        out.notes.append("no sitemap.xml (skipped)")
    return out


def check_redirects(site: Path) -> CheckOutcome:
    """SOFT skeleton: every declared redirect must materialise as an HTML stub.

    The redirect inventory is empty in F1. TODO(flip): for each redirect_maps
    entry, assert ``site/<from>`` exists and meta-refreshes to ``<to>``.
    """
    out = CheckOutcome("redirects", hard=False)
    redirect_pages = [
        p for p in _html_files(site) if "0; url=" in p.read_text(encoding="utf-8")[:600]
    ]
    out.notes.append(f"{len(redirect_pages)} redirect stubs present (0 expected in F1)")
    return out


CHECKS = (
    check_url_contract,
    check_internal_links,
    check_anchors,
    check_edit_links,
    check_language_alternates,
    check_redirects,
)


def main(argv: list[str]) -> int:
    site = Path(argv[1]) if len(argv) > 1 else REPO_ROOT / "site"
    if not site.is_dir():
        print(f"error: site directory not found: {site}", file=sys.stderr)
        return 2

    print(f"i18n site check: {site}  ({len(_html_files(site))} html pages)\n")
    hard_failed = False
    for check in CHECKS:
        outcome = check(site)
        status = "PASS" if outcome.ok else ("FAIL" if outcome.hard else "WARN")
        tag = "hard" if outcome.hard else "soft"
        print(f"[{status}] {outcome.name} ({tag})")
        for note in outcome.notes:
            print(f"       · {note}")
        for failure in outcome.failures:
            print(f"       ✗ {failure}")
        if outcome.failures and outcome.hard:
            hard_failed = True

    print()
    if hard_failed:
        print("i18n site check FAILED (hard check violated)")
        return 1
    print("i18n site check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
