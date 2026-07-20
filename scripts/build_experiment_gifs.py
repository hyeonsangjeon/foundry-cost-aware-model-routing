#!/usr/bin/env python3
"""Generate one animated explainer GIF per experiment.

Each experiment gets a *distinct* visual metaphor so they never look alike:

  hero          a live 100-task histogram stacking across the five tiers
  curated       five readable rows, each routed to its real cheapest-passing model
  ensemble      a fan-out to every candidate -> compare -> winners, with the tax meter
  adaptive      a rotating dial that collapses the fan-out and drains the tax to zero
  limits        the honest wall: the cheap arm fails at 0% coverage, equal spend bars
  model-router  two coverage gauges, single-call (52%) vs observe-and-escalate (100%)

Every number is the offline projection (labels.measured=false) and is taken from
`cost-router experiment run <name> --json/--ledger`. Frames are drawn with Pillow
and assembled into an optimised looping GIF with ffmpeg (palettegen/paletteuse).
"""

from __future__ import annotations

import math
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
BLUE = (59, 125, 216)
RED = (229, 72, 77)
GREEN = (46, 204, 113)
AMBER = (240, 160, 32)

TIERS = [
    ("mini-fast", (200, 146, 43)),
    ("swift-coder", (46, 139, 87)),
    ("balanced-pro", (59, 125, 216)),
    ("deep-reasoner", (123, 82, 201)),
    ("premium-max", (192, 57, 43)),
]
TIER_COLOR = {name: col for name, col in TIERS}

# ---- offline projection data (from `experiment run <name> --json/--ledger`) ----
HERO_HIST = [19, 14, 34, 26, 7]  # tasks resolved per tier (sums to 100)
CURATED_ROWS = [
    ("generate", "mini-fast", 0.000487, "clean-first"),
    ("repo_patch", "balanced-pro", 0.032793, "tie-broken"),
    ("plan", "balanced-pro", 0.014663, "escalated"),
    ("validate", "mini-fast", 0.000215, "clean-first"),
    ("test", "balanced-pro", 0.006880, "escalated"),
]
ENSEMBLE_WINNERS = [("swift-coder", 2), ("balanced-pro", 3), ("deep-reasoner", 1)]

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
    d.rounded_rectangle(box, radius=10, fill=blend(BG, accent, 0.16 if glow else 0.10),
                        outline=accent, width=2)
    if sub:
        d.text((cx, cy - 9), label, font=font("monob", 15), fill=INK, anchor="mm")
        d.text((cx, cy + 11), sub, font=font("mono", 12), fill=blend(INK, accent, 0.6), anchor="mm")
    else:
        d.text((cx, cy), label, font=font("monob", 15), fill=INK, anchor="mm")


def flow(d: ImageDraw.ImageDraw, x0: float, x1: float, y: float, t: float,
         color: tuple, n: int = 3) -> None:
    d.line([x0, y, x1, y], fill=blend(BG, INK, 0.28), width=3)
    for i in range(n):
        frac = ((i / n) + t) % 1.0
        glow_dot(d, x0 + frac * (x1 - x0), y, 5, color)


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
    d.rounded_rectangle([x, y, x + w, y + 12], radius=6, fill=FAINT)
    fw = max(0.0, min(1.0, frac)) * w
    if fw > 4:
        d.rounded_rectangle([x, y, x + fw, y + 12], radius=6, fill=color)
    d.text((x, y - 8), label, font=font("mono", 12), fill=MUTED, anchor="lb")
    if sub:
        d.text((x + w, y - 8), sub, font=font("monob", 12), fill=color, anchor="rb")


def panel(d: ImageDraw.ImageDraw, x0, y0, x1, y1, accent: tuple, label: str) -> None:
    d.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=blend(BG, accent, 0.06),
                        outline=blend(BG, accent, 0.4), width=1)
    pill(d, x0 + 20, y0 + 14, label, blend(INK, accent, 0.7), blend(BG, accent, 0.20),
         font("monob", 13))


