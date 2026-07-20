#!/usr/bin/env python3
"""Generate animated explainer GIFs (one per experiment).

Style follows the dark-navy "flowing dots" explainer look: two lanes, a naive
baseline vs the cost-aware strategy, animated flow dots, live counters, and a
mechanism widget (escalation ladder / fan-out / dial / single-call) per
experiment. Frames are drawn with Pillow and assembled into a looping GIF with
ffmpeg (palettegen/paletteuse).

All numbers are the offline projection (labels.measured=false), matching
`cost-router experiment run <name>`.
"""

from __future__ import annotations

import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

W, H = 1120, 640
FRAMES = 40
FPS = 16

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
BG = (11, 20, 34)
INK = (226, 232, 240)
MUTED = (129, 146, 163)
FAINT = (34, 48, 69)
RED = (229, 72, 77)
GREEN = (46, 204, 113)
AMBER = (240, 160, 32)

TIERS = [
    ("mini-fast", 0.12, (200, 146, 43)),
    ("swift-coder", 0.35, (46, 139, 87)),
    ("balanced-pro", 1.05, (59, 125, 216)),
    ("deep-reasoner", 2.80, (123, 82, 201)),
    ("premium-max", 5.20, (192, 57, 43)),
]

_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    key = (kind, size)
    if key not in _FONT_CACHE:
        name = {
            "mono": "DejaVuSansMono.ttf",
            "monob": "DejaVuSansMono-Bold.ttf",
            "sansb": "DejaVuSans-Bold.ttf",
            "sans": "DejaVuSans.ttf",
        }[kind]
        _FONT_CACHE[key] = ImageFont.truetype(os.path.join(FONT_DIR, name), size)
    return _FONT_CACHE[key]


def blend(a: tuple, b: tuple, f: float) -> tuple:
    f = max(0.0, min(1.0, f))
    return tuple(round(a[i] + (b[i] - a[i]) * f) for i in range(3))


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def glow_dot(d: ImageDraw.ImageDraw, x: float, y: float, r: float, color: tuple) -> None:
    d.ellipse([x - r - 6, y - r - 6, x + r + 6, y + r + 6], fill=blend(BG, color, 0.22))
    d.ellipse([x - r - 3, y - r - 3, x + r + 3, y + r + 3], fill=blend(BG, color, 0.5))
    d.ellipse([x - r, y - r, x + r, y + r], fill=color)


def node(d: ImageDraw.ImageDraw, cx: float, cy: float, w: float, h: float,
         label: str, accent: tuple, sub: str | None = None, glow: bool = False) -> None:
    box = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
    fill = blend(BG, accent, 0.16 if glow else 0.10)
    d.rounded_rectangle(box, radius=10, fill=fill, outline=accent, width=2)
    if sub:
        d.text((cx, cy - 9), label, font=font("monob", 15), fill=INK, anchor="mm")
        d.text((cx, cy + 11), sub, font=font("mono", 12), fill=blend(INK, accent, 0.6), anchor="mm")
    else:
        d.text((cx, cy), label, font=font("monob", 15), fill=INK, anchor="mm")


def flow(d: ImageDraw.ImageDraw, x0: float, x1: float, y: float, t: float,
         color: tuple, n: int = 3, dim: bool = False) -> None:
    d.line([x0, y, x1, y], fill=blend(BG, INK, 0.28 if not dim else 0.16), width=3)
    for i in range(n):
        frac = ((i / n) + t) % 1.0
        x = x0 + frac * (x1 - x0)
        glow_dot(d, x, y, 5, color)


def seg_width(segments: list[tuple[str, ImageFont.FreeTypeFont, tuple]]) -> float:
    return sum(f.getlength(s) for s, f, _ in segments)


def draw_segments(d: ImageDraw.ImageDraw, x: float, y: float,
                  segments: list[tuple[str, ImageFont.FreeTypeFont, tuple]]) -> None:
    for s, f, c in segments:
        d.text((x, y), s, font=f, fill=c, anchor="lm")
        x += f.getlength(s)


