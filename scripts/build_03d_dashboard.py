#!/usr/bin/env python3
"""Build the public 03D results dashboard: a masked JSON bundle + static SVG charts.

Offline only — never calls Azure. Two phases:

1. **extract** (needs the gitignored sealed run): run ``build_publish_bundle`` (the
   sanctioned, replay-gated, tenant-masked export), then augment it with two
   publishable aggregates the base bundle omits — per-arm backend distribution and
   a per-cell timeout breakdown (no prompts/responses, only model names + task ids
   + HTTP status). The endpoint is masked harder than the base host-only redaction
   (the resource sub-domain is dropped). The result is written as a *tracked*
   artifact under ``docs/assets/03d/`` so the public site never reads the sealed run.

2. **charts** (needs only the tracked bundle): render three deterministic SVGs
   (arm cost comparison, cost-vs-quality scatter, backend distribution). No browser
   fetch, no timestamps in the output, byte-stable across runs.

Usage::

    python scripts/build_03d_dashboard.py --run results/local/03d/run/<id>   # extract + charts
    python scripts/build_03d_dashboard.py --charts-only     # re-render from tracked bundle
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from router.measure import build_publish_bundle  # noqa: E402
from router.pricing import format_usd, format_usd_avg  # noqa: E402

OUT_DIR = ROOT / "docs" / "assets" / "03d"
BUNDLE_PATH = OUT_DIR / "published.json"

# Deployment name -> (public arm label, routing mode). Arm labels and mode names
# are public; deployment strings are not tenant secrets either, but the arm label
# is what a reader sees.
ARM_META = {
    "model-router-cost": ("router-cost", "Cost"),
    "model-router": ("router-balanced", "Balanced"),
    "model-router-quality": ("router-quality", "Quality"),
    "gpt-5.6-sol": ("direct-premium", "—"),
}
# Cost-ascending display order (reads as a ramp from cheapest to priciest).
ARM_ORDER = ["model-router-cost", "model-router", "gpt-5.6-sol", "model-router-quality"]

# Stable per-model colours for the backend chart.
MODEL_COLOURS = {
    "grok-4-1-fast-reasoning": "#2bb0a4",
    "gpt-5.4": "#f0a202",
    "gpt-5.5": "#6c8ae4",
    "gpt-5": "#9b6dd6",
    "gpt-5.6-sol": "#e8683f",
}


# --------------------------------------------------------------------------- #
# Phase 1 — extract the masked public bundle
# --------------------------------------------------------------------------- #
def _mask_endpoint(value: str | None) -> str | None:
    """Drop the resource-identifying sub-domain, keep the service domain only.

    ``https://<resource>.cognitiveservices.azure.com``
    -> ``https://***.cognitiveservices.azure.com``. The base bundle already
    reduces to host-only; this removes the leftmost (resource) label as well.
    """

    if not value:
        return value
    parts = urlsplit(value)
    host = parts.netloc
    if not host:
        return "***"
    labels = host.split(".")
    if len(labels) > 2:
        labels[0] = "***"
        host = ".".join(labels)
    else:
        host = "***." + ".".join(labels[-2:]) if len(labels) == 2 else "***"
    return urlunsplit((parts.scheme, host, "", "", ""))


def _backends_by_arm(run_dir: Path) -> dict[str, dict[str, int]]:
    """Per-arm distribution of the router's resolved backend model (graded cells)."""

    terminal: dict[tuple[str, str, int], dict] = {}
    for line in (run_dir / "traces.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        terminal[(row["candidate_model"], row["task_id"], row["repeat_idx"])] = row
    dist: dict[str, Counter] = {dep: Counter() for dep in ARM_META}
    for row in terminal.values():
        resolved = (row.get("pricing") or {}).get("resolved_model")
        if resolved and row["candidate_model"] in dist:
            dist[row["candidate_model"]][resolved] += 1
    return {
        dep: dict(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))
        for dep, counter in dist.items()
    }


