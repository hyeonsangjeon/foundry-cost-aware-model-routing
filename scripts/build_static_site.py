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

Usage: python scripts/build_static_site.py [output_dir]   (default: cost-router-dashboard)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from router.dashboard import DASHBOARD_HTML  # noqa: E402
from router.server import RouterService  # noqa: E402

_ENDPOINT_INJECTION = """<script>
window.__ENDPOINTS__ = {
  health: "healthz.json",
  policy: "policy.json",
  replay: function (synth) { return synth ? "replay-synth.json" : "replay-curated.json"; }
};
</script>
"""


def _payload(service: RouterService, path: str) -> object:
    response = service.dispatch("GET", path)
    if response.status != 200:
        raise SystemExit(f"unexpected status {response.status} for {path}")
    return response.payload


def build(output_dir: Path) -> None:
    service = RouterService()
    output_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "healthz.json": _payload(service, "/healthz"),
        "policy.json": _payload(service, "/policy"),
        "replay-curated.json": _payload(service, "/replay?synth=false"),
        "replay-synth.json": _payload(service, "/replay?synth=true"),
    }
    for name, payload in files.items():
        (output_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Inject the static endpoint map immediately before the dashboard script so
    # window.__ENDPOINTS__ is set before the main module reads it.
    if DASHBOARD_HTML.count("<script>") < 1:
        raise SystemExit("dashboard HTML has no <script> block to hook")
    index_html = DASHBOARD_HTML.replace("<script>", _ENDPOINT_INJECTION + "<script>", 1)
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")

    print(f"static site written to {output_dir}/")
    for name in ("index.html", *files):
        print(f"  - {name}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("cost-router-dashboard")
    build(target)
