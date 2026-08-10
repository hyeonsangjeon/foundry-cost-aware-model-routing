# Experiment 01 · Cheapest first, escalate only on failure

!!! abstract "One-line summary — this repo's *flagship* experiment"
    Route 100 synthetic-workload tasks cost-aware and you **hold coverage at 100%** while spending **25.5% less** than naive (premium on every task). All numbers are `measured = false`.

<figure markdown="span">
  ![Hero loop animation — a naive lane and a cost-aware lane running side by side](../assets/gif/hero.gif)
  <figcaption>Hero loop — the naive lane sends every task to premium; the cost-aware lane tries the cheapest candidate first and escalates one step only on a failed check.</figcaption>
</figure>

## What this experiment is

- **Situation (when):** the moment you first open the repo and want to confirm, in 30 seconds, that it "actually works." Assume a realistic coding-agent workload of mixed difficulty.
- **Task (what):** route **100** synthetic tasks drawn from five classes — `plan`, `generate`, `test`, `validate`, `repo_patch`.
- **Experiment (what it tests):** whether cost-aware routing lowers cost against naive (always premium) **while holding coverage at 100%**, and whether the result clears the floor of the reproducibility contract (`expect`).

- **Config file:** `experiments/hero.yaml`
- **Data:** 100 synthetic-workload tasks (`--synth`, deterministic signals)
- **Policy / pricing:** bundled seed policy / bundled example pricing
- **Reproducibility contract:** coverage ≥ 100%, savings ≥ 20%, tasks ≥ 100

## Run

```bash
cost-router hero
```

## Result — before / after

```text
before / after  (offline projection over synthetic data; labels.measured=false)
  BEFORE  naive: premium model on every task   $2.23
  AFTER   cost-aware routing                   $1.66
  SAVED   $0.57  (25.5% lower)  at 100.0% coverage
```

| Metric | Value |
| --- | --- |
| Tasks | 100 |
| Coverage | 100.0% |
| Naive cost | $2.23 |
| Routing cost | $1.66 |
| Savings | $0.57 |
| Savings rate | 25.5% |

> Canonical: the headline figures for this experiment are collected in [offline experiment results](../manual/projection-results.md) — on a re-run, that page is the reference.

## Spotlight — a representative task

The accepted task with the largest naive-to-routing ratio, chosen by `spotlight: auto`.

```text
spotlight  t-0078 · validate · clean-first
  routed  mini-fast      $0.0003
  naive   deep-reasoner  $0.0071   (24.1x more)
```

The `validate` task passed cleanly on the first try with the cheapest candidate (`mini-fast`). The naive approach would have spent **24.1×** more by using `deep-reasoner` on the same task.

## Why not "the cheapest bill" — arm comparison

| arm | Coverage | Cost | Note |
| --- | --- | --- | --- |
| cost | **22%** | $0.19 | cheapest, but coverage collapses |
| balanced | 38% | $1.32 | middle |
| quality (naive) | 100% | $2.23 | 100% coverage but maximum cost |
| **cost-aware routing** | **100%** | **$1.66** | holds coverage + saves |

The point is to lower cost while holding coverage. The cheapest arm is cheap, but its coverage collapses to 22%.

## Routing-strategy breakdown

```text
strategy  single-route=74 ensemble=26  |  clean-first=19 compared=18 escalated=55 tie-broken=8
```

- **single-route 74 / ensemble 26** — three-quarters resolve on a single route; the governor promotes the rest to an ensemble.
- **clean-first 19** — the cheapest candidate passed on the first try.
- **escalated 55** — a cheap route failed its check and moved to a higher candidate.
- **compared 18 / tie-broken 8** — ensemble comparison and referee tie-breaks.

## Strata — cost by risk / difficulty

| Risk | Tasks | Cost |
| --- | --- | --- |
| high | 32 | $1.23 |
| moderate | 42 | $0.37 |
| low | 26 | $0.06 |

| Difficulty | Tasks | Cost |
| --- | --- | --- |
| hard | 22 | $0.63 |
| medium | 41 | $0.86 |
| easy | 37 | $0.17 |

Cost concentrates in a handful of high-risk tasks — which is exactly where routing earns its keep.

## Reproducibility self-check

```text
reproducibility  PASS
  PASS  coverage: 100.0% ≥ 100.0%
  PASS  savings: 25.5% ≥ 20.0%
  PASS  tasks: 100 ≥ 100
```

If it fails the contract, `cost-router hero` exits with a non-zero code.

## Reproduce with the audit ledger

```bash
cost-router hero --ledger reports/hero.jsonl
cost-router ledger replay --ledger reports/hero.jsonl   # status: PASS
```

## Reproduce this experiment

```bash
pip install -e .
cost-router hero
# machine-readable full summary:
cost-router hero --json
```
