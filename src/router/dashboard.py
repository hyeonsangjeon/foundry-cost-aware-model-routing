"""Self-contained offline dashboard for the routing service.

The page is a single inline HTML/CSS/JS string with no external assets, fonts,
or network calls other than same-origin fetches to this service's own JSON
endpoints (``/healthz``, ``/policy``, ``/replay``). It renders the policy table,
runs a replay over the bundled synthetic workload, animates the per-task routing
decisions, and shows the naive-vs-routed before/after projection. All model
names come from the policy data (generic placeholders); nothing here is a
measured result.
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
    --bg: #0d1117; --panel: #161b22; --border: #30363d; --muted: #8b949e;
    --text: #e6edf3; --accent: #2f81f7; --green: #3fb950; --amber: #d29922;
    --red: #f85149; --purple: #a371f7;
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
  main { padding: 24px; display: grid; gap: 24px; grid-template-columns: 1fr; max-width: 1100px; }
  @media (min-width: 900px) { main { grid-template-columns: 340px 1fr; } }
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
  .panel h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 0 0 12px; }
  .controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
  button {
    background: var(--accent); color: #fff; border: 0; border-radius: 6px;
    padding: 8px 14px; font: inherit; cursor: pointer; font-weight: 600;
  }
  button:disabled { opacity: .5; cursor: default; }
  label.toggle { color: var(--muted); display: flex; gap: 6px; align-items: center; cursor: pointer; }
  .barwrap { margin: 10px 0; }
  .barwrap .lbl { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px; }
  .bar { height: 22px; background: #21262d; border-radius: 4px; overflow: hidden; }
  .bar > span { display: block; height: 100%; width: 0; transition: width .3s ease; }
  .bar.before > span { background: var(--red); }
  .bar.after > span { background: var(--green); }
  .saved { font-size: 22px; font-weight: 700; color: var(--green); margin-top: 6px; }
  .saved small { font-size: 12px; color: var(--muted); font-weight: 400; }
  .stats { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 10px; color: var(--muted); font-size: 12px; }
  .stats b { color: var(--text); }
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
  .foot { color: var(--muted); font-size: 11px; margin-top: 6px; }
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
    <div class="saved"><span id="savedPct">0.0%</span> lower <small id="savedAbs">— saved $0.000000</small></div>
    <div class="stats">
      <span>coverage <b id="cov">—</b></span>
      <span>tasks <b id="tasks">—</b></span>
      <span>single-route <b id="single">—</b></span>
      <span>ensemble <b id="ensemble">—</b></span>
    </div>

    <h2 style="margin-top:18px">Per-task routing trace</h2>
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
const pct = (n) => (Number(n) * 100).toFixed(1) + "%";

async function loadHealth() {
  try {
    const h = await (await fetch("/healthz")).json();
    $("health").textContent = h.status === "ok" ? "● healthy · offline" : "unhealthy";
    if (h.status === "ok") $("health").classList.add("ok");
  } catch (e) { $("health").textContent = "unreachable"; }
}

async function loadPolicy() {
  const p = await (await fetch("/policy")).json();
  $("polver").textContent = "policy v" + p.version;
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
      row.innerHTML = "<span>" + c.model + "</span><span>pass " + c.prior_pass +
        " · $" + c.prior_usd_resolved + "</span>";
      box.appendChild(row);
    }
  }
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
  $("beforeVal").textContent = usd(before);
  $("beforeBar").style.width = "100%";
  $("cov").textContent = pct(s.coverage);
  $("tasks").textContent = s.tasks;
  $("single").textContent = (s.mode_counts.ordered || 0);
  $("ensemble").textContent = (s.mode_counts.compare || 0);

  // animate task-by-task, accumulating routed cost against the fixed baseline
  const body = $("traceBody");
  const step = data.traces.length > 30 ? 12 : 260; // faster for the big workload
  let acc = 0;
  for (let i = 0; i < data.traces.length; i++) {
    const t = data.traces[i];
    acc += Number(t.cost_usd || 0);
    const tr = document.createElement("tr");
    tr.innerHTML =
      "<td>" + t.task_id + "</td>" +
      "<td>" + t.class + "</td>" +
      "<td class='mode-" + t.mode + "'>" + t.mode + "</td>" +
      "<td>" + t.chosen + "</td>" +
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
  $("savedPct").textContent = pct(s.delta_pct);
  $("savedAbs").textContent = "— saved " + usd(s.delta_usd) + " at " + pct(s.coverage) + " coverage";
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