def pill(d: ImageDraw.ImageDraw, x: float, y: float, text: str, fg: tuple, bg: tuple,
         fnt: ImageFont.FreeTypeFont, pad: int = 8) -> float:
    w = fnt.getlength(text)
    d.rounded_rectangle([x, y, x + w + 2 * pad, y + fnt.size + 8], radius=8, fill=bg)
    d.text((x + pad, y + 4 + fnt.size / 2), text, font=fnt, fill=fg, anchor="lm")
    return x + w + 2 * pad


def meter(d: ImageDraw.ImageDraw, x: float, y: float, w: float, frac: float,
          color: tuple, label: str, sub: str | None = None) -> None:
    h = 12
    d.rounded_rectangle([x, y, x + w, y + h], radius=6, fill=FAINT)
    fw = max(0.0, min(1.0, frac)) * w
    if fw > 4:
        d.rounded_rectangle([x, y, x + fw, y + h], radius=6, fill=color)
    d.text((x, y - 8), label, font=font("mono", 12), fill=MUTED, anchor="lb")
    if sub:
        d.text((x + w, y - 8), sub, font=font("monob", 12), fill=color, anchor="rb")


def lane_frame(d: ImageDraw.ImageDraw, y0: float, h: float, accent: tuple, label: str) -> None:
    d.rounded_rectangle([40, y0, W - 40, y0 + h], radius=14,
                        fill=blend(BG, accent, 0.06), outline=blend(BG, accent, 0.4), width=1)
    pill(d, 60, y0 + 14, label, blend(INK, accent, 0.7), blend(BG, accent, 0.20),
         font("monob", 13))


def escalation(d, x0, x1, y, accept_idx, t, honest=False):
    n = len(TIERS)
    xs = [x0 + (x1 - x0) * (i / (n - 1)) for i in range(n)]
    p = ease(min(1.0, t / 0.8))
    cur = round(p * accept_idx)
    for i, (name, _price, col) in enumerate(TIERS):
        cx = xs[i]
        reached = i <= cur
        if i < cur:
            state_col = RED
            fillf = 0.14
        elif i == cur and cur == accept_idx:
            state_col = RED if honest else GREEN
            fillf = 0.22
        elif i == cur:
            state_col = AMBER
            fillf = 0.2
        else:
            state_col = col
            fillf = 0.05
        box = [cx - 46, y - 20, cx + 46, y + 20]
        d.rounded_rectangle(box, radius=9, fill=blend(BG, state_col if reached else col, fillf),
                            outline=state_col if reached else blend(BG, col, 0.45),
                            width=2 if reached else 1)
        d.text((cx, y - 5), name, font=font("mono", 11),
               fill=INK if reached else MUTED, anchor="mm")
        mark = ""
        if i < cur:
            mark = "fail"
        elif i == cur and cur == accept_idx:
            mark = "keep" if not honest else "only"
        elif i == cur:
            mark = "try"
        if mark:
            mc = RED if mark == "fail" else (GREEN if mark == "keep" else
                                            (RED if mark == "only" else AMBER))
            d.text((cx, y + 9), mark, font=font("monob", 10), fill=mc, anchor="mm")
        if i < n - 1:
            seg_col = RED if i < cur else blend(BG, INK, 0.2)
            d.line([cx + 46, y, xs[i + 1] - 46, y], fill=seg_col, width=2)
            if i < cur:
                frac = t % 1.0
                mx = (cx + 46) + frac * ((xs[i + 1] - 46) - (cx + 46))
                glow_dot(d, mx, y, 4, RED)
    accept_col = RED if (honest and cur == accept_idx) else (
        GREEN if cur == accept_idx else AMBER)
    probe_x = xs[cur] - 46 - 11
    glow_dot(d, probe_x, y, 6, accept_col)


