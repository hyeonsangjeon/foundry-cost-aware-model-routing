"""Self-contained offline dashboard for the routing service.

The page is a single inline HTML/CSS/JS string with no external assets, fonts,
or network calls other than same-origin fetches to this service's own JSON
endpoints (``/healthz``, ``/policy``, ``/replay``). It renders the policy table,
runs a replay over the bundled synthetic workload, animates the per-task routing
decisions, and aggregates the results into cost-by-class, model-usage, and
mode/reason statistics. All model names come from the policy data (generic
placeholders); nothing here is a measured result.
"""

from __future__ import annotations

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>cost-router · offline routing demo</title>
<style>
  :root {
    --bg: #eef2f6; --panel: #ffffff; --elev: #f5f8fa; --line: #dce3ea; --line2: #eaeff4;
    --ink: #17222d; --muted: #5c6b7a; --faint: #8a97a4;
    --brand: #0a6b3b; --brand2: #12874c; --brand-soft: #e7f4ec;
    --blue: #1d6fd6; --green: #1a7f4b; --amber: #b7791f; --red: #c23b3b;
    --purple: #6b4fbb; --cyan: #0e7490;
    --m0: #0e7490; --m1: #1d6fd6; --m2: #6b4fbb; --m3: #b7791f; --m4: #c23b3b;
    --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
    --shadow: 0 1px 2px rgba(16,24,32,.05), 0 6px 20px rgba(16,24,32,.06);
    --radius: 14px;
  }
  * { box-sizing: border-box; }
  html { -webkit-text-size-adjust: 100%; }
  body {
    margin: 0; background: var(--bg); color: var(--ink);
    font-family: var(--sans); font-size: 14px; line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }
  .mono, .num { font-family: var(--mono); font-variant-numeric: tabular-nums; }

  /* ---- header ---- */
  header.top {
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
    flex-wrap: wrap; padding: 18px 28px; background: var(--panel);
    border-bottom: 1px solid var(--line);
  }
  .brand { display: flex; align-items: center; gap: 12px; }
  .logo {
    width: 34px; height: 34px; border-radius: 9px; display: grid; place-items: center;
    background: var(--brand-soft); color: var(--brand); font-size: 17px; font-weight: 800;
    border: 1px solid #cfe6da;
  }
  h1 { font-size: 16px; margin: 0; font-weight: 700; letter-spacing: -.01em; }
  .brand .tag { font-size: 12px; color: var(--muted); margin-top: 1px; }
  .badges { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .badge {
    font-size: 11px; padding: 3px 9px; border-radius: 999px; font-weight: 500;
    border: 1px solid var(--line); color: var(--muted); background: var(--panel);
    white-space: nowrap;
  }
  .badge.ok { color: var(--green); border-color: #b7dfc6; background: #eefaf1; }
  .badge.measured { color: var(--amber); border-color: #ecd9ac; background: #fbf5e7; }

  main {
    max-width: 1080px; margin: 0 auto; padding: 26px 24px 48px;
    display: flex; flex-direction: column; gap: 20px;
  }
  .panel {
    background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
    padding: 22px 24px; box-shadow: var(--shadow);
  }
  .eyebrow {
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .09em;
    color: var(--brand); margin: 0 0 6px;
  }
  h2.sec { font-size: 17px; font-weight: 700; margin: 0 0 3px; letter-spacing: -.01em; }
  .sec-sub { font-size: 13px; color: var(--muted); margin: 0 0 16px; }

  /* ---- hero ---- */
  .hero .lead { font-size: 15.5px; margin: 0 0 18px; max-width: 60ch; }
  .hero .lead b { color: var(--brand); }
  .controls { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  .btn {
    background: var(--brand2); color: #fff; border: 0; border-radius: 9px;
    padding: 10px 18px; font: inherit; font-weight: 600; cursor: pointer;
    box-shadow: 0 1px 2px rgba(10,107,59,.25); transition: background .15s, transform .05s;
  }
  .btn:hover { background: #0f7a44; }
  .btn:active { transform: translateY(1px); }
  .btn:disabled { opacity: .55; cursor: default; box-shadow: none; }
  label.toggle { color: var(--muted); display: flex; gap: 7px; align-items: center; cursor: pointer; font-size: 13px; }
  label.toggle input { accent-color: var(--brand2); }

  .headline { margin: 20px 0 4px; display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  .hnum { font-family: var(--mono); font-size: 44px; font-weight: 700; color: var(--brand); line-height: 1; letter-spacing: -.02em; }
  .hunit { font-size: 15px; color: var(--muted); font-weight: 500; }
  .hsub { font-size: 13.5px; color: var(--ink); margin-top: 10px; max-width: 72ch; }
  .caveat { font-size: 12px; color: var(--muted); margin: 10px 0 0; font-style: italic; }

  /* ---- spotlight ---- */
  .spotlight .spot-meta { font-family: var(--mono); font-size: 12px; color: var(--muted); font-weight: 500; letter-spacing: 0; }
  .spot-grid { display: grid; grid-template-columns: 1fr auto 1fr; gap: 14px; align-items: stretch; margin: 6px 0 2px; }
  .spot-arm { border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; background: var(--elev); }
  .spot-arm.routed { border-color: #b7dfc6; background: #f1faf4; }
  .spot-arm.naive { border-color: #ecd2d2; background: #fbf1f1; }
  .spot-lbl { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; font-weight: 700; color: var(--muted); margin-bottom: 8px; }
  .spot-arm.routed .spot-lbl { color: var(--green); }
  .spot-arm.naive .spot-lbl { color: var(--red); }
  .spot-model { font-family: var(--mono); font-size: 15px; font-weight: 700; color: var(--ink); }
  .spot-cost { font-family: var(--mono); font-size: 22px; font-weight: 700; margin-top: 4px; letter-spacing: -.01em; }
  .spot-arm.routed .spot-cost { color: var(--brand); }
  .spot-arm.naive .spot-cost { color: var(--red); }
  .spot-vs { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; padding: 0 4px; }
  .spot-vs span { font-family: var(--mono); font-size: 26px; font-weight: 800; color: var(--ink); line-height: 1; }
  .spot-vs small { font-size: 11px; color: var(--muted); }
  @media (max-width: 640px) { .spot-grid { grid-template-columns: 1fr; } .spot-vs { flex-direction: row; gap: 8px; } }

  /* ---- strategy comparison ---- */
  .strats { display: flex; flex-direction: column; gap: 14px; }
  .strat {
    border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; background: var(--elev);
  }
  .strat.win { border-color: #b7dfc6; background: #f1faf4; box-shadow: 0 0 0 1px #cdebd9 inset; }
  .strat .lbl { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; margin-bottom: 9px; }
  .strat .name { font-size: 13.5px; color: var(--ink); }
  .strat .desc { color: var(--muted); font-size: 12.5px; }
  .stag { display: inline-block; font-weight: 700; padding: 2px 8px; border-radius: 6px; font-size: 11px; margin-right: 9px; font-family: var(--mono); }
  .stag.prem { background: rgba(194,59,59,.12); color: var(--red); }
  .stag.mini { background: rgba(183,121,31,.14); color: var(--amber); }
  .stag.mix  { background: rgba(26,127,75,.14); color: var(--green); }
  .strat .cost { font-family: var(--mono); font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .bar { height: 12px; background: #e6ebf0; border-radius: 999px; overflow: hidden; }
  .bar > span { display: block; height: 100%; width: 0; border-radius: 999px; transition: width .5s cubic-bezier(.4,0,.2,1); }
  .bar.prem > span { background: var(--red); }
  .bar.mini > span { background: var(--amber); }
  .bar.mix  > span { background: var(--green); }
  .covline { display: flex; align-items: center; gap: 10px; margin-top: 9px; }
  .covline small { color: var(--muted); font-size: 12px; }
  .covpill {
    font-size: 11px; padding: 2px 9px; border-radius: 999px; font-weight: 600;
    border: 1px solid var(--line); color: var(--muted); white-space: nowrap; font-family: var(--mono);
  }
  .covpill.ok { color: var(--green); border-color: #b7dfc6; background: #eefaf1; }
  .covpill.warn { color: var(--amber); border-color: #ecd9ac; background: #fbf5e7; font-weight: 700; }
  .win-flag { font-size: 11px; color: var(--brand); font-weight: 700; margin-left: 8px; }
  .takeaway {
    margin-top: 16px; padding: 13px 16px; font-size: 13.5px; line-height: 1.6;
    border-left: 3px solid var(--brand2); background: var(--brand-soft); border-radius: 8px; color: #124a2e;
  }

  /* ---- KPI strip ---- */
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }
  .kpi { background: var(--elev); border: 1px solid var(--line); border-radius: 11px; padding: 13px 15px; }
  .kpi .v { font-size: 22px; font-weight: 700; font-family: var(--mono); font-variant-numeric: tabular-nums; letter-spacing: -.01em; }
  .kpi .v.warn { color: var(--red); }
  .kpi .k { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-top: 2px; }
  .modes { display: flex; flex-wrap: wrap; gap: 10px 22px; margin-top: 16px; padding-top: 15px; border-top: 1px solid var(--line2); }
  .mode-explain { font-size: 12.5px; color: var(--muted); max-width: 44ch; }
  .mode-explain b { color: var(--ink); font-family: var(--mono); font-size: 12px; }
  .covnote {
    display: none; margin-top: 14px; padding: 10px 14px; font-size: 12.5px;
    color: #8a5a12; border: 1px solid #ecd9ac; border-radius: 9px; background: #fbf5e7;
  }
  .covnote.show { display: block; }

  /* ---- progressive disclosure ---- */
  details.disc { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; }
  details.disc > summary {
    list-style: none; cursor: pointer; padding: 16px 22px; font-weight: 600; font-size: 14px;
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
  }
  details.disc > summary::-webkit-details-marker { display: none; }
  details.disc > summary .chev { color: var(--faint); font-size: 12px; transition: transform .2s; }
  details.disc[open] > summary .chev { transform: rotate(90deg); }
  details.disc > summary .sumsub { color: var(--muted); font-weight: 400; font-size: 12.5px; margin-left: auto; margin-right: 8px; }
  .disc-body { padding: 4px 22px 22px; }

  .cards { display: grid; grid-template-columns: 1fr; gap: 16px; }
  @media (min-width: 720px) { .cards { grid-template-columns: 1fr 1fr; } }
  .card { background: var(--elev); border: 1px solid var(--line); border-radius: 11px; padding: 16px; }
  .card h3 { margin: 0 0 12px; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 700; }
  .aggrow { margin: 10px 0; }
  .aggrow-h { display: flex; justify-content: space-between; gap: 10px; font-size: 12.5px; margin-bottom: 4px; }
  .aggrow-f { font-size: 11.5px; color: var(--muted); margin-top: 3px; font-family: var(--mono); }
  .track { height: 13px; background: #e6ebf0; border: 1px solid var(--line); border-radius: 999px; overflow: hidden; }
  .track.full { width: 100%; }
  .track > span { display: block; height: 100%; width: 0; border-radius: 999px; transition: width .5s cubic-bezier(.4,0,.2,1); }
  .fill-routed { background: var(--green); }
  .m0 { background: var(--m0); } .m1 { background: var(--m1); }
  .m2 { background: var(--m2); } .m3 { background: var(--m3); } .m4 { background: var(--m4); }
  .mdot::before { content: "●"; margin-right: 7px; font-size: 10px; vertical-align: 1px; }
  .mdot.m0::before { color: var(--m0); } .mdot.m1::before { color: var(--m1); }
  .mdot.m2::before { color: var(--m2); } .mdot.m3::before { color: var(--m3); } .mdot.m4::before { color: var(--m4); }
  .mdot { color: var(--ink); background: none !important; font-family: var(--mono); font-size: 12.5px; }
  .usage-split { margin-top: 14px; font-size: 12.5px; color: var(--muted); line-height: 1.6; padding-top: 12px; border-top: 1px solid var(--line2); }
  .usage-split b { color: var(--ink); }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 7px 11px; font-size: 12.5px; font-family: var(--mono); }
  .chip b { color: var(--ink); } .chip small { color: var(--muted); }

  table { width: 100%; border-collapse: collapse; font-family: var(--mono); }
  th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--line2); white-space: nowrap; font-size: 12.5px; }
  th { color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; font-family: var(--sans); position: sticky; top: 0; background: var(--panel); }
  .tracewrap { max-height: 460px; overflow: auto; border: 1px solid var(--line); border-radius: 11px; }
  .pill { font-size: 11px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--line); font-family: var(--sans); }
  .reason-clean-first { color: var(--green); border-color: #b7dfc6; background: #eefaf1; }
  .reason-escalated { color: var(--amber); border-color: #ecd9ac; background: #fbf5e7; }
  .reason-compared, .reason-tie-broken { color: var(--purple); border-color: #d3c8ee; background: #f2eefb; }
  .mode-compare { color: var(--purple); font-weight: 600; }
  .mode-ordered { color: var(--muted); }
  tbody tr { animation: fade .25s ease; }
  tbody tr:hover td { background: var(--elev); }
  @keyframes fade { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; } }

  .legend { display: grid; grid-template-columns: 1fr; gap: 8px; }
  .legend .li { font-size: 12.5px; }
  .legend .term { color: var(--brand); font-weight: 700; font-family: var(--mono); }
  .legend .li small { color: var(--muted); }

  .cls { color: var(--brand); font-weight: 700; margin: 14px 0 5px; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; font-family: var(--mono); }
  .cls:first-child { margin-top: 0; }
  .polrow { display: flex; justify-content: space-between; gap: 10px; padding: 4px 0; border-bottom: 1px dashed var(--line); font-family: var(--mono); font-size: 12.5px; }
  .polrow:last-child { border-bottom: 0; }
  .tiertag { font-size: 10px; padding: 1px 7px; border-radius: 999px; border: 1px solid var(--line); margin-left: 7px; white-space: nowrap; font-family: var(--sans); }
  .t0 { color: var(--m0); border-color: #a9d7e0; } .t1 { color: var(--m1); border-color: #b7d2f4; }
  .t2 { color: var(--m2); border-color: #d3c8ee; } .t3 { color: var(--m3); border-color: #ecd9ac; }
  .t4 { color: var(--m4); border-color: #ecc0c0; }
  .catrow { padding: 10px 0; border-bottom: 1px dashed var(--line); }
  .catrow:last-child { border-bottom: 0; }
  .catrow .h { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .catrow .name { font-weight: 600; font-family: var(--mono); font-size: 13px; }
  .catrow .role { color: var(--ink); font-size: 12.5px; margin-top: 4px; }
  .catrow .rw { font-size: 11.5px; color: var(--muted); margin-top: 2px; }

  .foot { color: var(--muted); font-size: 11.5px; margin-top: 12px; line-height: 1.6; }
  .foot.end { text-align: center; margin-top: 4px; }
  .grid2 { display: grid; grid-template-columns: 1fr; gap: 18px; }
  @media (min-width: 760px) { .grid2 { grid-template-columns: 1fr 1fr; } }
</style>
</head>
<body>
<header class="top">
  <div class="brand">
    <div class="logo">&#9671;</div>
    <div>
      <h1>cost-router</h1>
      <div class="tag">Cost-aware model routing over Microsoft Foundry &middot; offline demo</div>
    </div>
  </div>
  <div class="badges">
    <span id="health" class="badge">checking&#8230;</span>
    <span id="polver" class="badge">policy &mdash;</span>
    <span class="badge measured">offline projection &middot; labels.measured=false</span>
  </div>
</header>
<main>

  <section class="panel hero">
    <div class="eyebrow">The question</div>
    <p class="lead">Can we cut inference cost <b>without losing coverage</b>? Route cheap-first &mdash;
      try the cheapest capable model, and escalate to a stronger one only when the cheap one fails.</p>
    <div class="controls">
      <button id="run" class="btn">&#9654;&nbsp; Run replay</button>
      <label class="toggle"><input type="checkbox" id="synth" checked /> full synthetic workload (100 tasks)</label>
      <span id="progress" class="badge">idle</span>
    </div>
    <div class="headline">
      <span class="hnum" id="savedPct">0.0%</span>
      <span class="hunit">lower cost</span>
    </div>
    <div class="hsub" id="savedAbs">&mdash; run a replay to project savings against an all-premium baseline.</div>
    <p class="caveat" id="mixCaveat">Savings depend on workload mix and placeholder pricing &mdash; this is one synthetic run, not a guaranteed number.</p>
  </section>

  <section class="panel spotlight" id="spotlightPanel" hidden>
    <div class="eyebrow">The one task that makes it obvious</div>
    <h2 class="sec">Spotlight <span class="spot-meta" id="spotMeta">&mdash;</span></h2>
    <p class="sec-sub">The single task where cheap-first routing beat the all-premium arm by the widest margin &mdash;
      same task, same checks, one picked the cheapest model that passed.</p>
    <div class="spot-grid">
      <div class="spot-arm routed">
        <div class="spot-lbl">routed &middot; cost-aware</div>
        <div class="spot-model" id="spotRoutedModel">&mdash;</div>
        <div class="spot-cost" id="spotRoutedCost">&mdash;</div>
      </div>
      <div class="spot-vs"><span id="spotRatio">&mdash;</span><small>cheaper</small></div>
      <div class="spot-arm naive">
        <div class="spot-lbl">naive &middot; premium on every task</div>
        <div class="spot-model" id="spotNaiveModel">&mdash;</div>
        <div class="spot-cost" id="spotNaiveCost">&mdash;</div>
      </div>
    </div>
    <p class="caveat">One synthetic task, placeholder pricing &mdash; an offline projection, not a measured saving.</p>
  </section>

  <section class="panel">
    <h2 class="sec">Three strategies, one workload</h2>
    <p class="sec-sub">Each single-tier strategy fails on one axis. Only the cost-aware mix wins on both cost and coverage.</p>
    <div class="strats" id="strats">
      <div class="strat">
        <div class="lbl">
          <span class="name"><span class="stag mini">all-mini</span><span class="desc">cheapest tier on every task</span></span>
          <b class="cost" id="miniVal">&mdash;</b>
        </div>
        <div class="bar mini"><span id="miniBar"></span></div>
        <div class="covline"><span class="covpill" id="miniCov">coverage &mdash;</span><small>cheapest &mdash; but the cheap tier fails the hard tasks</small></div>
      </div>
      <div class="strat">
        <div class="lbl">
          <span class="name"><span class="stag prem">all-premium</span><span class="desc">premium model on every task</span></span>
          <b class="cost" id="premVal">&mdash;</b>
        </div>
        <div class="bar prem"><span id="premBar"></span></div>
        <div class="covline"><span class="covpill" id="premCov">coverage &mdash;</span><small>holds coverage &mdash; but the most expensive</small></div>
      </div>
      <div class="strat win">
        <div class="lbl">
          <span class="name"><span class="stag mix">cost-aware mix</span><span class="desc">cheap-first, escalate only the hard tasks</span><span class="win-flag">&#10003; recommended</span></span>
          <b class="cost" id="afterVal">&mdash;</b>
        </div>
        <div class="bar mix"><span id="afterBar"></span></div>
        <div class="covline"><span class="covpill" id="mixCov">coverage &mdash;</span><small>the only both-win: full coverage below premium cost</small></div>
      </div>
    </div>
    <div class="takeaway" id="takeaway">Run a replay to compare all-mini vs all-premium vs the cost-aware mix &mdash; each single-tier strategy fails on one axis; only the mix keeps full coverage below premium cost.</div>
  </section>

  <section class="panel">
    <h2 class="sec">At a glance</h2>
    <p class="sec-sub">Headline numbers for this run.</p>
    <div class="kpis" id="kpis">
      <div class="kpi"><div class="v" id="kTasks">&mdash;</div><div class="k">tasks</div></div>
      <div class="kpi"><div class="v" id="kCov">&mdash;</div><div class="k">coverage</div></div>
      <div class="kpi"><div class="v" id="kSingle">&mdash;</div><div class="k">single-route</div></div>
      <div class="kpi"><div class="v" id="kEnsemble">&mdash;</div><div class="k">ensemble</div></div>
      <div class="kpi"><div class="v" id="kAvg">&mdash;</div><div class="k">avg $/task</div></div>
    </div>
    <div class="covnote" id="covNote"></div>
    <div class="modes">
      <div class="mode-explain"><b>single-route</b> &mdash; try candidates cheapest-first and take the first one that passes.</div>
      <div class="mode-explain"><b>ensemble</b> &mdash; evaluate several models and keep the best; reserved for higher-value tasks.</div>
    </div>
  </section>

  <details class="disc" open>
    <summary><span class="chev">&#9656;</span> Breakdown <span class="sumsub">cost by class &middot; model usage &middot; routing modes</span></summary>
    <div class="disc-body">
      <div class="cards">
        <div class="card">
          <h3>Cost by task class &mdash; routed vs naive</h3>
          <div id="byClass"><small style="color:var(--muted)">run a replay&#8230;</small></div>
        </div>
        <div class="card">
          <h3>Model usage &mdash; tasks &amp; routed cost</h3>
          <div id="byModel"><small style="color:var(--muted)">run a replay&#8230;</small></div>
          <div class="usage-split" id="usageSplit"></div>
        </div>
        <div class="card">
          <h3>Routing mode</h3>
          <div class="chips" id="byMode"><small style="color:var(--muted)">run a replay&#8230;</small></div>
          <h3 style="margin-top:16px">Reason</h3>
          <div class="chips" id="byReason"><small style="color:var(--muted)">run a replay&#8230;</small></div>
        </div>
        <div class="card">
          <h3>What each column means</h3>
          <div class="legend">
            <div class="li"><span class="term">task</span> &mdash; synthetic task id.</div>
            <div class="li"><span class="term">class</span> &mdash; task type: plan &middot; generate &middot; test &middot; validate &middot; repo_patch.</div>
            <div class="li"><span class="term">mode</span> &mdash; <small><b>ordered</b> = cheapest-first, take the first clean one &middot; <b>compare</b> = ensemble, keep the best.</small></div>
            <div class="li"><span class="term">chosen</span> &mdash; placeholder model that handled the task.</div>
            <div class="li"><span class="term">reason</span> &mdash; <small><b>clean-first</b> top pick passed &middot; <b>escalated</b> cheaper failed, moved up &middot; <b>compared</b> ensemble winner &middot; <b>tie-broken</b> settled by cost.</small></div>
            <div class="li"><span class="term">cost</span> &mdash; <small>projected USD for this task (offline, not measured).</small></div>
          </div>
        </div>
      </div>
    </div>
  </details>

  <details class="disc">
    <summary><span class="chev">&#9656;</span> Per-task routing trace <span class="sumsub">every task, streamed live</span></summary>
    <div class="disc-body">
      <div class="tracewrap">
        <table>
          <thead><tr><th>task</th><th>class</th><th>mode</th><th>chosen</th><th>reason</th><th>cost</th></tr></thead>
          <tbody id="traceBody"></tbody>
        </table>
      </div>
    </div>
  </details>

  <details class="disc" id="policyDetails" open>
    <summary><span class="chev">&#9656;</span> Policy &amp; model tiers <span class="sumsub">class &#8594; candidates, cheapest first</span></summary>
    <div class="disc-body">
      <div class="grid2">
        <div>
          <div id="policy">loading&#8230;</div>
        </div>
        <div>
          <h3 style="margin:0 0 12px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:700">Model tiers &mdash; what these names mean</h3>
          <div id="catalog"><small style="color:var(--muted)">loading&#8230;</small></div>
        </div>
      </div>
      <div class="foot">Generic placeholder tiers &mdash; not real product names. They stand in for a
        lightweight/high-volume model, an efficient coder, a balanced general model, a deliberate
        reasoner, and a premium frontier model.</div>
    </div>
  </details>

  <div class="foot end">Numbers are an offline projection over synthetic data &mdash; not measured. Model names are generic placeholders.</div>
</main>
<script>
const $ = (id) => document.getElementById(id);
// Endpoint map — defaults hit this service's live JSON routes. A static export
// (e.g. Vercel) injects window.__ENDPOINTS__ to point at pre-rendered files.
const EP = (typeof window !== "undefined" && window.__ENDPOINTS__) || {
  health: "/healthz",
  policy: "/policy",
  replay: (synth) => "/replay?synth=" + synth,
};
// Display rounding (P1): totals at 2 decimals; sub-cent values keep up to 4 so
// tiny per-task/model costs don't collapse to $0.00. Underlying data is untouched.
const usd = (n) => "$" + Number(n).toFixed(2);
const usdSmart = (n) => (Math.abs(Number(n)) >= 0.01 ? usd(n) : "$" + Number(n).toFixed(4));
const usdAvg = (n) => "$" + Number(n).toFixed(4);
const pct = (n) => (Number(n) * 100).toFixed(1) + "%";

// Pure presentation decision for the coverage guard (P2.4): 100% is the claim,
// anything less is a quality regression that must warn.
function coverageState(cov) {
  if (Number(cov) >= 1) return { warn: false, note: "" };
  return { warn: true, note: "\\u26A0 coverage dropped — savings came at a quality cost." };
}

let MODEL_ORDER = [];   // cheapest first
let MODEL_INDEX = {};   // model -> palette index 0..4
let MODEL_META = {};    // model -> {tier, reasoning, role}

async function loadHealth() {
  try {
    const h = await (await fetch(EP.health)).json();
    $("health").textContent = h.status === "ok" ? "● healthy · offline" : "unhealthy";
    if (h.status === "ok") $("health").classList.add("ok");
  } catch (e) { $("health").textContent = "unreachable"; }
}

function tierTag(model) {
  const i = MODEL_INDEX[model];
  const meta = MODEL_META[model];
  if (i === undefined || !meta) return "";
  return "<span class='tiertag t" + i + "'>" + meta.tier + "</span>";
}

async function loadPolicy() {
  const p = await (await fetch(EP.policy)).json();
  $("polver").textContent = "policy v" + p.version;

  const catalog = p.catalog || [];
  MODEL_ORDER = catalog.map((c) => c.model);
  catalog.forEach((c, i) => {
    MODEL_INDEX[c.model] = Math.min(i, 4);
    MODEL_META[c.model] = c;
  });

  const box = $("policy");
  box.innerHTML = "";
  for (const [cls, cands] of Object.entries(p.classes)) {
    const h = document.createElement("div");
    h.className = "cls";
    h.textContent = cls;
    box.appendChild(h);
    for (const c of cands) {
      const row = document.createElement("div");
      row.className = "polrow";
      if (c.role) row.title = c.tier + " — " + c.role;
      row.innerHTML = "<span>" + c.model + tierTag(c.model) + "</span>" +
        "<span>pass " + c.prior_pass + " · $" + c.prior_usd_resolved + "</span>";
      box.appendChild(row);
    }
  }

  $("catalog").innerHTML = catalog.map((c) => {
    const i = MODEL_INDEX[c.model];
    return "<div class='catrow'><div class='h'>" +
      "<span class='name mdot m" + i + "'>" + c.model + "</span>" +
      "<span class='tiertag t" + i + "'>" + c.tier + "</span></div>" +
      "<div class='rw'>reasoning: " + c.reasoning + "</div>" +
      "<div class='role'>" + c.role + "</div></div>";
  }).join("");
}

function renderByClass(byClass) {
  const rows = Object.entries(byClass).sort((a, b) => b[1].baseline_usd - a[1].baseline_usd);
  const maxBase = Math.max(...rows.map((r) => r[1].baseline_usd), 1e-9);
  $("byClass").innerHTML = rows.map(([cls, v]) => {
    const trackPct = (100 * v.baseline_usd / maxBase).toFixed(2);
    const fillPct = (100 * v.routed_usd / (v.baseline_usd || 1)).toFixed(2);
    return "<div class='aggrow'>" +
      "<div class='aggrow-h'><span>" + cls + "</span>" +
      "<span style='color:var(--green)'>" + pct(v.saved_pct) + " saved</span></div>" +
      "<div class='track' style='width:" + trackPct + "%'>" +
      "<span class='fill-routed' style='width:" + fillPct + "%'></span></div>" +
      "<div class='aggrow-f'>routed " + usd(v.routed_usd) + " · naive " + usd(v.baseline_usd) +
      " · " + v.tasks + " tasks</div></div>";
  }).join("");
}

function renderByModel(byModel) {
  const rows = MODEL_ORDER.filter((m) => byModel[m]).map((m) => [m, byModel[m]]);
  const maxCost = Math.max(...rows.map((r) => r[1].routed_usd), 1e-9);
  $("byModel").innerHTML = rows.map(([m, v]) => {
    const i = MODEL_INDEX[m];
    const w = (100 * v.routed_usd / maxCost).toFixed(2);
    return "<div class='aggrow'>" +
      "<div class='aggrow-h'><span class='mdot m" + i + "'>" + m + tierTag(m) + "</span>" +
      "<span>" + v.tasks + " tasks · " + usdSmart(v.routed_usd) + "</span></div>" +
      "<div class='track full'><span class='m" + i + "' style='width:" + w + "%'></span></div></div>";
  }).join("");
}

function renderModeReason(modeCounts, modeCost, reasonCounts) {
  $("byMode").innerHTML = Object.entries(modeCounts).map(([k, c]) =>
    "<div class='chip'><b>" + k + "</b> " + c + " tasks <small>· " + usd(modeCost[k] || 0) +
    "</small></div>").join("");
  $("byReason").innerHTML = Object.entries(reasonCounts).map(([k, c]) =>
    "<span class='pill reason-" + k + "'>" + k + " · " + c + "</span>").join(" ");
}

function renderAggregation(s) {
  const bd = s.breakdown || {};
  renderByClass(bd.by_class || {});
  renderByModel(bd.by_model || {});
  renderUsageSplit(bd.by_model || {});
  renderModeReason(s.mode_counts || {}, bd.mode_cost_usd || {}, bd.reason_counts || {});
  $("kTasks").textContent = s.tasks;
  const cov = coverageState(s.coverage);
  const covEl = $("kCov");
  covEl.textContent = pct(s.coverage);
  covEl.className = "v" + (cov.warn ? " warn" : "");
  const note = $("covNote");
  note.textContent = cov.note;
  note.className = "covnote" + (cov.warn ? " show" : "");
  $("kSingle").textContent = (s.mode_counts.ordered || 0);
  $("kEnsemble").textContent = (s.mode_counts.compare || 0);
  $("kAvg").textContent = usdAvg(s.total_cost_usd / (s.tasks || 1));
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

// P2: name the cheap-vs-premium volume split with the run's real counts.
function renderUsageSplit(byModel) {
  const el = $("usageSplit");
  if (!el) return;
  const used = MODEL_ORDER.filter((m) => byModel[m]);
  if (used.length < 2) { el.textContent = ""; return; }
  const tasksFor = (m) => (byModel[m] ? byModel[m].tasks : 0);
  const cheapTwo = MODEL_ORDER.slice(0, 2).filter((m) => byModel[m]);
  const cheapCount = cheapTwo.reduce((a, m) => a + tasksFor(m), 0);
  const top = used[used.length - 1];
  el.innerHTML = "Cheap tiers carried the volume: <b>" + cheapTwo.join(", ") + "</b> handled <b>" +
    cheapCount + "</b> tasks, while the premium tier <b>" + top + "</b> handled only the <b>" +
    tasksFor(top) + "</b> hardest.";
}

function setCov(id, cov) {
  const el = $(id);
  if (!el) return;
  const st = coverageState(cov);
  el.textContent = "coverage " + pct(cov) + (st.warn ? " \\u26A0" : "");
  el.className = "covpill " + (st.warn ? "warn" : "ok");
}

// P1: three-way comparison — all-mini vs all-premium vs the cost-aware mix.
function renderStrategies(s) {
  const st = s.strategies || {};
  const prem = st.all_premium || { total_cost_usd: s.baseline_total_usd, coverage: 1 };
  const mini = st.all_mini || { total_cost_usd: s.total_cost_usd, coverage: s.coverage };
  const scale = prem.total_cost_usd || 1;
  $("premVal").textContent = usd(prem.total_cost_usd);
  $("premBar").style.width = "100%";
  setCov("premCov", prem.coverage);
  $("miniVal").textContent = usd(mini.total_cost_usd);
  $("miniBar").style.width = (100 * mini.total_cost_usd / scale).toFixed(2) + "%";
  setCov("miniCov", mini.coverage);
  setCov("mixCov", s.coverage);
  $("takeaway").textContent =
    "Cheapest-only is cheaper but drops coverage to " + pct(mini.coverage) +
    " — the cheap tier fails the hard tasks. Premium-only holds " + pct(prem.coverage) +
    " coverage but costs the most. The cost-aware mix is the only strategy that keeps " +
    pct(s.coverage) + " coverage below premium cost.";
}

let running = false;

function renderSpotlight(sp) {
  const panel = $("spotlightPanel");
  if (!panel) return;
  if (!sp) { panel.hidden = true; return; }
  panel.hidden = false;
  $("spotMeta").textContent = sp.task_id + " \\u00b7 " + sp["class"] + " \\u00b7 " + sp.reason;
  $("spotRoutedModel").textContent = sp.chosen_model || "\\u2014";
  $("spotRoutedCost").textContent = usdSmart(sp.routed_usd);
  $("spotNaiveModel").textContent = sp.naive_model;
  $("spotNaiveCost").textContent = usdSmart(sp.naive_usd);
  $("spotRatio").textContent = Number(sp.ratio).toFixed(1) + "\\u00d7";
}

async function runReplay() {
  if (running) return;
  running = true;
  const btn = $("run");
  btn.disabled = true;
  $("progress").textContent = "routing\\u2026";
  try {
    $("traceBody").innerHTML = "";
    const synth = $("synth").checked;
    let data;
    try {
      data = await (await fetch(EP.replay(synth))).json();
    } catch (e) {
      $("progress").textContent = "error \\u2014 could not load replay";
      return;
    }
    const s = data.summary;
    const before = s.baseline_total_usd, after = s.total_cost_usd;

    // fill aggregates + the 3-way strategy comparison immediately
    renderAggregation(s);
    renderStrategies(s);
    renderSpotlight(s.spotlight);

    // P3: headline names the mechanism, not just the percentage
    const byModel = (s.breakdown && s.breakdown.by_model) || {};
    const usedTop = MODEL_ORDER.filter((m) => byModel[m]).slice(-1)[0];
    const topCount = usedTop && byModel[usedTop] ? byModel[usedTop].tasks : 0;
    $("savedPct").textContent = pct(s.delta_pct);
    $("savedAbs").textContent = "lower \\u2014 cheap-first routing; only " + topCount + " of " +
      s.tasks + " tasks needed the top " + (usedTop || "premium") + " tier, held at " +
      pct(s.coverage) + " coverage \\u00b7 saved " + usd(s.delta_usd) + ".";

    // animate the per-task trace, accumulating the mix cost against the premium scale
    const body = $("traceBody");
    const step = data.traces.length > 30 ? 12 : 260;
    let acc = 0;
    for (let i = 0; i < data.traces.length; i++) {
      const t = data.traces[i];
      acc += Number(t.cost_usd || 0);
      const tr = document.createElement("tr");
      const meta = MODEL_META[t.chosen];
      const chosenTitle = meta ? (meta.tier + " \\u2014 " + meta.role) : "";
      tr.innerHTML =
        "<td>" + t.task_id + "</td>" +
        "<td>" + t.class + "</td>" +
        "<td class='mode-" + t.mode + "'>" + t.mode + "</td>" +
        "<td title='" + chosenTitle + "'>" + t.chosen + "</td>" +
        "<td><span class='pill reason-" + t.reason + "'>" + t.reason + "</span></td>" +
        "<td>" + usdSmart(t.cost_usd) + "</td>";
      body.insertBefore(tr, body.firstChild);
      $("afterVal").textContent = usd(acc);
      $("afterBar").style.width = (100 * acc / (before || 1)).toFixed(2) + "%";
      $("progress").textContent = "routed " + (i + 1) + "/" + data.traces.length;
      if (step > 20 || i % 5 === 0) await sleep(step);
    }
    $("afterVal").textContent = usd(after);
    $("afterBar").style.width = (100 * after / (before || 1)).toFixed(2) + "%";
    $("progress").textContent = "done \\u00b7 " + s.tasks + " tasks";
  } finally {
    running = false;
    btn.disabled = false;
  }
}

$("run").addEventListener("click", runReplay);
if (window.innerWidth < 960) { const d = $("policyDetails"); if (d) d.removeAttribute("open"); }
loadHealth();
loadPolicy();
</script>
</body>
</html>
"""