def build_masked_bundle(run_dir: Path) -> dict:
    """Sanctioned redacted export + publishable backend & timeout aggregates."""

    bundle = build_publish_bundle(run_dir)  # replay-gated; refuses corrupt snapshots
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    # Harden the endpoint mask (base bundle keeps host-only).
    prov = bundle["provenance"]
    prov["endpoint"] = _mask_endpoint(prov.get("endpoint"))

    # Publishable backend distribution (model names only).
    bundle["result"]["backends"] = _backends_by_arm(run_dir)

    # Per-arm graded-cell coverage. graded == resolved-backend count (verified: the
    # only ungraded cells are timeouts, which resolve no backend), so it is exactly
    # derivable from the published aggregates without exposing any per-cell content.
    n = int(summary.get("n") or 3)
    cov_by_arm = {}
    for dep in ARM_META:
        graded = sum(bundle["result"]["backends"][dep].values())
        planned = bundle["result"]["quality"]["by_candidate"][dep]["tasks_planned"] * n
        cov_by_arm[dep] = {
            "graded": graded,
            "planned": planned,
            "coverage": (graded / planned) if planned else None,
        }
    bundle["result"]["coverage_by_arm"] = cov_by_arm

    # Publishable timeout / failure breakdown — no content, only routing metadata.
    bundle["result"]["failures_detail"] = [
        {
            "arm": ARM_META.get(f["candidate_model"], (f["candidate_model"],))[0],
            "deployment": f["candidate_model"],
            "task_id": f["task_id"],
            "repeat_idx": f["repeat_idx"],
            "http_status": f["http_status"],
            "fail_reason": f["fail_reason"],
        }
        for f in summary.get("failures", [])
    ]
    bundle["dashboard"] = {
        "note": "Derived by scripts/build_03d_dashboard.py from the sealed run. "
        "Contains aggregates only — no prompts, responses, endpoints or tenant ids.",
        "arm_order": [ARM_META[d][0] for d in ARM_ORDER],
    }
    return bundle


# Non-secret structural markers that must never appear in a public bundle. These
# are schema/field names (not tenant identifiers), so they are safe to hardcode.
_STRUCTURAL_FORBIDDEN = (
    '"content"',  # raw response body field
    "per_million",  # tenant rate-card unit field
    "input_per_1k",  # tenant rate-card unit field
)


def _manifest_secrets(run_dir: Path) -> list[str]:
    """Sensitive identifiers to redact, read from the gitignored manifest (and the
    operator runtime env) at build time — never hardcoded in this tracked script."""

    secrets: list[str] = []
    mpath = run_dir / "manifest.json"
    if mpath.is_file():
        m = json.loads(mpath.read_text(encoding="utf-8"))
        host = urlsplit(m.get("endpoint") or "").netloc
        if host:
            secrets.append(host)  # full resource host
            secrets.append(host.split(".")[0])  # resource-name label
        if m.get("pricing_path"):
            secrets.append(str(m["pricing_path"]))  # tenant rate-card path
    for var in ("AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"):
        val = os.environ.get(var)
        if val:
            secrets.append(val)
    return [s for s in secrets if s]


def _assert_no_leak(bundle: dict, secrets: list[str] | None = None) -> None:
    """Fail closed if any known-sensitive token slipped into the public bundle."""

    # Scan everything except our own descriptive note (which legitimately spells
    # out what is excluded, e.g. the words "prompts"/"responses").
    scanned = {k: v for k, v in bundle.items() if k != "dashboard"}
    blob = json.dumps(scanned, ensure_ascii=False)
    forbidden = list(_STRUCTURAL_FORBIDDEN) + list(secrets or [])
    hit = [tok for tok in forbidden if tok and tok in blob]
    if hit:
        raise SystemExit(f"refusing to write bundle: leaked tokens {hit}")

    # Defence in depth: no raw workload prompt text may appear anywhere.
    wl = ROOT / "benchmarks" / "original-coding" / "tasks.jsonl"
    if wl.is_file():
        for line in wl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            task = json.loads(line)
            probe = (task.get("user_prompt") or "")[:40].strip()
            if probe and probe in blob:
                raise SystemExit(
                    f"refusing to write bundle: prompt text leaked for {task.get('id')}"
                )


