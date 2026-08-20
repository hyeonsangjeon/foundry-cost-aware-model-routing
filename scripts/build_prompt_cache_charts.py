#!/usr/bin/env python3
"""Build the two static charts for the prompt-cache explainer.

Offline only — never calls Azure. Two phases, mirroring
``build_03d_dashboard.py``:

1. **extract** (needs the gitignored sealed runs): aggregate the three sealed
   ``traces.jsonl`` into a small *tracked* bundle under
   ``docs/assets/prompt-cache/``. Only integer token sums are carried over — no
   prompt text, no response text, no task ids, no endpoint — so the public site
   never reads the sealed run and the bundle cannot leak workload content.
2. **charts** (needs only the tracked bundle): render four deterministic SVGs
   (two charts × two locales). No timestamps in the output, byte-stable across
   runs.

Both charts restate figures the page already publishes; the script prints every
value it draws so the charts can be diffed against the page tables by eye:

* **Chart A** — §3-5 repeat progression, ``router-cost`` (100% Grok in all three
  runs), ``sum(cached) / sum(input)`` per repeat over HTTP 200 rows.
* **Chart B** — §3-3 Grok-slice comparison, Cost mode versus Balanced mode with
  the backend held fixed. gpt-family rows are excluded by construction: the
  slice is defined by ``pricing.resolved_model``.

§3-2 (per-arm ratios) and §3-4 (the 12 → 13 turnover) are deliberately **not**
charted. A bar of §3-2 would render the unreadable zeros of §2 as if they were
measured absences, and a two-line plot of §3-4 reads as causation, which §4
explicitly disclaims. Both stay tables.

Usage::

    python scripts/build_prompt_cache_charts.py            # extract + charts
    python scripts/build_prompt_cache_charts.py --charts-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "assets" / "prompt-cache"
BUNDLE_PATH = OUT_DIR / "published.json"
RUNS_ROOT = ROOT / "results" / "local" / "03d" / "run"

# Experiment label -> sealed run id. The same three runs the page re-reads; the
# ids are already public in docs/assets/03d/published.json and the lab notebook.
RUNS: dict[str, str] = {
    "11": "20260806T023822Z",
    "12": "20260806T075344Z",
    "13": "20260814T141510Z",
}
VOID = {"11"}  # experiment 11 is VOID; every reader-facing label must say so

# Deployment -> public arm label + Model Router mode name.
ARMS: dict[str, tuple[str, str, str]] = {
    # deployment: (arm label, English mode, Korean mode)
    "model-router-cost": ("router-cost", "Cost mode", "Cost 모드"),
    "model-router": ("router-balanced", "Balanced mode", "Balanced 모드"),
}
COST_ARM = "model-router-cost"
BALANCED_ARM = "model-router"
GROK = "grok-4-1-fast-reasoning"
REPEATS = ("1", "2", "3")


# --------------------------------------------------------------------------- #
# Phase 1 — aggregate the sealed traces into the tracked bundle
# --------------------------------------------------------------------------- #
def _rows(run_dir: Path) -> list[dict]:
    path = run_dir / "traces.jsonl"
    if not path.is_file():
        raise SystemExit(f"build_prompt_cache_charts: missing sealed traces {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def build_bundle(runs_root: Path) -> dict:
    """Aggregate the three sealed runs into the publishable chart bundle.

    Only HTTP 200 rows are aggregated, the same rule the page states in §1: the
    non-200 rows are all HTTP 408 carrying ``tokens.input == 0``.
    """

    progression: dict[str, dict[str, dict[str, int]]] = {}
    grok_slice: dict[str, dict[str, dict[str, int]]] = {}
    provenance: dict[str, dict[str, str]] = {}

    for exp in sorted(RUNS):
        run_dir = runs_root / RUNS[exp]
        rows = [r for r in _rows(run_dir) if r.get("http_status") == 200]
        provenance[exp] = {
            "run_id": RUNS[exp],
            "traces_sha256": _sha256(run_dir / "traces.jsonl"),
        }

        per_repeat: dict[str, dict[str, int]] = {r: {"cached": 0, "input": 0} for r in REPEATS}
        for row in rows:
            if row.get("candidate_model") != COST_ARM:
                continue
            key = str(row.get("repeat_idx"))
            if key not in per_repeat:
                continue
            per_repeat[key]["cached"] += int(row["tokens"]["cached"])
            per_repeat[key]["input"] += int(row["tokens"]["input"])
        progression[exp] = per_repeat

        per_arm: dict[str, dict[str, int]] = {}
        for row in rows:
            arm = row.get("candidate_model")
            if arm not in (COST_ARM, BALANCED_ARM):
                continue
            if (row.get("pricing") or {}).get("resolved_model") != GROK:
                continue
            slot = per_arm.setdefault(arm, {"cached": 0, "input": 0, "rows": 0})
            slot["cached"] += int(row["tokens"]["cached"])
            slot["input"] += int(row["tokens"]["input"])
            slot["rows"] += 1
        grok_slice[exp] = per_arm

    return {
        "schema": "prompt-cache-charts/v1",
        "note": (
            "Integer token sums over HTTP 200 rows of the three sealed runs. "
            "Percentages are derived at render time as cached / input. "
            "No prompt or response text is carried here."
        ),
        "backend": GROK,
        "provenance": provenance,
        "repeat_progression": progression,
        "grok_slice": grok_slice,
    }


def write_bundle(bundle: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    BUNDLE_PATH.write_text(blob, encoding="utf-8")
    print(f"wrote {BUNDLE_PATH.relative_to(ROOT)}")


def pct(part: dict[str, int]) -> float:
    return 100.0 * part["cached"] / part["input"] if part["input"] else 0.0


# --------------------------------------------------------------------------- #
# Tiny SVG toolkit — same palette as build_03d_dashboard.py
# --------------------------------------------------------------------------- #
BG = "#ffffff"
INK = "#1f2933"
SUB = "#52606d"
MUTE = "#7b8794"
AXIS = "#9aa5b1"
GRID = "#e1e6ec"
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"

# Chart A ramps one hue across the three repeats so the rise reads as a
# progression. Colour is never the only cue: each bar is labelled with its
# repeat number and its value, and repeat 2 is hatched.
REPEAT_FILL = {"1": "#a9c9e8", "2": "#5b9bd5", "3": "#1f5c99"}
# Chart B: Cost mode solid, Balanced mode hatched — readable without colour.
BAR_COST = "#2f9e44"
BAR_BALANCED = "#5b7089"


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _n(value: float) -> str:
    """Fixed-precision coordinate, so re-runs are byte-identical."""
    return f"{value:.1f}"


def _txt(x, y, s, *, size=12, fill=SUB, weight=None, anchor="start"):
    attrs = f'x="{_n(x)}" y="{_n(y)}" font-size="{size}" fill="{fill}" text-anchor="{anchor}"'
    if weight:
        attrs += f' font-weight="{weight}"'
    return f"  <text {attrs}>{_esc(s)}</text>"


def _line(x1, y1, x2, y2, *, stroke=AXIS, width="1", dash=None):
    attrs = f'x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}"'
    attrs += f' stroke="{stroke}" stroke-width="{width}"'
    if dash:
        attrs += f' stroke-dasharray="{dash}"'
    return f"  <line {attrs}/>"


def _hatch(x: float, y: float, w: float, bottom: float, *, bands: int = 9) -> list[str]:
    """White rules across a bar, so a pair of bars differs without colour."""
    out = []
    for k in range(1, bands):
        yy = y + (bottom - y) * k / bands
        if yy < y + 3 or yy > bottom - 3:
            continue
        out.append(_line(x, yy, x + w, yy, stroke="#ffffff", width="1.4"))
    return out


def _svg_open(w: int, h: int, title: str, desc: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="{FONT}" role="img" '
        f'aria-labelledby="chart-title chart-desc">\n'
        f'  <title id="chart-title">{_esc(title)}</title>\n'
        f'  <desc id="chart-desc">{_esc(desc)}</desc>\n'
        f'  <rect x="0" y="0" width="{w}" height="{h}" fill="{BG}"/>\n'
    )


def _join(parts: list[str]) -> str:
    return "".join(p if p.endswith("\n") else p + "\n" for p in parts)


# --------------------------------------------------------------------------- #
# Chart copy, written natively per locale (not machine-substituted)
# --------------------------------------------------------------------------- #
COPY: dict[str, dict[str, str]] = {
    "en": {
        "a_title": "Recorded cache ratio across the three repeats — Cost mode",
        "a_sub": (
            "sum(cached) / sum(input) over HTTP 200 rows · router-cost, whose rows are "
            "100% Grok in all three runs"
        ),
        "a_warn": (
            "Repeat 1 is not a cold baseline: the first paid call of every run already "
            "recorded cached = 149 / input = 155 (§3-5)."
        ),
        "a_rep": "Repeat {n}",
        "a_svgtitle": "Recorded cache ratio by repeat, three sealed runs, Cost mode",
        "a_svgdesc": (
            "Grouped bar chart, one group per run, one bar per repeat, on a vertical axis "
            "running from 0 to 100 percent. Experiment 11 (VOID) reads 83.64, 95.67, "
            "100.00. Experiment 12 reads 89.61, 100.00, 100.00. Experiment 13 reads 90.79, "
            "100.00, 100.00. All three runs step up in the same shape and none falls back. "
            "Repeat 1 is not a cold baseline."
        ),
        "b_title": (
            "With the backend held fixed, the arm that spread its requests is not the "
            "lower one"
        ),
        "b_sub": (
            "Grok rows only · sum(cached) / sum(input) · gpt-family rows are excluded by "
            "construction (§3-3)"
        ),
        "b_note": (
            "Experiment 13 has no bar for Balanced mode: that arm recorded no Grok rows "
            "at all (§3-3)."
        ),
        "b_svgtitle": "Cost mode versus Balanced mode on the Grok slice only",
        "b_svgdesc": (
            "Grouped bar chart from 0 to 100 percent. Experiment 11 (VOID): Cost mode "
            "93.11 percent, Balanced mode 99.41 percent. Experiment 12: Cost mode 96.47 "
            "percent, Balanced mode 99.10 percent. In both runs Balanced mode, the arm "
            "that spread its requests across backends, recorded the higher ratio once the "
            "backend is held fixed. Experiment 13 recorded no Grok rows in Balanced mode."
        ),
        "void": "(VOID)",
        "exp": "Experiment",
    },
    "ko": {
        "a_title": "세 번의 반복에 걸친 캐시 기록 비율 — Cost 모드",
        "a_sub": (
            "HTTP 200 행에 대한 sum(cached) / sum(input) · 세 런 모두 행이 "
            "100% Grok인 router-cost"
        ),
        "a_warn": (
            "1회차는 콜드 기준선이 아닙니다. 세 런 모두 런의 최초 유료 호출이 이미 "
            "cached = 149 / input = 155로 기록됐습니다(§3-5)."
        ),
        "a_rep": "{n}회차",
        "a_svgtitle": "봉인된 세 런의 회차별 캐시 기록 비율, Cost 모드",
        "a_svgdesc": (
            "런마다 한 묶음, 회차마다 한 막대인 묶음 막대 그래프이고 세로축은 0에서 "
            "100퍼센트입니다. 실험 11(무효)은 83.64, 95.67, 100.00입니다. 실험 12는 89.61, "
            "100.00, 100.00입니다. 실험 13은 90.79, 100.00, 100.00입니다. 세 런이 같은 모양으로 "
            "올라가고 되돌아 내려간 런은 없습니다. 1회차는 콜드 기준선이 아닙니다."
        ),
        "b_title": "백엔드를 고정하면 요청을 나눠 보낸 쪽이 더 낮지 않습니다",
        "b_sub": (
            "Grok 행만 · sum(cached) / sum(input) · gpt 계열 행은 정의상 "
            "들어오지 않습니다(§3-3)"
        ),
        "b_note": (
            "실험 13에 Balanced 모드 막대가 없는 것은 그 arm에 Grok 행이 하나도 "
            "없었기 때문입니다(§3-3)."
        ),
        "b_svgtitle": "Grok 슬라이스만 놓고 본 Cost 모드와 Balanced 모드",
        "b_svgdesc": (
            "0에서 100퍼센트까지의 묶음 막대 그래프입니다. 실험 11(무효)은 Cost 모드 93.11퍼센트, "
            "Balanced 모드 99.41퍼센트입니다. 실험 12는 Cost 모드 96.47퍼센트, Balanced 모드 "
            "99.10퍼센트입니다. 백엔드를 고정하면 두 런 모두에서 요청을 여러 백엔드로 나눠 보낸 "
            "Balanced 모드가 더 높게 기록됐습니다. 실험 13의 Balanced 모드에는 Grok 행이 "
            "없었습니다."
        ),
        "void": "(무효)",
        "exp": "실험",
    },
}


# --------------------------------------------------------------------------- #
# Chart A — repeat progression
# --------------------------------------------------------------------------- #
def render_repeat_progression(bundle: dict, locale: str) -> str:
    """Grouped bars: one group per run, one bar per repeat.

    Grouping by run rather than by repeat puts the three staircases side by
    side, which is the shape the section claims. Bars, not lines: all three runs
    reach 100.00 at repeat 3, so three lines would land on one another there.
    """
    c = COPY[locale]
    w, h = 760, 420
    left, right, top, bot = 76, 700, 104, 306
    exps = sorted(bundle["repeat_progression"])
    out = [_svg_open(w, h, c["a_svgtitle"], c["a_svgdesc"])]
    out.append(_txt(24, 34, c["a_title"], size=16, fill=INK, weight=700))
    out.append(_txt(24, 56, c["a_sub"], size=11, fill=MUTE))

    def py(value: float) -> float:
        return bot - (bot - top) * value / 100.0

    # Axis from zero: an 80–100 window would exaggerate the rise.
    for tick in (0, 25, 50, 75, 100):
        y = py(tick)
        out.append(_line(left, y, right, y, stroke=GRID if tick else AXIS,
                         dash="4 4" if tick else None))
        out.append(_txt(left - 12, y + 4, f"{tick}%", size=11, fill=MUTE, anchor="end"))
    out.append(_line(left, top - 18, left, bot, width="1.4"))

    span = (right - left) / len(exps)
    bar_w, gap = 46.0, 10.0
    inset = (span - (len(REPEATS) * bar_w + (len(REPEATS) - 1) * gap)) / 2.0
    for gi, exp in enumerate(exps):
        base = left + span * gi + inset
        for bi, rep in enumerate(REPEATS):
            value = pct(bundle["repeat_progression"][exp][rep])
            x = base + bi * (bar_w + gap)
            y = py(value)
            out.append(
                f'  <rect x="{_n(x)}" y="{_n(y)}" width="{_n(bar_w)}" '
                f'height="{_n(bot - y)}" rx="3" fill="{REPEAT_FILL[rep]}"/>'
            )
            if rep == "2":
                out += _hatch(x, y, bar_w, bot)
            out.append(_txt(x + bar_w / 2, y - 9, f"{value:.2f}", size=11,
                            fill=INK, weight=700, anchor="middle"))
            out.append(_txt(x + bar_w / 2, bot + 18, c["a_rep"].format(n=rep), size=10,
                            fill=SUB, anchor="middle"))
        label = f"{c['exp']} {exp}" + (f" {c['void']}" if exp in VOID else "")
        out.append(_txt(base + (span - inset * 2) / 2, bot + 42, label, size=12,
                        fill=INK, weight=600, anchor="middle"))

    out.append(_txt(24, h - 34, c["a_warn"], size=11, fill=SUB))
    out.append("</svg>\n")
    return _join(out)


# --------------------------------------------------------------------------- #
# Chart B — Grok slice, Cost mode vs Balanced mode
# --------------------------------------------------------------------------- #
def render_backend_fixed(bundle: dict, locale: str) -> str:
    c = COPY[locale]
    w, h = 760, 420
    left, right, top, bot = 76, 700, 112, 300
    groups = [e for e in sorted(bundle["grok_slice"]) if BALANCED_ARM in bundle["grok_slice"][e]]
    out = [_svg_open(w, h, c["b_svgtitle"], c["b_svgdesc"])]
    out.append(_txt(24, 34, c["b_title"], size=15, fill=INK, weight=700))
    out.append(_txt(24, 56, c["b_sub"], size=11, fill=MUTE))

    def py(value: float) -> float:
        return bot - (bot - top) * value / 100.0

    for tick in (0, 25, 50, 75, 100):
        y = py(tick)
        out.append(_line(left, y, right, y, stroke=GRID if tick else AXIS,
                         dash="4 4" if tick else None))
        out.append(_txt(left - 12, y + 4, f"{tick}%", size=11, fill=MUTE, anchor="end"))
    out.append(_line(left, top - 18, left, bot, width="1.4"))

    span = (right - left) / len(groups)
    bar_w, gap = 88.0, 16.0
    for gi, exp in enumerate(groups):
        centre = left + span * (gi + 0.5)
        base = centre - (2 * bar_w + gap) / 2.0
        for bi, (arm, colour) in enumerate(((COST_ARM, BAR_COST), (BALANCED_ARM, BAR_BALANCED))):
            value = pct(bundle["grok_slice"][exp][arm])
            x = base + bi * (bar_w + gap)
            y = py(value)
            out.append(
                f'  <rect x="{_n(x)}" y="{_n(y)}" width="{_n(bar_w)}" '
                f'height="{_n(bot - y)}" rx="3" fill="{colour}"/>'
            )
            if bi:  # hatch the Balanced bar so the pair differs without colour
                out += _hatch(x, y, bar_w, bot)
            out.append(_txt(x + bar_w / 2, y - 10, f"{value:.2f}%", size=13,
                            fill=INK, weight=700, anchor="middle"))
            mode = ARMS[arm][1] if locale == "en" else ARMS[arm][2]
            out.append(_txt(x + bar_w / 2, bot + 20, mode, size=11, fill=INK,
                            weight=600, anchor="middle"))
            out.append(_txt(x + bar_w / 2, bot + 35, ARMS[arm][0], size=10, fill=MUTE,
                            anchor="middle"))
        label = f"{c['exp']} {exp}" + (f" {c['void']}" if exp in VOID else "")
        out.append(_txt(centre, bot + 60, label, size=12, fill=INK, weight=600, anchor="middle"))

    out.append(_txt(24, h - 34, c["b_note"], size=11, fill=SUB))
    out.append("</svg>\n")
    return _join(out)


CHARTS = (
    ("repeat-progression", render_repeat_progression),
    ("backend-fixed", render_backend_fixed),
)


def render_all(bundle: dict) -> list[Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for name, fn in CHARTS:
        for locale in ("en", "ko"):
            path = OUT_DIR / f"{name}.{locale}.svg"
            path.write_text(fn(bundle, locale), encoding="utf-8")
            written.append(path)
            print(f"wrote {path.relative_to(ROOT)}")
    return written


# --------------------------------------------------------------------------- #
# Cross-check output: every figure the charts draw, for diffing against the page
# --------------------------------------------------------------------------- #
def print_figures(bundle: dict) -> None:
    print("\nchart A — recorded cache ratio per repeat (router-cost, HTTP 200 rows)")
    print("           compare with the first table in section 3-5")
    for exp in sorted(bundle["repeat_progression"]):
        cells = "  ".join(
            f"repeat {rep} {pct(bundle['repeat_progression'][exp][rep]):6.2f}%" for rep in REPEATS
        )
        print(f"  exp {exp:<3}{' (VOID)' if exp in VOID else '       '}  {cells}")

    print("\nchart B — Grok slice only, cached / input (backend held fixed)")
    print("           compare with the second table in section 3-3")
    for exp in sorted(bundle["grok_slice"]):
        arms = bundle["grok_slice"][exp]
        parts = []
        for arm in (COST_ARM, BALANCED_ARM):
            if arm in arms:
                parts.append(f"{ARMS[arm][0]:<16}{pct(arms[arm]):6.2f}% (rows {arms[arm]['rows']})")
            else:
                parts.append(f"{ARMS[arm][0]:<16}   no Grok rows")
        print(f"  exp {exp:<3}{' (VOID)' if exp in VOID else '       '}  {parts[0]}")
        print(f"{'':<14}{parts[1]}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--charts-only",
        action="store_true",
        help="re-render the SVGs from the tracked bundle (no sealed run needed)",
    )
    ap.add_argument(
        "--runs-root",
        type=Path,
        default=RUNS_ROOT,
        help="directory holding the sealed run snapshots",
    )
    args = ap.parse_args(argv)

    if args.charts_only:
        if not BUNDLE_PATH.is_file():
            raise SystemExit(f"build_prompt_cache_charts: missing bundle {BUNDLE_PATH}")
        bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    else:
        bundle = build_bundle(args.runs_root)
        write_bundle(bundle)

    render_all(bundle)
    print_figures(bundle)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
