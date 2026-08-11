"""Render the offline dashboard as a static, deployable site.

The live service serves the dashboard plus ``/healthz``, ``/policy`` and
``/replay`` JSON. For static hosting (e.g. GitHub Pages under a project
sub-path, or a password-gated Vercel deployment) we pre-render those payloads
to flat files and inject an endpoint map so the exact same dashboard HTML/JS
fetches the files instead of live routes.

The injected endpoints are **relative** (``healthz.json`` — no leading slash),
so the export works no matter where it is mounted: the site root, a Vercel
deployment, or ``…/foundry-cost-aware-model-routing/demo/`` on project Pages.

Everything is generated deterministically from the bundled synthetic workload —
no network, no secrets, generic placeholder models only. Numbers are identical
to ``make replay`` / the live service by construction (same pipeline call).

Each locale renders in its own language. ``render_dashboard(locale)`` resolves
the per-locale prose from ``router.demo_i18n`` and injects the matching
measured-tab payload, and the experiment/metrics JSON is localized per locale,
so ``/demo/`` (en) is fully English and ``/ko/demo/`` (ko) fully Korean. The
``<html lang>``, reciprocal ``canonical``/``hreflang`` metadata, and a visible
EN<->KO switch link differ too, so a Korean reader who follows the demo link
from ``/ko/`` stays inside the Korean locale context.

Usage: python scripts/build_static_site.py [output_dir] [locale]
       (defaults: cost-router-dashboard en)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from router.dashboard import render_dashboard  # noqa: E402
from router.demo_i18n import localize_experiments  # noqa: E402
from router.server import RouterService  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
# Masked sealed 03D snapshot — aggregates only (no prompts/responses/endpoints/
# tenant ids). The Measured-run demo tab renders it read-only. Copied verbatim.
_MEASURED_BUNDLE = _REPO_ROOT / "docs" / "assets" / "03d" / "published.json"

# Canonical project Pages base (keeps the repository project prefix, matching
# ``site_url`` in mkdocs.yml). The two demos live at these stable URLs.
_SITE_URL = "https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/"
_DEMO_URLS = {"en": _SITE_URL + "demo/", "ko": _SITE_URL + "ko/demo/"}
# Relative EN<->KO switch target from each demo directory (trailing slash = dir).
_SWITCH = {
    "en": ("../ko/demo/", "ko", "\ud55c\uad6d\uc5b4"),   # -> /ko/demo/, label 한국어
    "ko": ("../../demo/", "en", "English"),               # -> /demo/
}

_ENDPOINT_INJECTION = """<script>
window.__ENDPOINTS__ = {
  health: "healthz.json",
  policy: "policy.json",
  replay: function (synth) { return synth ? "replay-synth.json" : "replay-curated.json"; },
  regression: "regression.json",
  fanoutSweep: "fanout-sweep.json",
  compare: "compare.json",
  experiments: "experiments.json",
  metricsHistory: "metrics-history.json",
  measured: "published.json"
};
</script>
"""


def _payload(service: RouterService, path: str) -> object:
    response = service.dispatch("GET", path)
    if response.status != 200:
        raise SystemExit(f"unexpected status {response.status} for {path}")
    return response.payload


def _localize(html: str, locale: str) -> str:
    """Return the dashboard HTML with locale-correct ``lang``, reciprocal
    ``canonical``/``hreflang`` metadata, and a visible EN<->KO switch link.

    The dashboard body stays English (a locale-neutral technical cockpit); only
    the language attribute, alternate metadata, and switch affordance change.
    """
    if locale not in _DEMO_URLS:
        raise SystemExit(f"unknown demo locale {locale!r} (expected en or ko)")

    html = html.replace('<html lang="en">', f'<html lang="{locale}">', 1)

    meta = (
        f'<script>window.__LOCALE__ = "{locale}";</script>\n'
        f'<link rel="canonical" href="{_DEMO_URLS[locale]}" />\n'
        f'<link rel="alternate" hreflang="en" href="{_DEMO_URLS["en"]}" />\n'
        f'<link rel="alternate" hreflang="ko" href="{_DEMO_URLS["ko"]}" />\n'
        f'<link rel="alternate" hreflang="x-default" href="{_DEMO_URLS["en"]}" />\n'
    )
    if "<head>" not in html:
        raise SystemExit("dashboard HTML has no <head> to inject alternates into")
    html = html.replace("<head>", "<head>\n" + meta, 1)

    href, other, label = _SWITCH[locale]
    switch = (
        f'<a class="badge" href="{href}" hreflang="{other}" rel="alternate" '
        f'lang="{other}">{label}</a>\n    '
    )
    if '<div class="badges">' not in html:
        raise SystemExit("dashboard HTML has no .badges block for the switch link")
    html = html.replace('<div class="badges">\n', '<div class="badges">\n    ' + switch, 1)
    return html


def build(output_dir: Path, locale: str = "en") -> None:
    service = RouterService()
    output_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "healthz.json": _payload(service, "/healthz"),
        "policy.json": _payload(service, "/policy"),
        "replay-curated.json": _payload(service, "/replay?synth=false"),
        "replay-synth.json": _payload(service, "/replay?synth=true"),
        "regression.json": _payload(service, "/regression"),
        "fanout-sweep.json": _payload(service, "/fanout-sweep"),
        "compare.json": _payload(service, "/compare"),
        "experiments.json": localize_experiments(_payload(service, "/experiments"), locale),
        "metrics-history.json": localize_experiments(
            _payload(service, "/metrics/history"), locale
        ),
    }
    # R4 for data: the English demo must never leak Korean through client-side
    # rendered JSON (experiment cards, history titles). A missing per-locale
    # translation fails the build rather than shipping mixed language.
    if locale == "en":
        hangul = re.compile(r"[\uac00-\ud7a3]")
        for name in ("experiments.json", "metrics-history.json"):
            if hangul.search(json.dumps(files[name], ensure_ascii=False)):
                raise SystemExit(
                    f"en demo {name} still contains Korean — add the missing "
                    "EXPERIMENT_I18N entry in router.demo_i18n"
                )
    for name, payload in files.items():
        (output_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Copy the masked sealed 03D snapshot verbatim (rendered read-only by the
    # Measured-run tab). The bundle is aggregates only — no prompts/responses,
    # no endpoint or tenant ids — so it is safe to host as a static file.
    if not _MEASURED_BUNDLE.is_file():
        raise SystemExit(f"measured bundle not found: {_MEASURED_BUNDLE}")
    (output_dir / "published.json").write_text(
        _MEASURED_BUNDLE.read_text(encoding="utf-8"), encoding="utf-8"
    )

    # Inject the static endpoint map immediately before the dashboard script so
    # window.__ENDPOINTS__ is set before the main module reads it.
    dashboard_html = render_dashboard(locale)
    if dashboard_html.count("<script>") < 1:
        raise SystemExit("dashboard HTML has no <script> block to hook")
    localized = _localize(dashboard_html, locale)
    index_html = localized.replace("<script>", _ENDPOINT_INJECTION + "<script>", 1)
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")

    print(f"static site written to {output_dir}/ (locale={locale})")
    for name in ("index.html", "published.json", *files):
        print(f"  - {name}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("cost-router-dashboard")
    demo_locale = sys.argv[2] if len(sys.argv) > 2 else "en"
    build(target, demo_locale)
