# Lab notebook — introduction and methodology

This lab notebook records the **methods, numbers, and reproduction steps** for the
experiments actually run in this repository. The point of a lab notebook is not
marketing numbers but letting anyone reach **the same results** with the same
commands.

!!! tip "New here? Start with the [story arc](story-arc.md)"
    The [story arc](story-arc.md) explains experiments 01–07 in order: what each
    experiment changed, what result came out, and which question the next experiment
    answers. It also links to the [experiment 08 four-way comparison](08-arena.md). This page covers
    the **shared methodology and metric definitions** used by all of them.

## Shared methodology

- **Offline and deterministic (projection track 01–08).** No network, no credentials,
  no external calls. Synthetic workloads and deterministic signals reproduce
  identically every time.
- **Honesty label.** The projection track (01–08) numbers carry `labels.measured =
  false` — an offline projection over synthetic data, not a measured saving. The
  measured track (09–13) uses real Azure Foundry calls with `measured = true`.
- **Placeholder models.** `mini-fast`, `swift-coder`, `balanced-pro`,
  `deep-reasoner`, and `premium-max` are all generic placeholders, not specific
  products.
- **Reproducibility criteria.** Each experiment sets an `expect` floor, and the run
  fails if the offline projection drops below it. Some experiments also set a
  `max_delta_pct` **ceiling** (a two-sided contract), so the run also fails if the
  saving becomes implausibly large — see [experiment 04](04-no-free-lunch.md).
  `max_tax_ratio` limits the extra cost of calling every candidate — see
  [experiment 06](06-fanout-dial.md). `min_escalation_gain` requires
  observe-then-escalate routing to solve more tasks than single-call routing — see
  [experiment 07](07-model-router.md).

## Arm definitions

An **arm** is one comparison strategy evaluated against the same workload under the same
measurement plan. The projection track uses four:

| arm | Selection | Character |
| --- | --- | --- |
| cost | cheapest candidate per class | illustrative equivalent |
| balanced | middle candidate per class | illustrative equivalent |
| quality (premium baseline) | most expensive candidate per class | the before comparator: premium on every task |
| **cost-aware routing** | cheapest passing model first, escalate on failure | this repo's approach |

The `cost` / `balanced` / `quality` arms are transparent **placeholder baselines**,
not claims about a managed router's internal implementation. They share their names with
Model Router's Cost, Balanced and Quality modes, measured separately in experiments 11,
12 and 13, but they are not measurements of those modes
([glossary](../manual/glossary.md)).

!!! tip "See it as a cost × pass-rate frontier"
    The [dashboard](../manual/dashboard.md) plots five strategies — `all-mini`,
    `all-premium`, `cost-aware mix`, `all-ensemble`, `single_call` — on a **cost (x)
    × pass rate (y) scatter**, where the chart's own axis label reads `coverage`, the
    field name for that pass rate. Observe-then-escalate routing (`cost-aware mix`)
    reaches a 100% pass rate at low cost. `all-ensemble` also reaches 100% but costs the
    most because it calls every candidate. `single_call` costs less and has a **lower
    pass rate**, because it cannot move up after a failure. See the chart in the
    [live demo](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1).

## Metrics

- **pass rate** — the share of accepted tasks (those whose self-signals are clean). The
  offline CLI prints it under the field name `coverage`. It differs from **grading
  coverage** (the share of planned cells that were graded — measurement completeness),
  which the measured experiments 11, 12 and 13 report separately →
  [glossary](../manual/glossary.md).
- **total_cost_usd** — the summed cost of the selected runs (offline projection).
- **delta_pct** — the saving relative to the premium-on-every-task baseline (the quality arm).
- **representative-task ratio** — the premium-baseline-to-routing cost ratio on a representative task.

## How to reproduce

```bash
pip install -e .
cost-router experiment list
cost-router experiment run hero --json     # machine-readable full summary
```

Each experiment page ends with the exact command that reproduces it.

## Experiment list

