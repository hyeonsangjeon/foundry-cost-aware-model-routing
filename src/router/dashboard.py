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
<title>cost-router · offline routing dashboard</title>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --panel2: #1c2230; --border: #30363d;
    --muted: #8b949e; --text: #e6edf3; --accent: #2f81f7; --green: #3fb950;
    --amber: #d29922; --red: #f85149; --purple: #a371f7; --cyan: #39c5cf;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 13px; line-height: 1.5;
  }
  header {
    padding: 16px 24px; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  }
  h1 { font-size: 16px; margin: 0; font-weight: 600; }
  .badge {
    font-size: 11px; padding: 2px 8px; border-radius: 999px;
    border: 1px solid var(--border); color: var(--muted);
  }
  .badge.ok { color: var(--green); border-color: var(--green); }
  .measured { color: var(--amber); }
  main { padding: 24px; display: grid; gap: 24px; grid-template-columns: 1fr; max-width: 1180px; }
  @media (min-width: 960px) { main { grid-template-columns: 320px 1fr; align-items: start; } }
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
  .panel h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 0 0 12px; }
  .panel h3 { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin: 18px 0 8px; }
  .controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 14px; }
  button {
    background: var(--accent); color: #fff; border: 0; border-radius: 6px;
    padding: 8px 14px; font: inherit; cursor: pointer; font-weight: 600;
  }
  button:disabled { opacity: .5; cursor: default; }
  label.toggle { color: var(--muted); display: flex; gap: 6px; align-items: center; cursor: pointer; }
  .barwrap { margin: 10px 0; }
  .barwrap .lbl { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px; }
  .bar { height: 22px; background: #21262d; border-radius: 4px; overflow: hidden; }
  .bar > span { display: block; height: 100%; width: 0; transition: width .35s ease; }
  .bar.before > span { background: var(--red); }
  .bar.after > span { background: var(--green); }
  .saved { font-size: 22px; font-weight: 700; color: var(--green); margin-top: 6px; }
  .saved small { font-size: 12px; color: var(--muted); font-weight: 400; }
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; margin-top: 14px; }
  .kpi { background: var(--panel2); border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; }
  .kpi .v { font-size: 18px; font-weight: 700; }
  .kpi .k { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }

  .cards { display: grid; grid-template-columns: 1fr; gap: 14px; margin-top: 6px; }
  @media (min-width: 720px) { .cards { grid-template-columns: 1fr 1fr; } }
  .card { background: var(--panel2); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
  .card h3 { margin-top: 0; }
  .aggrow { margin: 8px 0; }
  .aggrow-h { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 3px; }
  .aggrow-f { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .track { height: 14px; background: #0d1117; border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
  .track.full { width: 100%; }
  .track > span { display: block; height: 100%; width: 0; transition: width .4s ease; }
  .fill-routed { background: var(--green); }
  .m0 { background: var(--cyan); } .m1 { background: var(--accent); }
  .m2 { background: var(--purple); } .m3 { background: var(--amber); } .m4 { background: var(--red); }
  .mdot::before { content: "\\25CF"; margin-right: 6px; }
  .mdot.m0 { color: var(--cyan); } .mdot.m1 { color: var(--accent); }
  .mdot.m2 { color: var(--purple); } .mdot.m3 { color: var(--amber); } .mdot.m4 { color: var(--red); }
  .mdot { color: var(--text); }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip { background: #0d1117; border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; font-size: 12px; }
  .chip b { color: var(--text); } .chip small { color: var(--muted); }

  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--border); white-space: nowrap; }
  th { color: var(--muted); font-weight: 500; font-size: 11px; text-transform: uppercase; }
  .tracewrap { max-height: 420px; overflow: auto; }
  .pill { font-size: 11px; padding: 1px 7px; border-radius: 999px; border: 1px solid var(--border); }
  .reason-clean-first { color: var(--green); border-color: var(--green); }
  .reason-escalated { color: var(--amber); border-color: var(--amber); }
  .reason-compared, .reason-tie-broken { color: var(--purple); border-color: var(--purple); }
  .mode-compare { color: var(--purple); }
  .mode-ordered { color: var(--muted); }
  tbody tr { animation: fade .25s ease; }
  @keyframes fade { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; } }
  .polrow { display: flex; justify-content: space-between; padding: 2px 0; border-bottom: 1px dashed var(--border); }
  .polrow:last-child { border-bottom: 0; }
  .cls { color: var(--accent); margin: 10px 0 4px; font-size: 12px; }
  .foot { color: var(--muted); font-size: 11px; margin-top: 10px; }
  .legend { display: grid; grid-template-columns: 1fr; gap: 6px; }
  @media (min-width: 720px) { .legend { grid-template-columns: 1fr 1fr; } }
  .legend .li { font-size: 12px; }
  .legend .term { color: var(--cyan); font-weight: 600; }
  .legend .li small { color: var(--muted); }
  .tiertag { font-size: 10px; padding: 0 6px; border-radius: 999px; border: 1px solid var(--border); margin-left: 6px; white-space: nowrap; }
  .t0 { color: var(--cyan); border-color: var(--cyan); }
  .t1 { color: var(--accent); border-color: var(--accent); }
  .t2 { color: var(--purple); border-color: var(--purple); }
  .t3 { color: var(--amber); border-color: var(--amber); }
  .t4 { color: var(--red); border-color: var(--red); }
  .catrow { padding: 8px 0; border-bottom: 1px dashed var(--border); }
  .catrow:last-child { border-bottom: 0; }
  .catrow .h { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .catrow .name { font-weight: 600; }
  .catrow .role { color: var(--muted); font-size: 11px; margin-top: 3px; }
  .catrow .rw { font-size: 10px; color: var(--muted); }
</style>
</head>
<body>
<header>
  <h1>cost-router</h1>
  <span id="health" class="badge">checking…</span>
  <span id="polver" class="badge">policy —</span>
  <span class="badge measured">offline projection · labels.measured=false</span>
</header>
<main>
  <section class="panel" id="policyPanel">
    <h2>Policy — class → candidates (cheapest first)</h2>
    <div id="policy">loading…</div>
    <h3>Model tiers — what these names mean</h3>
    <div id="catalog"><small style="color:var(--muted)">loading…</small></div>
    <div class="foot">Generic placeholder tiers — not real product names. They stand in for a
      lightweight/high-volume model, an efficient coder, a balanced general model, a deliberate
      reasoner, and a premium frontier model.</div>
  </section>

  <section class="panel">
    <h2>Replay — naive vs cost-aware routing</h2>
    <div class="controls">
      <button id="run">▶ Run replay</button>
      <label class="toggle"><input type="checkbox" id="synth" checked /> full synthetic workload (100 tasks)</label>
      <span id="progress" class="badge">idle</span>
    </div>

    <div class="barwrap">
      <div class="lbl"><span>BEFORE — premium model on every task</span><b id="beforeVal">$0.000000</b></div>
      <div class="bar before"><span id="beforeBar"></span></div>
    </div>
    <div class="barwrap">
      <div class="lbl"><span>AFTER — cost-aware routing</span><b id="afterVal">$0.000000</b></div>
      <div class="bar after"><span id="afterBar"></span></div>
    </div>
    <div class="saved"><span id="savedPct">0.0%</span> lower <small id="savedAbs">— run a replay to project savings</small></div>

    <div class="kpis" id="kpis">
      <div class="kpi"><div class="v" id="kTasks">—</div><div class="k">tasks</div></div>
      <div class="kpi"><div class="v" id="kCov">—</div><div class="k">coverage</div></div>
      <div class="kpi"><div class="v" id="kSingle">—</div><div class="k">single-route</div></div>
      <div class="kpi"><div class="v" id="kEnsemble">—</div><div class="k">ensemble</div></div>
      <div class="kpi"><div class="v" id="kAvg">—</div><div class="k">avg $/task</div></div>
    </div>

    <h2 style="margin-top:22px">Aggregated statistics</h2>
    <div class="cards">
      <div class="card">
        <h3>Cost by task class — routed vs naive</h3>
        <div id="byClass"><small style="color:var(--muted)">run a replay…</small></div>
      </div>
      <div class="card">
        <h3>Model usage — tasks &amp; routed cost</h3>
        <div id="byModel"><small style="color:var(--muted)">run a replay…</small></div>
      </div>
      <div class="card">
        <h3>Routing mode</h3>
        <div class="chips" id="byMode"><small style="color:var(--muted)">run a replay…</small></div>
        <h3>Reason</h3>
        <div class="chips" id="byReason"><small style="color:var(--muted)">run a replay…</small></div>
      </div>
      <div class="card">
        <h3>What each column means</h3>
        <div class="legend">
          <div class="li"><span class="term">task</span> — synthetic task id.</div>
          <div class="li"><span class="term">class</span> — task type: plan · generate · test · validate · repo_patch.</div>
          <div class="li"><span class="term">mode</span> — <small><b>ordered</b> = try candidates cheapest-first, take the first clean one. <b>compare</b> = ensemble: evaluate several, keep the best.</small></div>
          <div class="li"><span class="term">chosen</span> — placeholder model that handled the task.</div>
          <div class="li"><span class="term">reason</span> — <small><b>clean-first</b> top pick passed · <b>escalated</b> cheaper failed, moved up · <b>compared</b> ensemble winner · <b>tie-broken</b> tie settled by cost.</small></div>
          <div class="li"><span class="term">cost</span> — <small>projected USD for this task (offline, not measured).</small></div>
        </div>
      </div>
    </div>

    <h2 style="margin-top:22px">Per-task routing trace</h2>
    <div class="tracewrap">
      <table>
        <thead><tr><th>task</th><th>class</th><th>mode</th><th>chosen</th><th>reason</th><th>cost</th></tr></thead>
        <tbody id="traceBody"></tbody>
      </table>
    </div>
    <div class="foot">Numbers are an offline projection over synthetic data — not measured. Model names are generic placeholders.</div>
  </section>
</main>
<script>
const $ = (id) => document.getElementById(id);
const usd = (n) => "$" + Number(n).toFixed(6);
const usd4 = (n) => "$" + Number(n).toFixed(4);
const pct = (n) => (Number(n) * 100).toFixed(1) + "%";

let MODEL_ORDER = [];   // cheapest first
let MODEL_INDEX = {};   // model -> palette index 0..4
let MODEL_META = {};    // model -> {tier, reasoning, role}

async function loadHealth() {
  try {
    const h = await (await fetch("/healthz")).json();
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
  const p = await (await fetch("/policy")).json();
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
      "<div class='aggrow-f'>routed " + usd4(v.routed_usd) + " · naive " + usd4(v.baseline_usd) +
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
      "<span>" + v.tasks + " tasks · " + usd4(v.routed_usd) + "</span></div>" +
      "<div class='track full'><span class='m" + i + "' style='width:" + w + "%'></span></div></div>";
  }).join("");
}

function renderModeReason(modeCounts, modeCost, reasonCounts) {
  $("byMode").innerHTML = Object.entries(modeCounts).map(([k, c]) =>
    "<div class='chip'><b>" + k + "</b> " + c + " tasks <small>· " + usd4(modeCost[k] || 0) +
    "</small></div>").join("");
  $("byReason").innerHTML = Object.entries(reasonCounts).map(([k, c]) =>
    "<span class='pill reason-" + k + "'>" + k + " · " + c + "</span>").join(" ");
}

function renderAggregation(s) {
  const bd = s.breakdown || {};
  renderByClass(bd.by_class || {});
  renderByModel(bd.by_model || {});
  renderModeReason(s.mode_counts || {}, bd.mode_cost_usd || {}, bd.reason_counts || {});
  $("kTasks").textContent = s.tasks;
  $("kCov").textContent = pct(s.coverage);
  $("kSingle").textContent = (s.mode_counts.ordered || 0);
  $("kEnsemble").textContent = (s.mode_counts.compare || 0);
  $("kAvg").textContent = usd4(s.total_cost_usd / (s.tasks || 1));
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function runReplay() {
  const btn = $("run");
  btn.disabled = true;
  $("traceBody").innerHTML = "";
  const synth = $("synth").checked;
  $("progress").textContent = "routing…";
  let data;
  try {
    data = await (await fetch("/replay?synth=" + synth)).json();
  } catch (e) {
    $("progress").textContent = "error";
    btn.disabled = false;
    return;
  }
  const s = data.summary;
  const before = s.baseline_total_usd, after = s.total_cost_usd;

  // fill the aggregate stats immediately from the full summary
  renderAggregation(s);
  $("beforeVal").textContent = usd(before);
  $("beforeBar").style.width = "100%";
  $("savedPct").textContent = pct(s.delta_pct);
  $("savedAbs").textContent = "— saved " + usd(s.delta_usd) + " at " + pct(s.coverage) + " coverage";

  // animate the per-task trace, accumulating routed cost against the fixed baseline
  const body = $("traceBody");
  const step = data.traces.length > 30 ? 12 : 260;
  let acc = 0;
  for (let i = 0; i < data.traces.length; i++) {
    const t = data.traces[i];
    acc += Number(t.cost_usd || 0);
    const tr = document.createElement("tr");
    const meta = MODEL_META[t.chosen];
    const chosenTitle = meta ? (meta.tier + " — " + meta.role) : "";
    tr.innerHTML =
      "<td>" + t.task_id + "</td>" +
      "<td>" + t.class + "</td>" +
      "<td class='mode-" + t.mode + "'>" + t.mode + "</td>" +
      "<td title=\"" + chosenTitle + "\">" + t.chosen + "</td>" +
      "<td><span class='pill reason-" + t.reason + "'>" + t.reason + "</span></td>" +
      "<td>" + usd(t.cost_usd) + "</td>";
    body.insertBefore(tr, body.firstChild);
    $("afterVal").textContent = usd(acc);
    $("afterBar").style.width = (100 * acc / before).toFixed(2) + "%";
    $("progress").textContent = "routed " + (i + 1) + "/" + data.traces.length;
    if (step > 20 || i % 5 === 0) await sleep(step);
  }
  $("afterVal").textContent = usd(after);
  $("afterBar").style.width = (100 * after / before).toFixed(2) + "%";
  $("progress").textContent = "done · " + s.tasks + " tasks";
  btn.disabled = false;
}

$("run").addEventListener("click", runReplay);
loadHealth();
loadPolicy();
</script>
</body>
</html>
"""
