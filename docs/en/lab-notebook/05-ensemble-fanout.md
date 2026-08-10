# Experiment 05 · Calling several models at once multiplies the cost

!!! abstract "One-line summary"
    Cost-aware routing fans out to every candidate (compare mode) **only on high-value tasks** and bills only the winner. But the trace's `cost_usd` records **only the winner**, so the money the fan-out *actually* spent (the sum of all candidates) stays hidden. This experiment surfaces that hidden cost — it spends **$0.50** fanning out across 6 tasks and keeps only the **$0.13** winner. The remaining **$0.36 (3.74×)** is the **ensemble tax** (the cost of running the losing models). All numbers are `measured = false`.

<figure markdown="span">
  ![Ensemble loop animation — a parallel fan-out to five candidates, then the cheapest passing candidate is adopted](/foundry-cost-aware-model-routing/assets/gif/ensemble.gif)
  <figcaption>Ensemble loop — the workload fans out in parallel to five candidates and the compare node keeps the cheapest passing one. The fan-out tax paid for the losing calls piles up alongside.</figcaption>
</figure>

## What this experiment is

- **Situation (when):** the moment the idea lands — "wouldn't running several models as an ensemble (best-of-N, OpenRouter-style) be better?" Fan-out can raise quality, but **the cost multiplies.** When you need to meter that cost honestly.
- **Task (what):** on 6 hand-picked high-value tasks, attach offline signals where the cheap candidate fails one check and the **middle and top candidates pass completely (a tie)** (`samples/responses/ensemble-fanout-signals.sample.json`). A budget gate sends them into **compare mode**, evaluating every candidate (fan-out), and ties break to the **cheapest fully-passing model** by policy rank.
- **Experiment (what it tests):** that routing (1) holds **coverage at 100%** while (2) saving **~47%** against naive, and at the same time (3) recovers, through a shared metric, the exact gap between the fan-out's total spend and the winner cost — **the ensemble tax**.

This is the **fifth honesty**, after experiments 01 · 02 (the gain), 03 (the coverage cliff), and 04 (no free lunch). Here it surfaces, in numbers, that *"an ensemble isn't free — fan-out carries a tax."*

## Why the tax hides

When `route_tasks` fans out in compare mode it evaluates every candidate, but the trace's `cost_usd` bills **only the one selected model**. So routing's bill (`total_cost_usd`) is the honest routing cost, but **not the real cost of "running every model as an ensemble."** That real cost is the **sum of the costs of every candidate tried** on each compare task.

`router.metrics.fanout_stats(traces)` recovers exactly this sum:

- `fanout_usd` — the sum of the costs of **all candidates** tried on the compare tasks (the fan-out cost)
- `winner_usd` — the cost of **the winner** among them (what routing actually billed)
- `ensemble_tax_usd` = `fanout_usd − winner_usd` — **the cost of running the losing models (the tax)**
- `tax_ratio` = `fanout_usd / winner_usd` — how many times the winner the fan-out costs

## Setup

- **Workload:** the 6 high-value tasks in `samples/telemetry/mixed-coding-workload.sample.jsonl`
- **Signals:** [`samples/responses/ensemble-fanout-signals.sample.json`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/responses/ensemble-fanout-signals.sample.json)
  (cheap candidate fails one check; middle and top pass completely, a tie)
- **Policy · pricing:** bundled seed policy · pricing (`measured = false`)

## Run

```bash
cost-router experiment run ensemble
cost-router experiment run ensemble --json     # contract checks + full fan-out stats
cost-router metrics emit ensemble              # Azure Foundry-shaped metric records
```

## Result — 47% saved, but the fan-out is 3.74×

```text
before / after  (offline projection over synthetic data; labels.measured=false)
  BEFORE  naive: premium model on every task   $0.25
  AFTER   cost-aware routing                   $0.13
  SAVED   $0.12  (47.0% lower)  at 100.0% coverage

reproducibility  PASS
  PASS  coverage: 100.0% ≥ 100.0%
  PASS  savings: 47.0% ≥ 40.0%
  PASS  tasks: 6 ≥ 6
```

Routing's bill is honestly cheap at **$0.13**, but fanning those 6 tasks out in compare mode actually ran **$0.50** worth of models. Task by task:

