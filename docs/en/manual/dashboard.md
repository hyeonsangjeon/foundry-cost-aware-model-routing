# Dashboard

You can bring up the same routing pipeline as a small offline service built on the standard
library alone (`http.server`). No web framework, no provider calls, nothing sent over the
network.

## Running it

```bash
cost-router serve                 # http://127.0.0.1:8000
# or together with a hero run
cost-router hero --serve
```

Open `http://127.0.0.1:8000` in a browser and the dashboard comes up. The page is a single
inline HTML/CSS/JS with no external assets or fonts, and makes same-origin fetches only to this
service's JSON endpoints.

!!! success "See it instantly, no install"
    This dashboard is also published statically on GitHub Pages, so you can open it directly with
    no clone or install.

    [:material-open-in-new: Live demo (autoplay)](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1){ .md-button target=_blank }

## What it shows

- **Policy table** — candidate models ranked per class, with their priors.
- **before / after** — naive (premium on every task) vs. cost-aware routing.
- **Cost × coverage frontier** — plots three strategies (all-mini / all-premium / cost-aware
  mix) as a cost (x) × coverage (y) scatter. It's an inline SVG with no library, and **only the
  cost-aware mix** sits in the top-left "both-win" corner (full coverage + low cost). all-mini
  collapses down the coverage axis, and all-premium has the same coverage but sits at the far
  right (maximum cost).
- **Spotlight card** — highlights the one task where cost-aware routing beat the naive premium
  arm by the most, with two cards (routing vs. naive) and a multiplier (e.g. `24.1×` cheaper).
- **Arena (one problem, four ways)** — the "5-minute wow" panel. Pick one task and send **the
  same problem** four ways: the cheapest model · a premium model · an ensemble that fans out to
  everyone · a cost-aware router that climbs up from the cheapest. Each card fills in three axes —
  **cost · latency · accuracy** — and highlights the winner on each. On the default task
  (`t-0003`) the router is **the cheapest and also right** (premium and ensemble are right too) but
  the **slowest on latency** (sequential escalation) — the honest trade-off that there's no free
  lunch. It reads from `/compare` (live) or `compare.json` (static), and task switching is handled
  client-side with no round trip. For details, see [One problem, four ways](head-to-head.md).
- **Coverage cliff (policy A/B)** — compares the same workload side by side against a `cost-cut`
  candidate that erases the seed policy and its expensive fallback. The candidate looks cheaper,
  but coverage collapses **100% → 67% (−33%p)**. This comes from `/regression`, independently of
  replay, and hides silently when there's no data. For the full reading, see [Experiment 03 ·
  Coverage cliff](../lab-notebook/03-coverage-cliff.md).
- **Fan-out dial (threshold sweep)** — sweeps the budget gate's `compare_min_value` from 0 → 1.01
  and shows the number of fan-out tasks, coverage, savings, and ensemble tax at each step.
  **Coverage (100%) and savings (47%) are flat lines**, and only the fan-out tax draws a staircase
  collapsing **[3.74×](projection-results.md) → $0.0000** — a dial that switches off just the tax
  without losing coverage or savings. It comes from `/fanout-sweep` and hides when there's no data.
  See [Experiment 06 · Adaptive fan-out dial](../lab-notebook/06-fanout-dial.md).
- **Experiments (click for statistics)** — click an experiment tab and that experiment's cost,
  coverage, **ensemble fan-out tax**, and reproducibility contract appear at once. It reads
  Azure-Foundry-shaped offline metrics from `GET /experiments` (live) or `experiments.json` (static
  export). To see **which models and how** each tab is built as an animated SVG, see [Experiment
  atlas](experiment-atlas.md); for reading the ensemble tax, see [Experiment 05 · Ensemble fan-out
  tax](../lab-notebook/05-ensemble-fanout.md).
- **Historical dashboard** — a table of recorded experiment-run history. On a live server, one row
  accumulates each time you run an experiment (`GET /metrics/history`); in the static demo, it shows
  a deterministic baseline snapshot per experiment.