def arc_gauge(d: ImageDraw.ImageDraw, cx, cy, r, frac, color, center, sub) -> None:
    box = [cx - r, cy - r, cx + r, cy + r]
    d.arc(box, 0, 360, fill=FAINT, width=18)
    if frac > 0.001:
        d.arc(box, -90, -90 + 360 * frac, fill=color, width=18)
    d.text((cx, cy - 6), center, font=font("monob", 34), fill=color, anchor="mm")
    d.text((cx, cy + 26), sub, font=font("mono", 13), fill=MUTED, anchor="mm")


def knob(d: ImageDraw.ImageDraw, cx, cy, r, prog, accent) -> None:
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=blend(BG, accent, 0.12),
              outline=blend(BG, accent, 0.5), width=3)
    d.ellipse([cx - r + 14, cy - r + 14, cx + r - 14, cy + r - 14],
              fill=blend(BG, accent, 0.18), outline=accent, width=2)
    ang = math.radians(-150 + 120 * prog)
    ex, ey = cx + (r - 22) * math.cos(ang), cy + (r - 22) * math.sin(ang)
    d.line([cx, cy, ex, ey], fill=accent, width=6)
    glow_dot(d, ex, ey, 6, accent)
    for lab, a, on in (("ON", -150, prog < 0.5), ("OFF", -30, prog >= 0.5)):
        rr = math.radians(a)
        tx, ty = cx + (r + 18) * math.cos(rr), cy + (r + 18) * math.sin(rr)
        d.text((tx, ty), lab, font=font("monob", 13),
               fill=accent if on else MUTED, anchor="mm")


def header(d, spec, t) -> None:
    ta, tb = spec["title_a"], spec["title_b"]
    d.text((48, 40), ta, font=font("sansb", 32), fill=INK, anchor="lm")
    wa = font("sansb", 32).getlength(ta + " ")
    d.text((48 + wa, 40), tb, font=font("sansb", 32), fill=(90, 160, 246), anchor="lm")
    d.text((48, 82), spec["subtitle"], font=font("mono", 15), fill=MUTED, anchor="lm")
    pill(d, 48, 104, "offline · labels.measured=false", blend(INK, AMBER, 0.5),
         blend(BG, AMBER, 0.14), font("mono", 12))
    scoreboard(d, spec)
    d.line([40, 138, W - 40, 138], fill=FAINT, width=1)
    d.rounded_rectangle([40, 137, 40 + (W - 80) * t, 140], radius=2, fill=blend(BG, INK, 0.4))


def scoreboard(d, spec) -> None:
    a, b, ac, bc = spec["score"]
    fb = font("monob", 26)
    segs = [(a, fb, ac), ("  ->  ", font("mono", 22), MUTED), (b, fb, bc)]
    draw_segments(d, W - 40 - seg_width(segs), 52, segs)
    d.text((W - 40, 92), spec["score_note"], font=font("monob", 15), fill=AMBER, anchor="rm")


def counter(d, x, y, label, value_text, color) -> None:
    d.text((x, y), label, font=font("mono", 12), fill=MUTED, anchor="lm")
    d.text((x, y + 22), value_text, font=font("monob", 24), fill=color, anchor="lm")


# ---- per-experiment scenes ---------------------------------------------------

def draw_hero(d, t, spec):
    panel(d, 40, 160, W - 40, 600, GREEN, "ROUTED · where the 100 tasks actually land")
    base = 560
    max_h, max_c = 300, max(HERO_HIST)
    centers = [round(300 + i * (980 - 300) / 4) for i in range(5)]
    d.text((70, 214), "naive puts all 100 on premium-max ($2.23).  routing spreads them —",
           font=font("mono", 13), fill=MUTED, anchor="lm")
    d.text((70, 234), "only 7 reach premium-max, 33 clear on a cheap tier.",
           font=font("mono", 13), fill=MUTED, anchor="lm")
    for i, (name, col) in enumerate(TIERS):
        cx = centers[i]
        grow = ease(min(1.0, (t - 0.05 * i) / 0.6))
        h = (HERO_HIST[i] / max_c) * max_h * grow
        d.rounded_rectangle([cx - 58, base - h, cx + 58, base], radius=8,
                            fill=blend(BG, col, 0.55), outline=col, width=2)
        shown = round(HERO_HIST[i] * grow)
        d.text((cx, base - h - 16), str(shown), font=font("monob", 20), fill=col, anchor="mm")
        d.text((cx, base + 18), name, font=font("mono", 12), fill=INK, anchor="mm")
    d.line([292, base, 988, base], fill=blend(BG, INK, 0.3), width=2)
    for k in range(4):
        frac = ((k / 4) + t) % 1.0
        col = centers[k % 5]
        glow_dot(d, col, 250 + frac * 60, 4, TIERS[k % 5][1])