def fanout(d, x_app, x_cmp, x_win, y, t, collapsed_frac=0.0):
    ys = [y - 66, y - 33, y, y + 33, y + 66]
    active = 1 + round((1 - collapsed_frac) * 4)
    for i in range(5):
        col = TIERS[i][2]
        show = i < active or i == 2
        if not show:
            continue
        yb = ys[i]
        d.line([x_app + 60, y, x_cmp - 54, yb], fill=blend(BG, col, 0.55), width=2)
        for k in range(2):
            frac = ((k / 2) + t) % 1.0
            xx = (x_app + 60) + frac * ((x_cmp - 54) - (x_app + 60))
            yy = y + frac * (yb - y)
            glow_dot(d, xx, yy, 4, col)
    node(d, x_app, y, 108, 48, "workload", (59, 125, 216), sub="high-value")
    d.rounded_rectangle([x_cmp - 54, y - 26, x_cmp + 54, y + 26], radius=10,
                        fill=blend(BG, AMBER, 0.14), outline=AMBER, width=2)
    d.text((x_cmp, y - 6), "compare", font=font("monob", 14), fill=INK, anchor="mm")
    d.text((x_cmp, y + 11), "keep best", font=font("mono", 11), fill=blend(INK, AMBER, 0.6),
           anchor="mm")
    flow(d, x_cmp + 54, x_win - 66, y, t, TIERS[1][2], n=2)
    node(d, x_win, y, 128, 50, "swift-coder", TIERS[1][2], sub="winner", glow=True)


def single_call(d, x_app, x_mid, x_out, y, t, tier_idx, cov_target, cov_color, gauge=True):
    node(d, x_app, y, 100, 46, "prompt", (59, 125, 216))
    if gauge:
        d.rounded_rectangle([x_mid - 58, y - 26, x_mid + 58, y + 26], radius=10,
                            fill=blend(BG, (59, 125, 216), 0.14), outline=(59, 125, 216), width=2)
        d.text((x_mid, y - 6), "difficulty", font=font("monob", 13), fill=INK, anchor="mm")
        d.text((x_mid, y + 11), "pick one", font=font("mono", 11),
               fill=blend(INK, (59, 125, 216), 0.6), anchor="mm")
    flow(d, x_app + 52, x_mid - 58, y, t, (59, 125, 216), n=2)
    flow(d, x_mid + 58, x_out - 64, y, t, TIERS[tier_idx][2], n=2)
    name = TIERS[tier_idx][0]
    node(d, x_out, y, 128, 46, name, TIERS[tier_idx][2], glow=True)
    cov = ease(min(1.0, t / 0.8)) * cov_target
    meter(d, x_app - 50, y + 44, 320, cov / 100.0, cov_color,
          "coverage", sub=f"{cov:4.0f}%")


def scoreboard(d, before, after, delta, cov, dp=2):
    bf = f"${before:.{dp}f}"
    af = f"${after:.{dp}f}"
    fb = font("monob", 26)
    segs = [(bf, fb, RED), ("  ->  ", font("mono", 22), MUTED), (af, fb, GREEN)]
    total = seg_width(segs)
    draw_segments(d, W - 40 - total, 52, segs)
    d.text((W - 40, 92), f"{delta}   {cov}", font=font("monob", 15), fill=AMBER, anchor="rm")


def header(d, title_a, title_b, subtitle, t):
    d.text((48, 40), title_a, font=font("sansb", 33), fill=INK, anchor="lm")
    wa = font("sansb", 33).getlength(title_a + " ")
    d.text((48 + wa, 40), title_b, font=font("sansb", 33), fill=(90, 160, 246), anchor="lm")
    d.text((48, 82), subtitle, font=font("mono", 15), fill=MUTED, anchor="lm")
    pill(d, 48, 104, "offline · labels.measured=false", blend(INK, AMBER, 0.5),
         blend(BG, AMBER, 0.14), font("mono", 12))
    d.line([40, 138, W - 40, 138], fill=FAINT, width=1)
    d.rounded_rectangle([40, 137, 40 + (W - 80) * (t), 140], radius=2, fill=blend(BG, INK, 0.4))


def counter(d, x, y, label, value_text, color):
    d.text((x, y), label, font=font("mono", 12), fill=MUTED, anchor="lm")
    d.text((x, y + 22), value_text, font=font("monob", 24), fill=color, anchor="lm")


