#!/usr/bin/env python3
"""Re-localize the site-root ``404.html`` to the default (English) locale.

mkdocs-static-i18n (v1.3.x) builds each language by re-running the full mkdocs
build inside its ``on_post_build`` hook. mkdocs core always writes ``404.html``
to the *site root* (a 404 has to live at the root to be served for any missing
path), so the last language built — Korean — overwrites the English 404 that the
default build produced. The published English site therefore serves a fully
Korean 404 shell (Korean ``<title>``, nav, search and footer) at its root.

There is no config knob for this in v1.3.x, so we repair it as an explicit
post-build step (mirroring ``build_static_site.py`` / ``check_i18n_site.py``):
reconstruct the English 404 from the already-built English home page — which
carries the correct ``lang="en"``, English chrome and absolute asset paths — and
swap its article body for an English "page not found" notice. The Korean 404
under any ``/ko/`` path is unaffected (mkdocs does not emit one there; the root
404 is the single not-found document).

Usage: ``python scripts/localize_root_404.py <site-dir>``
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

CANONICAL_RE = re.compile(r'<link[^>]*\brel="canonical"[^>]*>', re.IGNORECASE)
CANONICAL_HREF_RE = re.compile(
    r'<link[^>]*\brel="canonical"[^>]*\bhref="([^"]+)"', re.IGNORECASE
)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
ARTICLE_RE = re.compile(
    r'(<article\b[^>]*\bmd-content__inner\b[^>]*>).*?(</article>)',
    re.IGNORECASE | re.DOTALL,
)
# The per-page "on this page" table of contents links to the home page's own
# headings; once we swap the article body those targets are gone. The TOC lives
# in the secondary nav (right sidebar plus its mobile copy), so remove every
# ``md-nav--secondary`` element (nesting-safe, see ``_remove_balanced``). A 404
# has no on-page sections, so nothing of value is lost.
SECONDARY_NAV_MARKER = "md-nav--secondary"
# The theme's "skip to content" link targets the first home heading, which we
# also remove; retarget it to the id we give the 404 heading below.
CONTENT_ID = "not-found-404"
SKIP_HREF_RE = re.compile(r'href="#[^"]*"(\s+class="md-skip")', re.IGNORECASE)


def _remove_balanced(html: str, tag: str, attr_substr: str) -> str:
    """Remove every ``<tag ...attr_substr...> ... </tag>`` element, honoring
    nested same-tag elements so we drop the whole subtree, not just to the first
    close tag."""
    open_re = re.compile(r"<" + tag + r"\b[^>]*>", re.IGNORECASE)
    pair_re = re.compile(r"<(/?)" + tag + r"\b[^>]*>", re.IGNORECASE)
    out: list[str] = []
    i = 0
    while True:
        m = open_re.search(html, i)
        if not m:
            out.append(html[i:])
            break
        if attr_substr not in m.group(0):
            out.append(html[i : m.end()])
            i = m.end()
            continue
        out.append(html[i : m.start()])
        depth = 1
        j = m.end()
        while depth > 0:
            mm = pair_re.search(html, j)
            if not mm:  # unbalanced markup: stop consuming, keep the remainder
                j = len(html)
                break
            depth += -1 if mm.group(1) == "/" else 1
            j = mm.end()
        i = j
    return "".join(out)


def _base_path(home_html: str) -> str:
    """Root URL path (e.g. ``/repo/``) taken from the home page canonical link."""
    m = CANONICAL_HREF_RE.search(home_html)
    if not m:
        return "/"
    path = urlparse(m.group(1)).path or "/"
    return path if path.endswith("/") else path + "/"


def build_404(home_html: str) -> str:
    """Return an English 404 document derived from the English home page."""
    base = _base_path(home_html)

    title_m = TITLE_RE.search(home_html)
    site_name = ""
    if title_m:
        # "Home - <site name>" -> "<site name>"; fall back to the whole title.
        parts = title_m.group(1).strip().split(" - ")
        site_name = parts[-1].strip() if len(parts) > 1 else title_m.group(1).strip()
    new_title = "404 - Not found" + (f" - {site_name}" if site_name else "")

    html = TITLE_RE.sub("<title>" + new_title + "</title>", home_html, count=1)
    # A 404 must not self-canonicalize to the home page.
    html = CANONICAL_RE.sub("", html, count=1)

    body = (
        f'\n<h1 id="{CONTENT_ID}">404 - Page not found</h1>\n'
        "<p>We could not find that page. It may have moved, or the link may be "
        "incomplete.</p>\n"
        f'<p><a href="{base}">Go to the home page</a>, or use the search box '
        "above.</p>\n"
    )
    html, n = ARTICLE_RE.subn(r"\1" + body + r"\2", html, count=1)
    if n != 1:
        raise SystemExit(
            "localize_root_404: could not find the md-content article in the "
            "home page; the theme markup may have changed"
        )
    # Drop the on-page TOC (its links target the removed home headings) and
    # retarget the skip link to the 404 heading, so no in-page anchor dangles.
    html = _remove_balanced(html, "nav", SECONDARY_NAV_MARKER)
    html = SKIP_HREF_RE.sub(r'href="#' + CONTENT_ID + r'"\1', html, count=1)
    return html


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: localize_root_404.py <site-dir>", file=sys.stderr)
        return 2
    site = Path(argv[1])
    home = site / "index.html"
    root_404 = site / "404.html"
    if not home.is_file():
        print(f"localize_root_404: home page not found: {home}", file=sys.stderr)
        return 2
    root_404.write_text(build_404(home.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"localized {root_404} to English (default locale)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
