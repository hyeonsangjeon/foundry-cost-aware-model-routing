# Lab notebook — introduction and methodology

This lab notebook records the **methods, numbers, and reproduction steps** for the
experiments actually run in this repository. The point of a lab notebook is not
marketing numbers but letting anyone reach **the same results** with the same
commands.

!!! tip "New here? Start with the [story arc](story-arc.md)"
    The [story arc](story-arc.md) explains experiments 01–07 in order: what each
    experiment changed, what result came out, and which question the next experiment
    answers. It also links to the [experiment 08 arena](08-arena.md). This page covers
    the **shared methodology and metric definitions** used by all of them.

## Shared methodology

- **Offline and deterministic.** No network, no credentials, no external calls.
  Synthetic workloads and deterministic signals reproduce identically every time.
- **Honesty label.** Every number carries `labels.measured = false` — an offline
  projection over synthetic data, not a measured saving.
- **Placeholder models.** `mini-fast`, `swift-coder`, `balanced-pro`,
  `deep-reasoner`, and `premium-max` are all generic placeholders, not specific
  products.
- **Reproducibility contract.** Each experiment sets an `expect` floor, and the run
  fails if the offline projection drops below it. Some experiments also set a
  `max_delta_pct` **ceiling** (a two-sided contract), so the run also fails if the
  saving becomes implausibly large — see [experiment 04](04-no-free-lunch.md).
  `max_tax_ratio` limits the extra cost of calling every candidate — see
  [experiment 06](06-fanout-dial.md). `min_escalation_gain` requires
  observe-then-escalate to recover more coverage than single-call routing — see
  [experiment 07](07-model-router.md).

## Arm definitions

| arm | Selection | Character |
| --- | --- | --- |
| cost | cheapest candidate per class | illustrative equivalent |
| balanced | middle candidate per class | illustrative equivalent |
| quality (naive) | most expensive candidate per class | before (naive) baseline |
| **cost-aware routing** | cheapest passing model first, escalate on failure | this repo's approach |

The `cost` / `balanced` / `quality` arms are transparent **placeholder baselines**,
not claims about a managed router's internal implementation.

!!! tip "See it as a cost × coverage frontier"
    The [dashboard](../manual/dashboard.md) plots five strategies — `all-mini`,
    `all-premium`, `cost-aware mix`, `all-ensemble`, `single_call` — on a **cost (x)
    × coverage (y) scatter**. cost-aware mix has full coverage at low cost.
    `all-ensemble` also reaches 100% coverage but costs the most because it calls
    every candidate. `single_call` costs less but has **low coverage** because it
    cannot move up after a failure. See the chart in the
    [live demo](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1).

## Metrics

- **coverage (pass rate)** — the share of accepted tasks (those whose self-signals
  are clean). This is the `coverage` field the offline CLI prints, and it differs
  from the **grading coverage** (the share of graded cells — measurement
  completeness) that the measured experiments (11 · 12 · 03D) report separately →
  [glossary](../manual/glossary.md).
- **total_cost_usd** — the summed cost of the selected runs (offline projection).
- **delta_pct** — the saving relative to the naive (quality arm) baseline.
- **spotlight ratio** — the naive-to-routing cost ratio on a representative task.

## How to reproduce

```bash
pip install -e .
cost-router experiment list
cost-router experiment run hero --json     # machine-readable full summary
```

Each experiment page ends with the exact command that reproduces it.

## Experiment list

This repository holds **12 experiments (01–12)** — a projection track (01–08) and a
measured track (09–12). The canonical figures for the projection track are collected
in [offline experiment results](../manual/projection-results.md).

- [Experiment 01 · Flagship](01-hero.md) — 100 synthetic tasks; 25.5% saved while holding coverage
- [Experiment 02 · Curated sample](02-curated.md) — five tasks you can follow by eye; 56.7% saved
- [Experiment 03 · Coverage cliff](03-coverage-cliff.md) — removing the expensive fallback drops coverage from 100% → 67%
- [Experiment 04 · No free lunch](04-no-free-lunch.md) — when only the top model passes, routing saves 0% at 100% coverage
- [Experiment 05 · Ensemble fan-out tax](05-ensemble-fanout.md) — calling every model still saves 47%, but costs 3.74× as much as the winner alone
- [Experiment 06 · Adaptive fan-out dial](06-fanout-dial.md) — compared with experiment 05, raising one budget threshold keeps coverage and savings unchanged while the extra-call ratio falls 3.74× → 0
- **[Experiment 07 · Routing layer](07-model-router.md)** ⭐ *centerpiece* — pick once, like a generic `single-call` arm? 52% coverage on synthetic data (the observe-then-escalate mix reaches 100% at comparable cost, +48%p) · *selection is the built-in router's job; verification and governance are this repo's*
- [Experiment 08 · Arena](08-arena.md) — one problem, four ways (a prototype run)? the router is the cheapest correct answer but the **slowest**, because escalation is sequential (cost and accuracy are offline projections; **latency is a new illustrative projection**)
- [Experiment 09 · Live routing](09-live-routing-proof.md) — one real `model-router` deployment routes to **`gpt-5.4` (3)** and **`grok-4-1-fast-reasoning` (2)** (the repo's first **`measured = true`**, keyless Entra)
- [Experiment 10 · Measured ledger](10-measured-ledger.md) — the live run is written to a hash-chained ledger with a sealed rate card; one command re-verifies `PASS`, and **a single edited byte fails**
- [Experiment 11 · Paid router-mode run](11-router-modes-void.md) — the first **paid 4-arm comparison ($3.47/$20)** is **VOID** because quality grading coverage was 79.2% < 90%; it also recorded quality > premium, Grok 100% (not Claude), and reasoning consuming the output
- [Experiment 12 · Paid router-mode re-run](12-router-modes-measured.md) — Fix A/B from experiment 11 are applied and the same gate is used again; grading coverage rises 79.2% → **96.18%**, **all four arms PASS → publishable**, `cost < balanced < premium ≤ quality` holds, and Cost is 100% Grok across two runs. $3.27/$20, byte-identical replay, unpriced 0%