# --------------------------------------------------------------------------- #
# Reader-facing view model (shared by charts + used to sanity-check the page)
# --------------------------------------------------------------------------- #
def arm_rows(bundle: dict) -> list[dict]:
    cost = bundle["result"]["cost"]["by_candidate"]
    qual = bundle["result"]["quality"]["by_candidate"]
    backends = bundle["result"]["backends"]
    cov = bundle["result"].get("coverage_by_arm", {})
    rows = []
    for dep in ARM_ORDER:
        label, mode = ARM_META[dep]
        c, q = cost[dep], qual[dep]
        rows.append(
            {
                "deployment": dep,
                "label": label,
                "mode": mode,
                "total_usd": c["total_usd"],
                "cost_complete": c["cost_complete"],
                "pass_rate": q["pass_rate"],
                "tasks_passed": q["tasks_passed"],
                "tasks_planned": q["tasks_planned"],
                "cost_per_pass": q["cost_per_pass_usd"],
                "coverage": (cov.get(dep) or {}).get("coverage"),
                "backends": backends[dep],
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Tiny SVG toolkit (no deps; matches the site's light theme)
# --------------------------------------------------------------------------- #
BG = "#ffffff"
INK = "#1f2933"
SUB = "#52606d"
MUTE = "#7b8794"
AXIS = "#9aa5b1"
GRID = "#e1e6ec"
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
WIN = "#2f9e44"  # router-cost highlight (green)
PREM = "#e8683f"  # direct-premium (orange)
NEUT = "#5b7089"  # other router arms


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _txt(x, y, s, *, size=12, fill=SUB, weight=None, anchor="start", rotate=None):
    attrs = f'x="{x}" y="{y}" font-size="{size}" fill="{fill}" text-anchor="{anchor}"'
    if weight:
        attrs += f' font-weight="{weight}"'
    if rotate is not None:
        attrs += f' transform="rotate({rotate} {x} {y})"'
    return f"<text {attrs}>{_esc(s)}</text>"


def _svg_open(w, h, label):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="{FONT}" role="img" '
        f'aria-label="{_esc(label)}">\n'
        f'  <rect x="0" y="0" width="{w}" height="{h}" fill="{BG}"/>\n'
    )


def _line(x1, y1, x2, y2, *, stroke=AXIS, width="1", dash=None):
    attrs = f'x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"'
    attrs += f' stroke="{stroke}" stroke-width="{width}"'
    if dash:
        attrs += f' stroke-dasharray="{dash}"'
    return f"  <line {attrs}/>"


def _circle(cx, cy, r, fill, *, stroke="#ffffff", width="1.5"):
    attrs = f'cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"'
    attrs += f' stroke="{stroke}" stroke-width="{width}"'
    return f"  <circle {attrs}/>"


def _rect(x, y, w, h, fill, *, rx=None, opacity=None):
    attrs = f'x="{x}" y="{y}" width="{w}" height="{h}"'
    if rx is not None:
        attrs += f' rx="{rx}"'
    attrs += f' fill="{fill}"'
    if opacity is not None:
        attrs += f' opacity="{opacity}"'
    return f"  <rect {attrs}/>"


# --------------------------------------------------------------------------- #
# Chart 1 — arm cost comparison (horizontal bars + pass-rate / cost-per-pass)
# --------------------------------------------------------------------------- #
def render_cost_chart(rows: list[dict]) -> str:
    w, h = 760, 360
    x0, top, bar_h, gap = 150, 78, 40, 26
    max_cost = max(r["total_usd"] for r in rows)
    axis_w = 470
    label = (
        "Per-arm total cost bar chart. router-cost "
        f"{format_usd(rows[0]['total_usd'])} versus direct-premium "
        f"{format_usd(next(r['total_usd'] for r in rows if r['label'] == 'direct-premium'))}; "
        "each bar annotated with task pass-rate and cost-per-pass."
    )
    out = [_svg_open(w, h, label)]
    out.append(_txt(24, 34, "arm별 총비용 — 통과율 · cost-per-pass", size=16, fill=INK, weight=700))
    out.append(
        _txt(
            24,
            56,
            "24 tasks × n=3 = 288 cells · 표시 금액 2자리(서브센트 4자리) · 절감은 풀정밀도 계산",
            size=11,
            fill=MUTE,
        )
    )
    for i, r in enumerate(rows):
        y = top + i * (bar_h + gap)
        colour = (
            WIN
            if r["label"] == "router-cost"
            else (PREM if r["label"] == "direct-premium" else NEUT)
        )
        bw = max(2, round(axis_w * (r["total_usd"] / max_cost)))
        out.append(
            _txt(
                x0 - 10, y + bar_h / 2 + 4, r["label"], size=12, fill=INK, weight=600, anchor="end"
            )
        )
        out.append(
            _txt(x0 - 10, y + bar_h / 2 + 18, f"({r['mode']})", size=10, fill=MUTE, anchor="end")
        )
        out.append(
            f'  <rect x="{x0}" y="{y}" width="{bw}" height="{bar_h}" rx="4" fill="{colour}"/>'
        )
        pr = f"pass {r['pass_rate'] * 100:.1f}% ({r['tasks_passed']}/{r['tasks_planned']})"
        cpp = f"$/pass {format_usd_avg(r['cost_per_pass'])}"
        out.append(
            _txt(
                x0 + bw + 10,
                y + bar_h / 2 - 2,
                format_usd(r["total_usd"]),
                size=13,
                fill=INK,
                weight=700,
            )
        )
        out.append(_txt(x0 + bw + 10, y + bar_h / 2 + 14, f"{pr} · {cpp}", size=10, fill=SUB))
    # headline contrast callout
    cy = h - 24
    out.append(
        _txt(
            24,
            cy,
            "핵심 대비: router-cost는 direct-premium 대비 95.2% 저렴(풀정밀도), "
            "품질 격차 4.17%p 이내.",
            size=11,
            fill=SUB,
        )
    )
    out.append("</svg>\n")
    return "".join(x if x.endswith("\n") else x + "\n" for x in out)


# --------------------------------------------------------------------------- #
# Chart 2 — cost vs quality scatter (quality mode costs more and passes less)
# --------------------------------------------------------------------------- #
def render_scatter(rows: list[dict]) -> str:
    w, h = 760, 440
    left, right, top, bot = 96, 700, 92, 360
    xmin, xmax = 0.0, 1.7  # cost USD
    ymin, ymax = 94.0, 101.0  # pass-rate %, zoomed to show the 4.17pp gap

    def px(cost):
        return left + (right - left) * (cost - xmin) / (xmax - xmin)

    def py(rate):
        return bot - (bot - top) * (rate - ymin) / (ymax - ymin)

    label = (
        "Cost versus pass-rate scatter. direct-premium costs less and has a higher "
        "pass rate than router-quality. router-cost has the lowest cost among the "
        "router arms with the same pass rate."
    )
    out = [_svg_open(w, h, label)]
    out.append(
        _txt(
            24,
            34,
            "비용 × 통과율 — Quality 모드는 비용이 더 들고 덜 풀었다",
            size=16,
            fill=INK,
            weight=700,
        )
    )
    out.append(
        _txt(24, 56, "y축 확대(94–101%)로 4.17%p 격차 가시화 · x축 총비용(USD)", size=11, fill=MUTE)
    )
    # axes
    out.append(_line(left, top, left, bot, width="1.4"))
    out.append(_line(left, bot, right, bot, width="1.4"))
    # y gridlines/ticks every 2%
    for rate in (94, 96, 98, 100):
        yy = py(rate)
        out.append(_line(left, f"{yy:.1f}", right, f"{yy:.1f}", stroke=GRID, dash="4 4"))
        out.append(_txt(left - 10, yy + 4, f"{rate}%", size=11, fill=MUTE, anchor="end"))
    out.append(
        _txt(34, (top + bot) / 2, "task pass-rate", size=12, fill=SUB, anchor="middle", rotate=-90)
    )
    # x ticks every $0.25
    tick = 0.0
    while tick <= xmax + 1e-9:
        xx = px(tick)
        out.append(_line(f"{xx:.1f}", bot, f"{xx:.1f}", bot + 5))
        out.append(_txt(xx, bot + 20, format_usd(tick), size=10, fill=MUTE, anchor="middle"))
        tick += 0.25
    out.append(
        _txt((left + right) / 2, h - 40, "arm 총비용 (USD)", size=12, fill=SUB, anchor="middle")
    )
    # Highlight the area that costs more and has an equal-or-lower pass rate than premium.
    prem = next(r for r in rows if r["label"] == "direct-premium")
    ppx, ppy = px(prem["total_usd"]), py(prem["pass_rate"] * 100)
    out.append(
        f'  <rect x="{ppx:.1f}" y="{ppy:.1f}" width="{right - ppx:.1f}" height="{bot - ppy:.1f}" '
        f'fill="#e8683f" opacity="0.06"/>'
    )
    out.append(
        _txt(
            right - 8,
            ppy + 16,
            "direct-premium보다 비싸고 통과율 낮음",
            size=10,
            fill=PREM,
            anchor="end",
        )
    )
    out.append(
        _txt(right - 8, ppy + 29, "→ 비용 높음 · ↓ 통과율 낮음", size=9, fill=MUTE, anchor="end")
    )
    # points
    for r in rows:
        cx, cy = px(r["total_usd"]), py(r["pass_rate"] * 100)
        colour = (
            WIN
            if r["label"] == "router-cost"
            else (PREM if r["label"] == "direct-premium" else NEUT)
        )
        out.append(_circle(f"{cx:.1f}", f"{cy:.1f}", 7, colour))
        # keep labels inside the frame: right-side points label leftwards
        right_side = cx > 560
        anchor = "end" if right_side else "start"
        lx = cx - 12 if right_side else cx + 12
        dy = 20 if r["label"] == "router-balanced" else -14
        out.append(_txt(lx, cy + dy, r["label"], size=11, fill=INK, weight=600, anchor=anchor))
        out.append(
            _txt(
                lx,
                cy + dy + 13,
                f"{format_usd(r['total_usd'])} · {r['pass_rate'] * 100:.1f}%",
                size=10,
                fill=SUB,
                anchor=anchor,
            )
        )
    out.append("</svg>\n")
    return "".join(x if x.endswith("\n") else x + "\n" for x in out)


# --------------------------------------------------------------------------- #
# Chart 3 — backend distribution (stacked bars per arm)
# --------------------------------------------------------------------------- #
def render_backends(rows: list[dict]) -> str:
    w, h = 760, 380
    x0, top, bar_h, gap = 150, 92, 34, 30
    axis_w = 470
    models = []
    for r in rows:
        for m in r["backends"]:
            if m not in models:
                models.append(m)
    label = (
        "Per-arm backend distribution stacked bars. router-cost routed 100% to "
        "grok-4-1-fast-reasoning; router-quality split gpt-5 and gpt-5.5 with no "
        "grok; direct-premium is 100% gpt-5.6-sol."
    )
    out = [_svg_open(w, h, label)]
    out.append(
        _txt(
            24,
            34,
            "백엔드 분포 — arm별 실제 라우팅된 모델 (graded 셀 기준)",
            size=16,
            fill=INK,
            weight=700,
        )
    )
    out.append(
        _txt(
            24,
            56,
            "Cost 모드 100% Grok은 void 런과 이번 런 두 번 연속 재현됐다",
            size=11,
            fill=MUTE,
        )
    )
    for i, r in enumerate(rows):
        y = top + i * (bar_h + gap)
        total = sum(r["backends"].values()) or 1
        out.append(
            _txt(
                x0 - 10, y + bar_h / 2 + 4, r["label"], size=12, fill=INK, weight=600, anchor="end"
            )
        )
        out.append(
            _txt(x0 - 10, y + bar_h / 2 + 18, f"({r['mode']})", size=10, fill=MUTE, anchor="end")
        )
        cx = x0
        for m, cnt in r["backends"].items():
            seg = axis_w * (cnt / total)
            colour = MODEL_COLOURS.get(m, "#b0b8c4")
            out.append(
                f'  <rect x="{cx:.1f}" y="{y}" width="{seg:.1f}" height="{bar_h}" fill="{colour}"/>'
            )
            pct = cnt / total * 100
            if seg > 42:
                out.append(
                    _txt(
                        cx + seg / 2,
                        y + bar_h / 2 + 4,
                        f"{pct:.0f}%",
                        size=11,
                        fill="#ffffff",
                        weight=700,
                        anchor="middle",
                    )
                )
            cx += seg
    # legend
    ly = h - 34
    lx = x0
    for m in models:
        out.append(_rect(lx, ly - 10, 12, 12, MODEL_COLOURS.get(m, "#b0b8c4"), rx=2))
        out.append(_txt(lx + 16, ly, m, size=10, fill=SUB))
        lx += 40 + 7 * len(m)
    out.append("</svg>\n")
    return "".join(x if x.endswith("\n") else x + "\n" for x in out)


# --------------------------------------------------------------------------- #
def write_charts(bundle: dict) -> list[Path]:
    rows = arm_rows(bundle)
    charts = {
        "arm-cost-comparison.svg": render_cost_chart(rows),
        "cost-vs-quality-scatter.svg": render_scatter(rows),
        "backend-distribution.svg": render_backends(rows),
    }
    written = []
    for name, svg in charts.items():
        p = OUT_DIR / name
        p.write_text(svg, encoding="utf-8")
        written.append(p)
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", help="sealed snapshot run directory (extract phase)")
    ap.add_argument(
        "--charts-only", action="store_true", help="re-render SVGs from the tracked bundle"
    )
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.charts_only:
        bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    else:
        if not args.run:
            ap.error("--run is required unless --charts-only")
        bundle = build_masked_bundle(Path(args.run))
        _assert_no_leak(bundle, _manifest_secrets(Path(args.run)))
        BUNDLE_PATH.write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {BUNDLE_PATH.relative_to(ROOT)}")

    for p in write_charts(bundle):
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