This repository holds **13 experiments (01–13)** — a projection track (01–08) and a
measured track (09–13). The canonical figures for the projection track are collected
in [offline experiment results](../manual/projection-results.md).

- [Experiment 01 · Try-cheap-first routing](01-hero.md) — 100 synthetic tasks; 25.5% saved while holding a 100% pass rate
- [Experiment 02 · Curated sample](02-curated.md) — five tasks you can follow by eye; 56.7% saved
- [Experiment 03 · the pass-rate cliff](03-coverage-cliff.md) — removing the expensive fallback drops the pass rate from 100% → 67%
- [Experiment 04 · No free lunch](04-no-free-lunch.md) — when only the top model passes, routing saves 0% at a 100% pass rate
- [Experiment 05 · Extra candidate-call cost](05-ensemble-fanout.md) — calling every model still saves 47%, but costs 3.74× as much as the winner alone
- [Experiment 06 · adaptive fan-out threshold](06-fanout-dial.md) — compared with experiment 05, raising one budget threshold keeps the pass rate and savings unchanged while the extra-call ratio falls 3.74× → 0.00× ($0.36 → $0.00)
- **[Experiment 07 · Single-call routing vs observe-then-escalate](07-model-router.md)** ⭐ *Primary comparison* — pick once, like a generic `single-call` arm? A 52% pass rate on synthetic data, while observe-then-escalate routing reaches 100% at comparable cost, a gain of +48 percentage points · *selection is the built-in router's job; verification and governance are this repo's*
- [Experiment 08 · the four-way comparison](08-arena.md) — one problem, four ways (a prototype run)? the router is the cheapest correct answer but the **slowest**, because escalation is sequential (cost and accuracy are offline projections; **latency is an illustrative axis**, not a measurement)

The measured track follows. Experiments 09 and 10 measure 5 curated tasks; experiments
11, 12 and 13 each measure 24 tasks × 4 arms × 3 repeats = 288 planned cells.

- [Experiment 09 · Live routing](09-live-routing-proof.md) — the repository's first live Model Router run and its first **`measured = true`** result. One real `model-router` deployment routed 5 curated prompts to **`gpt-5.4` (3)** and **`grok-4-1-fast-reasoning` (2)** over keyless Entra.
- [Experiment 10 · Measured ledger](10-measured-ledger.md) — experiment 09's run is written to a hash-chained ledger with a sealed rate card; one command re-verifies `PASS`, and **a single edited byte fails**
- [Experiment 11 · Paid router-mode run](11-router-modes-void.md) — the first **paid 4-arm comparison** is **VOID** on two independently sufficient grounds: the quality arm's grading coverage was 79.2%, below the 90% floor, and 43.4% of cells were unpriced. Its **priced-cell total was $3.47 against a $20 budget**, excluding the 125 of 288 withheld cells, so it is not an Azure invoice total. It also recorded quality costing more than premium, Cost mode going 100% to Grok rather than to Claude, and reasoning consuming the output budget.
- [Experiment 12 · Paid router-mode re-run](12-router-modes-measured.md) — Fix A and Fix B from experiment 11 are applied and the same gate is used again. Aggregate grading coverage rises 90.6% → **96.18%**, and the quality arm rises 79.2% → 94.4%, so **all four arms PASS → publishable**. `cost < balanced < premium ≤ quality` holds, and Cost mode is 100% Grok across two runs. $3.27/$20, byte-identical replay, unpriced 0%.
- [Experiment 13 · Paid router-mode run 3](13-router-modes-rate-card-gap.md) — the raised timeout does what its proposal predicted (aggregate grading coverage **96.18% → 99.65%**, every arm at pass rate 1.0, cost order still holding), and the run instead exposes **our own rate card**: 12 Balanced-arm calls were served by `gpt-5.6-terra`, which had no priced row, so that arm is **cost-incomplete** and carries no savings claim. **Priced-cell total $4.20 against a $20 budget**, excluding the 12 withheld `router-balanced` cells.