def naive_lane(d, y0, before, t, dp=2):
    lane_frame(d, y0, 200, RED, "NAIVE · premium-max on every task")
    mid = y0 + 120
    node(d, 150, mid, 116, 50, "workload", (59, 125, 216))
    flow(d, 210, 900, mid, t, RED, n=3)
    node(d, 986, mid, 150, 52, "premium-max", RED, sub="$5.20 / call")
    val = ease(min(1.0, t / 0.8)) * before
    counter(d, 70, y0 + 58, "spend", f"${val:.{dp}f}", RED)


def render_experiment(spec, outdir):
    os.makedirs(outdir, exist_ok=True)
    for fi in range(FRAMES):
        t = fi / FRAMES
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        header(d, spec["title_a"], spec["title_b"], spec["subtitle"], t)
        scoreboard(d, spec["before"], spec["after"], spec["delta"], spec["cov"],
                   dp=spec.get("dp", 2))
        spec["draw"](d, t, spec)
        d.text((W / 2, H - 20), spec["reproduce"], font=font("mono", 13), fill=MUTED, anchor="mm")
        img.save(os.path.join(outdir, f"f_{fi:03d}.png"))


def assemble_gif(outdir, gif_path):
    palette = os.path.join(outdir, "palette.png")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
         "-i", os.path.join(outdir, "f_%03d.png"),
         "-vf", "palettegen=stats_mode=full:max_colors=128", palette],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
         "-i", os.path.join(outdir, "f_%03d.png"), "-i", palette,
         "-lavfi", "paletteuse=dither=sierra2_4a:diff_mode=rectangle",
         "-loop", "0", gif_path],
        check=True,
    )


# ---- experiment lane drawers -------------------------------------------------

def _escalation_lane(d, t, spec, y0, label, accept_idx, honest=False):
    lane_frame(d, y0, 200, GREEN, label)
    mid = y0 + 118
    node(d, 118, mid, 96, 46, "tasks", (59, 125, 216))
    escalation(d, 210, 940, mid, accept_idx, t, honest=honest)
    val = ease(min(1.0, t / 0.8)) * spec["after"]
    counter(d, 70, y0 + 54, "spend", f"${val:.{spec.get('dp', 2)}f}",
            RED if honest else GREEN)


def draw_hero(d, t, spec):
    naive_lane(d, 168, spec["before"], t)
    _escalation_lane(d, t, spec, 392, "COST-AWARE · try cheap first, escalate on fail", 1)


def draw_curated(d, t, spec):
    naive_lane(d, 168, spec["before"], t, dp=3)
    _escalation_lane(d, t, spec, 392, "COST-AWARE · 5 hand-picked tasks, eyeball each", 1)


def draw_limits(d, t, spec):
    naive_lane(d, 168, spec["before"], t, dp=3)
    _escalation_lane(d, t, spec, 392,
                     "COST-AWARE · every task is genuinely hard", 4, honest=True)


def draw_ensemble(d, t, spec):
    naive_lane(d, 168, spec["before"], t, dp=3)
    lane_frame(d, 392, 200, GREEN, "ENSEMBLE · fan-out to all, keep best")
    mid = 392 + 118
    fanout(d, 150, 560, 980, mid, t, collapsed_frac=0.0)
    tax = ease(min(1.0, t / 0.8)) * 3.7
    meter(d, 70, 392 + 176, 300, tax / 4.0, AMBER, "fan-out tax", sub=f"{tax:3.1f}x")


def draw_adaptive(d, t, spec):
    naive_lane(d, 168, spec["before"], t, dp=3)
    lane_frame(d, 392, 200, GREEN, "ADAPTIVE · dial turns the fan-out OFF")
    mid = 392 + 118
    if t < 0.5:
        cf = 0.0
        tax = (t / 0.5) * 3.7
    else:
        cf = (t - 0.5) / 0.5
        tax = 3.7 * (1 - (t - 0.5) / 0.5)
    fanout(d, 150, 560, 980, mid, t, collapsed_frac=cf)
    on = t < 0.5
    pill(d, 640, 392 + 168, "compare_min_value  " + ("LOW -> fan-out ON" if on
         else "HIGH -> fan-out OFF"), INK, blend(BG, AMBER if on else GREEN, 0.2),
         font("monob", 12))
    meter(d, 70, 392 + 176, 300, tax / 4.0, AMBER if on else GREEN, "fan-out tax",
          sub=f"{tax:3.1f}x")


