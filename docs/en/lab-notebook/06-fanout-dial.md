# Experiment 06 · When is it worth calling several models

!!! abstract "One-line summary"
    Experiment 05 surfaced the ensemble tax — "run everything" costs **[3.74×](../manual/projection-results.md)** the winner. This experiment shows that tax is a **dial**: raise the budget gate's `compare_min_value` by one notch and the number of tasks that fan out drops, so **coverage (100%) and savings (47%) stay put while only the tax** collapses `$0.36 → $0.00`. Using the **same** workload · signals · policy · pricing as experiment 05, only with the dial turned off, experiment 06 (`adaptive`) pins that extreme (zero tax) with a reproducibility contract. All numbers are `measured = false`.

<figure markdown="span">
  ![Adaptive loop animation — a dial rises and folds the parallel fan-out into one](../assets/gif/adaptive.gif)
  <figcaption>Adaptive loop — raise the dial above every task's value and the parallel fan-out folds to one, draining the fan-out tax to zero while the savings stay put.</figcaption>
</figure>

## What this experiment is

- **Situation (when):** right after experiment 05 showed "an ensemble isn't free." The natural next question — *"how much, and how, can we cut that tax without losing coverage or savings?"* When that question needs an honest answer.
- **Task (what):** make the lever that governs the router's fan-out decision — the budget gate `BudgetGate.compare_min_value` (fan out in compare mode if a task's **value** is at or above this threshold, otherwise take a single ordered route) — adjustable **from the experiment config (`budget:`)**, and **sweep** that threshold from low (fan out everything) to high (fan out nothing).
- **Experiment (what it tests):** that while the dial turns, (1) **coverage 100%**, (2) **winner cost $0.13**, and (3) **savings 47%** stay **invariant**, and only (4) the **ensemble tax** collapses `$0.36 → $0.00`. The extreme (zero tax) is pinned by experiment 06 `adaptive`'s reproducibility contract (`max_tax_ratio`).

This is the **sixth honesty**, after 01 · 02 (the gain), 03 (the coverage cliff), 04 (no free lunch), and 05 (the ensemble tax), and it is the **honest fix** for experiment 05: *the fan-out tax is a controllable dial, and on this workload turning the dial off recovers all of it at no loss.*

## What the dial is

For each task `route_task` asks the budget gate: "fan out (compare) or take a single route (ordered)?" The gate picks compare (fan-out) if the task's **value** (derived from `difficulty` · `diff_size_lines` · `class`) is at or above `compare_min_value`, otherwise ordered.

- **Lower the threshold** → more tasks fan out → tax ↑
- **Raise the threshold** → fewer tasks fan out → tax ↓

The experiment config now exposes this lever:

```yaml
budget:
  compare_min_value: 1.1     # above every task value (max 1.0) → never fan out
  min_compare_candidates: 2
```

The per-task values on this workload are as follows (which is why the sweep moves in steps):

| task | class · difficulty | value |
| --- | --- | --- |
| t-0003 | repo_patch · medium | 0.750 |
| t-0007 | plan · hard | 0.850 |
| t-0015 | validate · hard | 0.850 |
| t-0032 | test · hard | 0.850 |
| t-0036 | generate · hard | 0.850 |
| t-0024 | repo_patch · hard | 1.000 |

## Result — the tax is a dial, everything else is invariant