def draw_curated(d, t, spec):
    panel(d, 40, 160, W - 40, 600, GREEN,
          "ROUTED · each task -> its cheapest passing model (exact offline projection)")
    rows_y = [230, 300, 370, 440, 510]
    reason_col = {"clean-first": GREEN, "escalated": AMBER, "tie-broken": BLUE}
    for i, (cls, model, cost, reason) in enumerate(CURATED_ROWS):
        y = rows_y[i]
        prog = ease(min(1.0, (t - 0.06 * i) / 0.55))
        d.rounded_rectangle([70, y - 22, 250, y + 22], radius=9, fill=blend(BG, BLUE, 0.10),
                            outline=blend(BG, BLUE, 0.5), width=1)
        d.text((160, y), cls, font=font("monob", 14), fill=INK, anchor="mm")
        d.line([250, y, 700, y], fill=blend(BG, INK, 0.2), width=2)
        col = TIER_COLOR[model]
        landed = prog >= 0.999
        dot_x = 262 + (688 - 262) * prog
        glow_dot(d, dot_x, y, 5, col)
        mbox = [730, y - 20, 900, y + 20]
        d.rounded_rectangle(mbox, radius=9,
                            fill=blend(BG, col, 0.16 if landed else 0.05),
                            outline=col if landed else blend(BG, col, 0.4),
                            width=2 if landed else 1)
        d.text((815, y), model, font=font("monob", 13),
               fill=INK if landed else MUTED, anchor="mm")
        if landed:
            d.text((915, y), "OK", font=font("monob", 13), fill=GREEN, anchor="lm")
            d.text((970, y - 8), f"${cost:.6f}", font=font("mono", 12), fill=INK, anchor="lm")
            d.text((970, y + 10), reason, font=font("mono", 11),
                   fill=reason_col[reason], anchor="lm")


def _fan(d, x_app, x_cmp, y, t, active):
    ys = [y - 66, y - 33, y, y + 33, y + 66]
    x_out = x_app + 60
    x_in = x_cmp - 54
    x_cand = round(x_out + 0.46 * (x_in - x_out))
    for i in range(5):
        if not (i < active or i == 2):
            continue
        col = TIERS[i][1]
        line_col = blend(BG, col, 0.55)
        d.line([x_out, y, x_cand, ys[i]], fill=line_col, width=2)
        d.line([x_cand, ys[i], x_in, y], fill=line_col, width=2)
        for k in range(2):
            frac = ((k / 2) + t) % 1.0
            glow_dot(d, x_out + frac * (x_cand - x_out),
                     y + frac * (ys[i] - y), 4, col)
        glow_dot(d, x_cand, ys[i], 5, col)
    node(d, x_app, y, 108, 48, "workload", BLUE, sub="high-value")
    d.rounded_rectangle([x_cmp - 54, y - 26, x_cmp + 54, y + 26], radius=10,
                        fill=blend(BG, AMBER, 0.14), outline=AMBER, width=2)
    d.text((x_cmp, y - 6), "compare", font=font("monob", 14), fill=INK, anchor="mm")
    d.text((x_cmp, y + 11), "keep best", font=font("mono", 11), fill=blend(INK, AMBER, 0.6),
           anchor="mm")