| task | class | fan-out candidates | winner | fan-out cost | winner cost | ensemble tax |
| --- | --- | --- | --- | --- | --- | --- |
| t-0003 | repo_patch | swift · balanced · deep · premium | **balanced-pro** | $0.18 | $0.03 | $0.15 |
| t-0007 | plan | swift · balanced · deep | **balanced-pro** | $0.09 | $0.03 | $0.06 |
| t-0024 | repo_patch | swift · balanced · deep · premium | **deep-reasoner** | $0.19 | $0.06 | $0.12 |
| t-0036 | generate | mini · swift · balanced | **swift-coder** | $0.02 | $0.0026 | $0.01 |
| t-0015 | validate | mini · balanced · deep | **balanced-pro** | $0.01 | $0.0049 | $0.0090 |
| t-0032 | test | mini · swift · balanced | **swift-coder** | $0.01 | $0.0021 | $0.01 |
| **Total** | | | | **$0.50** | **$0.13** | **$0.36** |

**Ensemble tax = $0.36**, i.e. the fan-out cost is **3.74×** the winner.

> Canonical: the ensemble fan-out tax (3.74×) is collected in [offline experiment results](../manual/projection-results.md).

!!! example "Spotlight — t-0032 (test)"
    Routing chose `swift-coder` ($0.0021) while the naive premium arm uses `balanced-pro` ($0.01) → **5.14× cheaper**. But fanning out this one task (mini · swift · balanced) costs **$0.01**, 6.5× the winner. The saving and the fan-out tax hold **at the same time**.

## Strategy frontier — "run everything" is off the frontier

We confirm the same honesty with a **strategy arm** on the 100-task synthetic hero workload. We added a fourth point, `all_ensemble` (fan out every model on every task), to the dashboard frontier:

| Strategy | Cost | Coverage |
| --- | --- | --- |
| all-mini (cheapest model only) | $0.19 | 22% |
| cost-aware mix (routing) | $1.66 | 100% |
| all-premium (priciest model only) | $2.23 | 100% |
| **all-ensemble (fan out everything)** | **$4.23** | 100% |

`all-ensemble` has 100% coverage but is **the most expensive** — 1.9× even premium. The frontier makes it visually plain that "just run everything" is pure waste that buys no coverage (premium already reaches 100%).

## The shared metric class — store and query in Foundry shape

The reusable asset this experiment introduces is the **shared metric module** in `src/router/metrics.py`. Because the CLI, the HTTP service, and the dashboard all share this one module, per-experiment stats and the historical dashboard never recompute numbers by hand.

- `ExperimentMetrics` — a normalized snapshot of one run (cost · coverage · fan-out tax + a content-addressed `run_id`). Pure and deterministic.
- `ExperimentMetrics.to_metric_records()` — renders **Azure Monitor / OpenTelemetry** metric-data-point shape (value · unit · `customDimensions`) — a payload you can push straight into Azure AI Foundry observability.
- `JsonlMetricsStore` — an offline history store (append-only JSONL). The historical dashboard reads from here.
- `FoundryMetricsEmitter` — becomes `configured = True` when a connection string (`AZURE_AI_FOUNDRY_CONNECTION_STRING` etc.) is present, but actual sending happens **only through an injected sink** → the default path never touches the network (offline- and test-safe).

For usage details, see the [Metrics & Foundry](../manual/metrics.md) manual.

## See it in the web app — click for stats, historical dashboard

We added two panels to the dashboard:

- **Experiments** — click an experiment tab and its cost · coverage · **ensemble fan-out tax** · reproducibility contract appear instantly. It reads Foundry-shaped metrics from `GET /experiments` (live) or `experiments.json` (static export).
- **Historical dashboard** — a table of recorded run history. On a live server it accrues one row every time you run an experiment (`GET /metrics/history`); in the static demo it shows a deterministic reference snapshot per experiment.

[See it in the live demo →](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1)

## Reading this number honestly

Ensemble/fan-out **can raise quality** — but that is the claim of a quality experiment, not a cost one. This repo honestly covers only the **offline cost view**: *at the same coverage, fan-out is always more expensive than routing that bills only the winner.* Whether to turn ensemble on is a question to settle with **measured** data — whether the fan-out tax ($0.36, 3.74×) buys quality worth having — and this experiment meters exactly that **cost axis**, providing half of that judgment.

## When to use this experiment

- To gauge "how much more does adopting a multi-model ensemble / best-of-N cost?" as a **per-task fan-out tax**.
- To expose the tax alongside routing's savings, so you don't boast the winner cost **while hiding the fan-out cost**.
- When you need a **shared metric schema** to export experiment stats to Azure AI Foundry observability.

## Reproduce this experiment

```bash
pip install -e .
cost-router experiment run ensemble          # human-readable summary
cost-router experiment run ensemble --json    # contract checks + fan-out stats
cost-router metrics emit ensemble             # Azure Foundry-shaped metric records
cost-router metrics history --store runs.jsonl   # query history (if recorded)
```
