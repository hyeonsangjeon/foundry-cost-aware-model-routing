# Lab notebook — introduction and methodology

This lab notebook records the **methods, numbers, and reproduction steps** for the
experiments actually run in this repository. The point of a lab notebook is not
marketing numbers but letting anyone reach **the same results** with the same
commands.

!!! tip "New here? Start with the [story arc](story-arc.md)"
    To read experiments 01–07 as **one story**, start with the [story arc](story-arc.md)
    — it holds the one-sentence thesis, the journey table, the three-act
    narrative, the [experiment 08 arena](08-arena.md) epilogue, and the axis of
    honesty. This page (introduction and methodology) covers the **shared
    methodology and metric definitions** beneath it.

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
  `max_delta_pct` **ceiling** (a two-sided contract), so an inflated **phantom
  saving** trips the run too — see [experiment 04](04-no-free-lunch.md). You can go
  further and cap the **fan-out tax** with `max_tax_ratio` — see
  [experiment 06](06-fanout-dial.md). And `min_escalation_gain` sets a **floor on
  escalation gain**, guarding that observe-then-escalate really buys more coverage
  than single-call routing does — see [experiment 07](07-model-router.md).

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
    × coverage (y) scatter**. Only mix lands in the upper-left "win-win" corner
    (full coverage + low cost); `all-ensemble` (fan out everything) reaches 100%
    coverage but sits in the **most expensive** corner off the frontier; and
    `single_call` (a single-call routing layer) sits below the corner at **low
    coverage** — see it for yourself in the
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
- [Experiment 03 · Coverage cliff](03-coverage-cliff.md) — delete the expensive model? coverage 100% → 67% (an honest counterexample)
- [Experiment 04 · No free lunch](04-no-free-lunch.md) — a workload where only the top model passes? 0% saved, 100% coverage (routing's limit)
- [Experiment 05 · Ensemble fan-out tax](05-ensemble-fanout.md) — ensemble every model? 47% saved, but the fan-out is 3.74× the winner (a hidden tax + Foundry metrics)
- [Experiment 06 · Adaptive fan-out dial](06-fanout-dial.md) — turn that tax down? one budget-gate dial holds coverage and savings flat while the tax drops 3.74× → 0 (the honest fix for experiment 05)
- **[Experiment 07 · Routing layer](07-model-router.md)** ⭐ *centerpiece* — pick once, like a generic `single-call` arm? 52% coverage on synthetic data (the observe-then-escalate mix reaches 100% at comparable cost, +48%p) · *selection is the built-in router's job; verification and governance are this repo's*
- [Experiment 08 · Arena](08-arena.md) — one problem, four ways (a prototype run)? the router is the cheapest correct answer but the **slowest**, because escalation is sequential (cost and accuracy are offline projections; **latency is a new illustrative projection**)
- [Experiment 09 · Live routing](09-live-routing-proof.md) — wired to real Foundry, what does the router **actually** pick? a single `model-router` deployment really forks to **`gpt-5.4` (3)** and **`grok-4-1-fast-reasoning` (2)** (the repo's first **`measured = true`**, keyless Entra)
- [Experiment 10 · Measured ledger](10-measured-ledger.md) — make that measured spend impossible to edit later? seal the live run into a canonical ledger that is **tamper-evident (hash chain) + cost-replayable (sealed rate card)**, re-verified to `PASS` in one line — **a single edited byte fails**, and the offline ledger is immutable
- [Experiment 11 · Paid router-mode run](11-router-modes-void.md) — do the three modes really separate cost and quality? the repo's first **paid 4-arm comparison ($3.47/$20)** is **VOID** by the preregistration I committed in advance — quality grading coverage 79.2% < 90%. Predictions overturned (quality > premium) + Grok 100% (not Claude) + reasoning swallowing the output. **A negative result kept as an asset by discipline**
- [Experiment 12 · Paid router-mode re-run](12-router-modes-measured.md) — fix only the two causes experiment 11 identified (Fix A/B) and **re-run on the same gate**? grading coverage recovers 79.2% → **96.18%**, and **all four arms PASS → publishable**. The updated prediction `cost < balanced < premium ≤ quality` **holds**, and Cost is 100% Grok — **reproduced across two runs**. $3.27/$20, byte-identical replay, unpriced 0% — **the same gate twice, with no loosening**