def draw_ensemble(d, t, spec):
    panel(d, 40, 160, W - 40, 600, GREEN, "ENSEMBLE · run all five, pay for all, keep the best")
    y = 350
    _fan(d, 150, 560, y, t, 5)
    flow(d, 614, 840, y, t, GREEN, n=2)
    node(d, 928, y, 150, 52, "best-of-N", GREEN, sub="cheapest passing", glow=True)
    lx = 150
    d.text((lx, 470), "winners kept:", font=font("mono", 13), fill=MUTED, anchor="lm")
    x = lx + 130
    for name, cnt in ENSEMBLE_WINNERS:
        x = pill(d, x, 458, f"{cnt}x {name}", INK, blend(BG, TIER_COLOR[name], 0.28),
                 font("monob", 12)) + 10
    tax = ease(min(1.0, t / 0.8)) * 3.74
    meter(d, 150, 545, 360, tax / 4.0, AMBER, "fan-out tax (all calls / winners)",
          sub=f"{tax:3.2f}x")
    d.text((540, 540), "winners $0.133  ·  all calls $0.497", font=font("mono", 12),
           fill=MUTED, anchor="lm")


def draw_adaptive(d, t, spec):
    panel(d, 40, 160, W - 40, 600, GREEN, "ADAPTIVE · one dial trades the fan-out tax away")
    on = t < 0.5
    prog = min(1.0, max(0.0, (t - 0.5) / 0.5)) if not on else 0.0
    dial_prog = ease(min(1.0, t / 0.9))
    accent = AMBER if on else GREEN
    d.text((250, 210), "compare_min_value", font=font("monob", 15), fill=INK, anchor="mm")
    knob(d, 250, 380, 92, dial_prog, accent)
    d.text((250, 495), "LOW · fan-out ON" if on else "HIGH · fan-out OFF",
           font=font("monob", 14), fill=accent, anchor="mm")
    active = 5 if on else 1
    _fan(d, 470, 800, 360, t, active)
    node(d, 968, 360, 128, 50, "swift-coder", GREEN, sub="same winner", glow=True)
    flow(d, 854, 904, 360, t, GREEN, n=2)
    tax = 3.74 * (1 - prog) if not on else 3.74 * (t / 0.5)
    meter(d, 470, 540, 360, tax / 4.0, accent, "fan-out tax", sub=f"{tax:3.2f}x")
    d.text((850, 535), "savings -47% unchanged", font=font("monob", 13), fill=GREEN, anchor="lm")


def draw_limits(d, t, spec):
    panel(d, 40, 160, W - 40, 380, RED, "CHEAP ARM · every cheap model fails the checks")
    yy = 300
    for i, name in enumerate(("mini-fast", "swift-coder")):
        cx = 180 + i * 210
        col = TIER_COLOR[name]
        d.rounded_rectangle([cx - 80, yy - 26, cx + 80, yy + 26], radius=10,
                            fill=blend(BG, RED, 0.10), outline=blend(BG, col, 0.5), width=2)
        d.text((cx, yy - 6), name, font=font("monob", 14), fill=INK, anchor="mm")
        d.text((cx, yy + 12), "FAIL", font=font("monob", 12), fill=RED, anchor="mm")
    pill(d, 470, yy - 16, "coverage 0%  ·  cheap-only spend $0.020 buys nothing",
         blend(INK, RED, 0.5), blend(BG, RED, 0.16), font("monob", 13))
    d.text((470, yy + 24), "the work truly needs the top model per task",
           font=font("mono", 13), fill=MUTED, anchor="lm")
    panel(d, 40, 396, W - 40, 600, GREEN, "SO ROUTING == NAIVE · no free lunch")
    prog = ease(min(1.0, t / 0.8))
    for i, (lab, col) in enumerate((("naive · top model per task", RED),
                                    ("routed · cost-aware", GREEN))):
        by = 470 + i * 60
        d.text((70, by), lab, font=font("mono", 13), fill=MUTED, anchor="lm")
        d.rounded_rectangle([360, by - 12, 360 + 560 * prog, by + 12], radius=6,
                            fill=blend(BG, col, 0.7))
        d.text((930, by), "$0.2368", font=font("monob", 14), fill=INK, anchor="lm")
    d.text((360, 560), "identical spend  ->  savings 0.0%", font=font("monob", 14),
           fill=AMBER, anchor="lm")


