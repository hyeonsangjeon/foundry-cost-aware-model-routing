# Offline experiment results · synthetic data

> **`measured=false` offline experiments.** This page is the **single source of
> truth** that gathers the headline figures of **experiments 01–08** in one place.
> Every value is a **deterministic offline calculation** over a synthetic workload,
> not a measurement of real Azure spend. The measured (`measured=true`) results live
> separately in [Routing-mode measured results · 03D](03d-results.md).

!!! abstract "This page's role — the canonical source for the offline figures"
    The flagship savings, the extra cost of calling every candidate, and the
    single-call gap appear on several pages. When an experiment is run again, updating
    every copy can leave conflicting numbers. This page is the **canonical source for
    these values**. Other pages **link** here instead of maintaining another copy.
    (Stripping the duplicated figures out of the existing pages is a later step.)

!!! warning "How to read this — an offline calculation is not a measurement"
    - **`measured = false`.** An offline calculation over synthetic data. Not measured
      Azure spend.
    - **Deterministic and reproducible.** Each figure replays to the same value at any
      time via the command below (0 billed calls).
    - **A directional signal.** These values show how the design behaves on this
      synthetic workload. They are not a performance guarantee for any specific
      deployment.
    - **Pass rate = offline coverage.** The offline experiments and CLI emit the pass
      rate as the `coverage` field (`accepted / counted`) — the same value. The term is
      defined in the [Glossary](glossary.md).

## At a glance — headline figures

| Metric | Value | Source experiment |
| --- | --- | --- |
| Flagship savings — cost-aware vs `direct-premium` (premium on every task) | **25.5%** ($2.23 → $1.66) | [Experiment 01 · Flagship run](../lab-notebook/01-hero.md) |
| Pass rate (cost-aware routing, 100 synthetic tasks) | **100%** (100/100) | [Experiment 01 · Flagship run](../lab-notebook/01-hero.md) |
| Extra cost from calling every candidate | **3.74×** | [Experiment 05 · Ensemble fan-out](../lab-notebook/05-ensemble-fanout.md) |
| single-call pass-rate gap | **+48%p** (52% → 100%) | [Experiment 07 · Routing layer](../lab-notebook/07-model-router.md) |

The reproduction command for each value is in the sections below. Every value is
`labels.measured = false`. Percentages and dollars follow the display-precision
convention (savings `%.1f%%`, cost `$%.2f`).

## Flagship — same pass rate, lower cost

On a synthetic workload of **100 tasks**, cost-aware routing and the direct-premium
baseline both reach a **100% pass rate**. Calling the premium model on every task costs
$2.23; routing costs $1.66, or **−25.5%**.

```bash
cost-router hero --json        # total_cost·baseline·delta_pct·coverage
```

- **Source:** [Experiment 01 · Flagship run](../lab-notebook/01-hero.md) · config `experiments/hero.yaml`.

## Calling every candidate costs more

An ensemble calls several candidates and keeps one winner. The run still pays for
every candidate, so it costs **3.74×** as much as the winner alone.
Observe-then-escalate reaches the same goal without making all of those calls (see
experiment 06).

```bash
cost-router experiment run ensemble --json     # tax_ratio·fanout stats
```

- **Source:** [Experiment 05 · Ensemble fan-out](../lab-notebook/05-ensemble-fanout.md) · config `experiments/ensemble.yaml`.

## The single-call gap — pick once vs observe and escalate

The `single-call` arm picks a model **once** per prompt and stops. It chooses by
difficulty but has **no escalation**, so it reaches a **52% pass rate** over 100
synthetic tasks. The `cost-aware mix` checks the result and moves up after a failure.
It reaches a **100% pass rate** at **comparable cost** ($1.66 vs $1.59), a gap of
**+48%p**.

```bash
cost-router experiment run single-call --json  # single-call vs mix coverage·cost
```

- **Source:** [Experiment 07 · Routing layer](../lab-notebook/07-model-router.md) · config `experiments/single-call.yaml`.
- This arm is a generic single-call projection over synthetic data (`measured = false`).

---

- **Reproduction:** all three commands above are offline and deterministic and make no
  billed calls. They replay the same values every time from the same workload and
  signals.
- **Honesty label:** every figure on this page is `measured = false` (an offline
  calculation). Measured values are in the [03D measured results](03d-results.md), and
  the honesty boundaries as a whole are in the [Honesty Charter](../honesty.md).