The result of sweeping `compare_min_value` (the very data the dashboard's **fan-out dial** panel plots, on the `cost-router` bundled workload):

| Threshold | Fan-out tasks | Coverage | Savings | Winner cost | Ensemble tax | Ratio |
| --- | --- | --- | --- | --- | --- | --- |
| ≤ 0.75 (fan out all = experiment 05) | 6 / 6 | 100% | 47.0% | $0.13 | **$0.36** | 3.74× |
| 0.76 (excludes the one at 0.75) | 5 / 6 | 100% | 47.0% | $0.13 | $0.22 | 3.17× |
| 0.86 – 1.00 (only the one at 1.0) | 1 / 6 | 100% | 47.0% | $0.13 | $0.12 | 3.03× |
| > 1.00 (fan out none = experiment 06) | 0 / 6 | 100% | 47.0% | **$0.00** | **$0.00** | — |

**Coverage, winner cost, and savings are identical in every cell.** The only thing that moves is the ensemble tax, and turning the dial all the way up makes the tax **exactly 0**.

## Why fan-out is pure tax on this workload

On deterministic offline signals, ordered mode **escalates from the cheapest candidate** and takes the first model that passes. That is the **same winner as the cheapest passing model** compare mode picks after evaluating every candidate. So compare only pays extra to **run the losing candidates** on the way to the same winner — it produces neither a cheaper winner nor higher coverage → **pure tax**.

## Experiment 06 — pinning the extreme with a contract

```bash
cost-router experiment run adaptive
```

```text
before / after  (offline projection over synthetic data; labels.measured=false)
  BEFORE  naive: premium model on every task   $0.25
  AFTER   cost-aware routing                   $0.13
  SAVED   $0.12  (47.0% lower)  at 100.0% coverage

reproducibility  PASS
  PASS  coverage: 100.0% ≥ 100.0%
  PASS  savings: 47.0% ≥ 40.0%
  PASS  tasks: 6 ≥ 6
  PASS  fanout_tax_ceiling: tax 0.00x ≤ 0.01x
```

Exactly the **same** savings and coverage as experiment 05, but a new contract check `fanout_tax_ceiling` pins *"this config must not fan out (tax ≈ 0)."* If someone accidentally lowers the dial and fan-out leaks back in, CI fails on this contract.

!!! note "New capability — a contract beyond two sides"
    Where experiment 04 introduced `max_delta_pct` (a phantom-saving ceiling), experiment 06 introduces `max_tax_ratio` (**a fan-out tax ceiling**). Placing the savings/coverage **floor** and the tax **ceiling** together, CI catches both "inflating to look cheap" and "quietly growing fan-out cost." For the fields, see [experiment config (YAML)](../manual/experiments.md).

## See it in the web app — the fan-out dial panel

We added a **Fan-out dial** panel to the dashboard. It reads the sweep data from `GET /fanout-sweep` (live) or `fanout-sweep.json` (static export):

- **purple bars** = the ensemble tax at each threshold (collapsing 3.74× → 0),
- **green/blue dotted lines** = coverage and savings (flat across the whole dial),
- **table** = the exact numbers for fan-out task count · coverage · savings · tax · ratio.

In other words, it shows the story "the tax comes down but coverage and savings stay put" at a glance.

[See it in the live demo →](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1)

## Reading this number honestly

This experiment shows that *"the fan-out tax is controllable, and on this workload the right move is to turn it off."* But that conclusion is limited to a **deterministic projection** — here best-of-N produces no better winner than ordered escalation. In a real system, ensemble/voting **can raise quality** (this repo does not model that quality gain). So the honest rule is: *before paying the fan-out tax ($0.36, 3.74×), **measure** the quality it buys.* This experiment meters the cost axis, and experiment 05 the size of the tax, providing the material for that judgment.

## When to use this experiment

- When you're deciding whether to turn on ensemble / best-of-N and want to pick the sweet spot by reading "how much to fan out" off a **cost curve**.
- To set a **fan-out tax ceiling** (`max_tax_ratio`) in the reproducibility contract so CI blocks a quiet cost increase.
- To tune the router's fan-out threshold **per workload from config**.

## Reproduce this experiment

```bash
pip install -e .
cost-router experiment run adaptive          # human-readable summary (incl. the zero-tax contract)
cost-router experiment run adaptive --json    # contract checks + fan-out stats
cost-router experiment run ensemble           # the control — same workload, fan out everything (3.74×)
```