def draw_model_router(d, t, spec):
    panel(d, 40, 160, W - 40, 600, BLUE, "COVERAGE · one pick vs observe-and-escalate")
    prog = ease(min(1.0, t / 0.8))
    arc_gauge(d, 320, 400, 108, prog * 0.52, AMBER, f"{prog * 52:.0f}%", "single-call")
    arc_gauge(d, 800, 400, 108, prog * 1.00, GREEN, f"{prog * 100:.0f}%", "escalate")
    d.text((320, 250), "pick one tier up front", font=font("monob", 14), fill=INK, anchor="mm")
    d.text((320, 272), "(Foundry model-router)", font=font("mono", 12), fill=MUTED, anchor="mm")
    d.text((320, 540), "$1.59 · commits before any check", font=font("mono", 13),
           fill=MUTED, anchor="mm")
    d.text((800, 250), "observe, raise only on fail", font=font("monob", 14), fill=INK, anchor="mm")
    d.text((800, 272), "(this repo's mix)", font=font("mono", 12), fill=MUTED, anchor="mm")
    d.text((800, 540), "$1.66 · reclaims full coverage", font=font("mono", 13),
           fill=MUTED, anchor="mm")
    d.text((560, 380), "+48", font=font("monob", 30), fill=GREEN, anchor="mm")
    d.text((560, 410), "points", font=font("mono", 12), fill=MUTED, anchor="mm")
    d.text((560, 428), "for ~4% cost", font=font("mono", 11), fill=MUTED, anchor="mm")


SPECS = {
    "hero": {
        "title_a": "Hero —", "title_b": "same coverage, lower cost",
        "subtitle": "100 synthetic tasks · premium-on-everything vs try-cheap-first",
        "score": ("$2.23", "$1.66", RED, GREEN), "score_note": "-25.5% · 100% coverage",
        "reproduce": "cost-router experiment run hero", "draw": draw_hero,
    },
    "curated": {
        "title_a": "Curated —", "title_b": "five tasks you can read",
        "subtitle": "5 hand-labelled tasks · every routing decision, end to end",
        "score": ("$0.127", "$0.055", RED, GREEN), "score_note": "-56.7% · 100% coverage",
        "reproduce": "cost-router experiment run curated", "draw": draw_curated,
    },
    "ensemble": {
        "title_a": "Ensemble —", "title_b": "best-of-N, at a real cost",
        "subtitle": "6 high-value tasks · fan out to all candidates, keep the best",
        "score": ("$0.251", "$0.133", RED, GREEN), "score_note": "-47% · tax 3.74x",
        "reproduce": "cost-router experiment run ensemble", "draw": draw_ensemble,
    },
    "adaptive": {
        "title_a": "Adaptive —", "title_b": "the fan-out dial, turned off",
        "subtitle": "same workload · a dial drops the tax to zero, savings unchanged",
        "score": ("3.74x", "0.00x", AMBER, GREEN), "score_note": "tax gone · -47% kept",
        "reproduce": "cost-router experiment run adaptive", "draw": draw_adaptive,
    },
    "limits": {
        "title_a": "Limits —", "title_b": "there is no free lunch",
        "subtitle": "genuinely hard tasks · only the top model passes · routing saves 0%",
        "score": ("$0.237", "$0.237", RED, RED), "score_note": "0.0% · 100% coverage",
        "reproduce": "cost-router experiment run limits", "draw": draw_limits,
    },
    "model-router": {
        "title_a": "Model Router —", "title_b": "pick once vs raise",
        "subtitle": "single-call tier pick vs observe-and-escalate, at one cost band",
        "score": ("52%", "100%", AMBER, GREEN), "score_note": "+48%p · ~4% more cost",
        "reproduce": "cost-router experiment run model-router", "draw": draw_model_router,
    },
}


def render_experiment(spec, outdir):
    os.makedirs(outdir, exist_ok=True)
    for fi in range(FRAMES):
        t = fi / FRAMES
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        header(d, spec, t)
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
        print(f"  {name:14s} -> {gif}  ({os.path.getsize(gif) // 1024} KB)")


if __name__ == "__main__":
    main()