def draw_model_router(d, t, spec):
    lane_frame(d, 168, 200, AMBER, "SINGLE-CALL · pick one tier up front (Foundry model-router)")
    single_call(d, 150, 470, 900, 168 + 108, t, tier_idx=2, cov_target=52.0, cov_color=AMBER)
    lane_frame(d, 392, 200, GREEN, "ESCALATE · observe, raise only when a cheap tier fails")
    mid = 392 + 112
    node(d, 118, mid, 96, 44, "prompt", (59, 125, 216))
    escalation(d, 210, 940, mid, 1, t)
    cov = ease(min(1.0, t / 0.8)) * 100.0
    meter(d, 100, 392 + 170, 320, cov / 100.0, GREEN, "coverage", sub=f"{cov:4.0f}%")


SPECS = {
    "hero": {
        "title_a": "Hero —", "title_b": "same coverage, lower cost",
        "subtitle": "100 synthetic tasks · premium-on-everything vs try-cheap-first",
        "before": 2.2269, "after": 1.6592, "delta": "-25.5%", "cov": "· 100% coverage",
        "reproduce": "cost-router experiment run hero", "draw": draw_hero,
    },
    "curated": {
        "title_a": "Curated —", "title_b": "eyeball five tasks",
        "subtitle": "5 hand-labelled tasks · read every routing decision end to end",
        "before": 0.1271, "after": 0.0550, "delta": "-56.7%", "cov": "· 100% coverage",
        "dp": 3, "reproduce": "cost-router experiment run curated", "draw": draw_curated,
    },
    "ensemble": {
        "title_a": "Ensemble —", "title_b": "best-of-N, real cost",
        "subtitle": "6 high-value tasks · fan-out to all candidates, keep the best",
        "before": 0.2507, "after": 0.1328, "delta": "-47.0%", "cov": "· tax 3.7x",
        "dp": 3, "reproduce": "cost-router experiment run ensemble", "draw": draw_ensemble,
    },
    "adaptive": {
        "title_a": "Adaptive —", "title_b": "tax to zero",
        "subtitle": "same workload · a dial drops the fan-out tax, savings unchanged",
        "before": 0.2507, "after": 0.1328, "delta": "-47.0%", "cov": "· tax 3.7x -> 0.00x",
        "dp": 3, "reproduce": "cost-router experiment run adaptive", "draw": draw_adaptive,
    },
    "limits": {
        "title_a": "Limits —", "title_b": "no free lunch",
        "subtitle": "every task is genuinely hard · routing spends honestly, saves 0%",
        "before": 0.2368, "after": 0.2368, "delta": "0.0%", "cov": "· 100% coverage",
        "dp": 3, "reproduce": "cost-router experiment run limits", "draw": draw_limits,
    },
    "model-router": {
        "title_a": "Model Router —", "title_b": "pick once vs raise",
        "subtitle": "single-call tier pick (52%) vs escalation (100%) at the same cost band",
        "before": 2.2269, "after": 1.6592, "delta": "+48%p coverage", "cov": "· same cost",
        "reproduce": "cost-router experiment run model-router", "draw": draw_model_router,
    },
}


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assets = os.path.join(root, "docs", "assets", "gif")
    os.makedirs(assets, exist_ok=True)
    work = os.environ.get("GIF_WORK", "/tmp/gifout")
    for name, spec in SPECS.items():
        outdir = os.path.join(work, name)
        render_experiment(spec, outdir)
        gif = os.path.join(assets, f"{name}.gif")
        assemble_gif(outdir, gif)
        size = os.path.getsize(gif)
        print(f"  {name:14s} -> {gif}  ({size // 1024} KB)")


if __name__ == "__main__":
    main()
