# Experiment 02 · Which model the router chose, and why

!!! abstract "One-line summary"
    Run **5 tasks** with hand-written offline signals. Each row shows the chosen
    model, reason, and cost from start to finish. The total is **56.7% lower** than
    naive. All numbers are `measured = false`.

<figure markdown="span">
  ![Curated loop animation — the same escalation ladder applied to five hand-labelled tasks](/foundry-cost-aware-model-routing/assets/gif/curated.gif)
  <figcaption>Curated loop — the same escalation ladder runs over five hand-labelled tasks, adopting a cheap candidate as soon as it passes cleanly.</figcaption>
</figure>

## What this experiment is

- **Situation (when):** the 100-task run is too large to inspect one decision at a
  time, so this experiment uses a small hand-built signal set.
- **Task (what):** route **5 curated tasks** on fixed-fixture signals (`samples/responses/routing-signals.sample.json`).
- **Experiment (what it tests):** confirm each routing decision (class, chosen model, reason, cost) at a human-verifiable scale, and reproduce the saving against naive.

- **Config file:** `experiments/curated.yaml`
- **Data:** curated fixture (`samples/responses/routing-signals.sample.json`)
- **Reproducibility contract:** coverage ≥ 100%, savings ≥ 30%, tasks ≥ 3

## Run

```bash
cost-router experiment run curated
```

## Result — before / after

```text
before / after  (offline projection over synthetic data; labels.measured=false)
  BEFORE  naive: premium model on every task   $0.13
  AFTER   cost-aware routing                   $0.06
  SAVED   $0.07  (56.7% lower)  at 100.0% coverage
```

| Metric | Value |
| --- | --- |
| Tasks | 5 |
| Coverage | 100.0% |
| Naive cost | $0.13 |
| Routing cost | $0.06 |
| Savings rate | 56.7% |

## Spotlight

```text
spotlight  t-0005 · validate · clean-first
  routed  mini-fast      $0.0002
  naive   deep-reasoner  $0.0051   (23.8x more)
```

The cheapest candidate passed the check, so the router stopped there. The naive path
called the more expensive model for the same task.

## When to use this experiment

- When you want the fastest possible check that the repo **actually works** (few tasks, instant run).
- When you want to follow the routing logic by eye on **a small, readable dataset** rather than 100 synthetic tasks.

!!! note "Curated vs Flagship"
    The curated sample's savings rate (56.7%) is larger than [Flagship](../manual/projection-results.md)'s (25.5%) because it has fewer tasks and a different mix. It is a plain example of how **the savings rate depends on workload composition** — which is why the real number has to be measured on your own workload.

## Reproduce this experiment

```bash
pip install -e .
cost-router experiment run curated
cost-router experiment run curated --json
```
