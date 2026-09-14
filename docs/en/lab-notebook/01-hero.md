# Experiment 01 · Cheapest first, escalate only on failure

!!! abstract "One-line summary — this repo's default cost-and-pass-rate experiment"
    Run 100 synthetic-workload tasks in two ways. Cost-aware routing keeps the **pass
    rate** — the share of tasks solved — at **100%** and costs **25.5% less** than
    sending every task to the premium model.
    All numbers are `measured = false`.

<figure markdown="span">
  ![Default-experiment loop animation — a premium-on-every-task lane and a cost-aware lane running side by side](/foundry-cost-aware-model-routing/assets/gif/hero.gif)
  <figcaption>Default-experiment loop — the premium-on-every-task lane sends every task to premium; the cost-aware lane tries the cheapest candidate first and escalates one step only on a failed check.</figcaption>
</figure>

## What this experiment is

- **Situation (when):** the moment you first open the repo and want to confirm, in 30 seconds, that it "actually works." Assume a realistic coding-agent workload of mixed difficulty.
- **Task (what):** route **100** synthetic tasks drawn from five classes — `plan`, `generate`, `test`, `validate`, `repo_patch`.
- **Experiment (what it tests):** whether cost-aware routing lowers cost against the **premium-on-every-task baseline** — the comparator that sends every task to the most expensive candidate, called the premium baseline from here on — **while holding the pass rate at 100%**, and whether the result clears the floor of the reproducibility criteria (`expect`).

The offline CLI and the experiment contract emit this pass rate under the field name
`coverage` ([glossary](../manual/glossary.md)).

- **Config file:** `experiments/hero.yaml`
- **Data:** 100 synthetic-workload tasks (`--synth`, deterministic signals)
- **Policy / pricing:** bundled seed policy / bundled example pricing
- **Reproducibility criteria:** pass rate ≥ 100%, savings ≥ 20%, tasks ≥ 100

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
| Pass rate | 100.0% |
| Premium-baseline cost | $2.23 |
| Routing cost | $1.66 |
| Savings | $0.57 |
| Savings rate | 25.5% |

> Canonical: the headline figures for this experiment are collected in [offline experiment results](../manual/projection-results.md) — on a re-run, that page is the reference.

## The representative task

The accepted task with the largest premium-baseline-to-routing cost ratio, selected automatically by the config field `spotlight: auto`.

```text
spotlight  t-0078 · validate · clean-first
  routed  mini-fast      $0.0003
  naive   deep-reasoner  $0.0071   (24.1x more)
```

The `validate` task passed cleanly on the first try with the cheapest candidate (`mini-fast`). The premium baseline would have spent **24.1×** more by using `deep-reasoner` on the same task.

## Why not "the cheapest bill" — comparing the arms

An **arm** is one comparison strategy evaluated against the same workload under the same
measurement plan. This experiment scores four of them.

| arm | Pass rate | Cost | Note |
| --- | --- | --- | --- |
| cost | **22%** | $0.19 | cheapest, but the pass rate collapses |
| balanced | 38% | $1.32 | middle |
| quality (premium baseline) | 100% | $2.23 | 100% pass rate but maximum cost |
| **cost-aware routing** | **100%** | **$1.66** | holds the pass rate + saves |

The cheapest arm solves only 22% of the tasks. Cost-aware routing moves to another
model after a failed check and keeps a 100% pass rate at a lower cost than the premium baseline.

## Routing-strategy breakdown

```text
strategy  single-route=74 ensemble=26  |  clean-first=19 compared=18 escalated=55 tie-broken=8
```

- **single-route 74 / ensemble 26** — three-quarters resolve on a single route; the budget gate promotes the rest to an ensemble.
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

High-risk tasks account for most of the cost: they are 32% of the tasks and $1.23 of the
$1.66 total. Routing spends more on those tasks and less on the rest.

## Reproducibility self-check

```text
reproducibility  PASS
  PASS  coverage: 100.0% ≥ 100.0%
  PASS  savings: 25.5% ≥ 20.0%
  PASS  tasks: 100 ≥ 100
```

If it fails the contract, `cost-router hero` exits with a non-zero code.

## Reproduce with the audit ledger

The audit ledger is the hash-chained record of every routing decision, and it can
replay each decision's cost from the stored inputs.

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
