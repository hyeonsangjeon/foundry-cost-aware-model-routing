// Headless render harness for tests/test_demo_rendered_locale.py.
//
// Runs the exported demo's own page script against its exported JSON payloads
// with a minimal stub DOM, drives the replay, every compare task and every
// experiment card, then prints (as JSON) every string the page wrote. This is
// how the locale assertions see what a reader actually sees, rather than only
// what the payload contains.
//
// Usage: node render_demo.js <exported-demo-dir>
const fs = require("fs");
const path = require("path");

const dir = process.argv[2];
const html = fs.readFileSync(path.join(dir, "index.html"), "utf8");

const written = [];
function record(s) {
  if (typeof s === "string" && s.trim()) written.push(s);
}

class El {
  constructor(tag) {
    this.tagName = (tag || "div").toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this._cls = new Set();
    this._text = "";
    this._html = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = true;
    this.value = "";
    this.classList = {
      add: (c) => this._cls.add(c),
      remove: (c) => this._cls.delete(c),
      toggle: (c, on) => (on ? this._cls.add(c) : this._cls.delete(c)),
      contains: (c) => this._cls.has(c),
    };
  }
  get className() { return Array.from(this._cls).join(" "); }
  set className(v) { this._cls = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get textContent() { return this._text; }
  set textContent(v) { this._text = String(v); record(this._text); }
  get innerHTML() { return this._html; }
  set innerHTML(v) { this._html = String(v); record(this._html); }
  get offsetWidth() { return 1; }
  appendChild(c) { this.children.push(c); return c; }
  insertBefore(c) { this.children.unshift(c); return c; }
  removeChild(c) { return c; }
  get firstChild() { return this.children[0] || null; }
  setAttribute() {}
  getAttribute() { return null; }
  addEventListener() {}
  removeEventListener() {}
  closest() { return null; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  focus() {}
  scrollIntoView() {}
}

const els = new Map();
const document = {
  getElementById: (id) => {
    if (!els.has(id)) els.set(id, new El("div"));
    return els.get(id);
  },
  createElement: (t) => new El(t),
  createTextNode: (t) => { record(String(t)); return { textContent: String(t) }; },
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener: (_e, fn) => { queue.push(fn); },
  body: new El("body"),
  documentElement: new El("html"),
};
const queue = [];
const window = {
  __ENDPOINTS__: null,
  location: { search: "" },
  addEventListener: () => {},
  matchMedia: () => ({ matches: false, addEventListener: () => {} }),
};
global.document = document;
global.window = window;
global.navigator = { language: "en" };
global.setTimeout = (fn) => { fn(); return 0; };
global.requestAnimationFrame = (fn) => { fn(); return 0; };
global.fetch = async (url) => {
  const name = String(url).split("/").pop();
  const file = path.join(dir, name);
  if (!fs.existsSync(file)) throw new Error("no payload " + name);
  const body = fs.readFileSync(file, "utf8");
  return { ok: true, json: async () => JSON.parse(body), text: async () => body };
};

// The page carries two <script> blocks: the endpoint map, then the app.
const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
const appIdx = blocks.findIndex((b) => b.indexOf("function runReplay") >= 0);
if (appIdx < 0) throw new Error("app script not found in the exported page");
// Everything before the app script sets up window globals (locale, endpoints).
for (let i = 0; i < appIdx; i++) {
  try { eval(blocks[i]); } catch (e) { /* metadata block, not needed here */ }
}
// Re-export the page's own entry points so the harness can drive them.
eval(
  blocks[appIdx] +
    "\n;globalThis.__api = { runReplay, loadArena, loadExperiments, loadHistory," +
    " renderArena, selectExperiment, arena: () => ARENA, experiments: () => EXPERIMENTS };"
);
const api = globalThis.__api;

(async () => {
  for (const fn of queue) {
    try { await fn(); } catch (e) { /* a panel whose endpoint is absent stays hidden */ }
  }
  // The replay is behind a button; drive it directly.
  try { await api.runReplay(); } catch (e) { record("[runReplay error] " + e.message); }
  try { await api.loadArena(); } catch (e) { record("[loadArena error] " + e.message); }
  try { await api.loadExperiments(); } catch (e) { /* optional panel */ }
  try { await api.loadHistory(); } catch (e) { /* optional panel */ }
  // Every task in the compare menu, so all five problems are rendered.
  try {
    const A = api.arena();
    if (A) for (const t of A.tasks) api.renderArena(A, t.task_id);
  } catch (e) { record("[arena sweep error] " + e.message); }
  // Every experiment card, so all contract checks are rendered.
  try {
    const X = api.experiments() || [];
    for (let i = 0; i < X.length; i++) api.selectExperiment(i);
  } catch (e) { record("[experiment sweep error] " + e.message); }
  process.stdout.write(JSON.stringify(written, null, 0));
})();