- The **cost × coverage frontier** also plots a fourth point, `all-ensemble` (fan out every model
  on every task), revealing that "just run everything" is 100% coverage but sits in the **most
  expensive** corner outside the frontier. A fifth point, `single_call` (**blue dot**), is an Azure
  AI Foundry Model Router–shaped **single-call** routing layer — it picks one model per prompt in
  advance with no escalation, so it sits below and outside the both-win corner at **low coverage**.
  For the full reading, see [Experiment 07 · The routing layer](../lab-notebook/07-model-router.md).
- **Per-task routing-decision animation** — class, selected model, reason, cost.
- **Aggregates** — cost by class, model usage, mode/reason statistics.
- **Fleet & live routing** — shows the registered deployment catalog and picks **which model goes
  in each arm** via router (main)/cheapest/premium dropdowns and an ensemble checkbox. **Run
  selection** honestly re-labels a committed measured snapshot as `measured = false` · `provenance =
  recorded` and replays it (the web path **never makes a paid call**), and prints the exact terminal
  command to measure your selection live. It reads from `GET /fleet` · `POST /fleet/run` and hides
  silently when it's not a live server. For details, see [Fleet registration & model
  selection](fleet.md).

Flip the `full synthetic workload (100 tasks)` toggle at the top and the whole synthetic workload
replays, filling in before/after clearly within 20 seconds. The spotlight card is rendered from the
replay summary's `spotlight` field (an auto-selected representative task).

!!! tip "Hero autorun"
    Open the `http://127.0.0.1:8000/?run=1` address that `cost-router hero --serve` points you to,
    and replay starts the moment the page loads. With the query parameter `?run=1` (or `?autorun`)
    present, replay runs automatically after the policy loads.

!!! note "Every number is an offline projection"
    The dashboard's figures are **identical by construction** to `make replay`/the service (the same
    pipeline calls), not measurements. Model names are generic placeholders.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/` · `/dashboard` | Dashboard HTML |
| GET | `/healthz` | Liveness probe |
| GET | `/policy` | Policy version and candidates per class |
| GET | `/fleet` | Fleet catalog + current slate + live-readiness state |
| POST | `/fleet/run` | Validates the selected slate, then replays a recorded arena snapshot |
| GET | `/replay?synth=true` | Workload replay result (traces + summary) |
| GET | `/regression` | Policy A/B regression (coverage cliff) summary |
| GET | `/fanout-sweep` | Fan-out threshold sweep (adaptive fan-out dial) summary |
| GET | `/compare` · `/compare?task=<id>` | Arena: one problem, four ways (cost · latency · accuracy) |
| GET | `/experiments` | All experiment cards + Foundry-shaped offline metrics |
| GET | `/experiment?name=<name>` | Runs one experiment and records it in history (live timestamp) |
| GET | `/metrics/history` | Recorded run history for the historical dashboard |
| POST | `/route` | Route a single task |
| POST | `/batch-route` | Route several tasks |

```bash
curl -s http://127.0.0.1:8000/healthz
curl -s "http://127.0.0.1:8000/replay?synth=true" | head -c 400
```

## Exporting to a static site

Instead of the live service, you can pre-render the payloads for static hosting.

```bash
python scripts/build_static_site.py cost-router-dashboard
```

It bakes the `/healthz`, `/policy`, `/replay`, `/regression`, `/fanout-sweep`, `/compare`,
`/experiments`, and `/metrics/history` JSON into flat files and injects an endpoint map so the same
dashboard HTML/JS fetches those files instead of the live routes. The injected paths are **relative**
(`healthz.json` etc., with no leading `/`), so it works wherever you put it — the site root or a
project Pages subpath (`…/foundry-cost-aware-model-routing/demo/`). The result is deterministic and
is generated from the bundled synthetic workload only.

This repository's `docs` workflow builds the manual site and then uses this script to bake the
dashboard into `_site/demo/` and deploy it alongside. That's why the [live
demo](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1) above always
reflects the latest routing results.

## Running in a container

```bash
make docker-build     # build the image
make docker-run       # run the service on port 8000
```
