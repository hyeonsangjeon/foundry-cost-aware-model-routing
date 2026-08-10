# Experiment 02 · Which model the router chose, and why

!!! abstract "One-line summary"
    Route **5 tasks** carrying hand-written offline signals and you can read the routing decisions from start to finish, watching each one by eye. **56.7% lower** cost than naive. All numbers are `measured = false`.

<figure markdown="span">
  ![Curated loop animation — the same escalation ladder applied to five hand-labelled tasks](../assets/gif/curated.gif)
  <figcaption>Curated loop — the same escalation ladder runs over five hand-labelled tasks, adopting a cheap candidate as soon as it passes cleanly.</figcaption>
</figure>

## What this experiment is

- **Situation (when):** 100 synthetic tasks are hard to follow by eye. When you want to validate the routing logic by reading each decision on a small, hand-built set of signals.
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
