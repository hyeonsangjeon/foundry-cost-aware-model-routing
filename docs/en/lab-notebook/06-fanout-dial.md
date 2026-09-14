# Experiment 06 · When is it worth calling several models

!!! abstract "One-line summary"
    Experiment 05 showed that "run everything" costs
    **[3.74×](../manual/projection-results.md)** as much as the winner. This experiment
    raises the budget gate's `compare_min_value`, so fewer tasks call every candidate.
    **The pass rate (100%) and savings (47%) stay unchanged while extra-call cost falls
    `$0.36 → $0.00`.** It uses the **same** workload · signals · policy · pricing as
    experiment 05. Experiment 06 (`adaptive`) fixes the zero-extra-call end with
    reproducibility criteria. All numbers are `measured = false`.

<figure markdown="span">
  ![Adaptive loop animation — a threshold rises and folds parallel calls into one](/foundry-cost-aware-model-routing/assets/gif/adaptive.gif)
  <figcaption>Adaptive loop — raise the threshold above every task's value, and each task uses one ordered route. The cost of the extra candidate calls falls to zero while savings stay unchanged.</figcaption>
</figure>

## What this experiment is

- **Situation (when):** right after experiment 05 showed "an ensemble isn't free." The natural next question — *"how much, and how, can we cut that tax without losing passes or savings?"* When that question needs an honest answer.
- **Task (what):** expose `BudgetGate.compare_min_value` in the experiment config
  (`budget:`). Tasks at or above this value use compare mode; tasks below it use one
  ordered route. Run the same workload from a low threshold (fan out everything) to a
  high threshold (fan out nothing).
- **Experiment (what it tests):** while the threshold changes, (1) a **100% pass rate**,
  (2) **routing total cost `total_cost_usd` $0.13**, and (3) **savings 47%** stay
  **invariant**, while (4) extra fan-out cost falls `$0.36 → $0.00`. Experiment 06
  `adaptive` pins the zero-fan-out end with `max_tax_ratio`.

Experiments 01 · 02 show savings, 03 shows a lost pass rate, 04 shows no saving on hard
work, and 05 counts every ensemble call. This experiment changes only the fan-out
threshold and checks whether the result changes compared with experiment 05.

## What the threshold controls

For each task `route_task` asks the budget gate: "fan out (compare) or take a single route (ordered)?" The gate picks compare (fan-out) if the task's **value** (derived from `difficulty` · `diff_size_lines` · `class`) is at or above `compare_min_value`, otherwise ordered.

- **Lower the threshold** → more tasks call every candidate → extra cost ↑
- **Raise the threshold** → fewer tasks call every candidate → extra cost ↓

The experiment config exposes this setting:

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

## Result — extra calls fall while the pass rate and savings stay unchanged

The result of sweeping `compare_min_value` (the very data the dashboard's **fan-out threshold** panel plots, on the `cost-router` bundled workload):

| Threshold | Fan-out tasks | Pass rate | Savings | `winner_usd` (fan-out winners only) | Extra fan-out cost | Ratio |
| --- | --- | --- | --- | --- | --- | --- |
| ≤ 0.75 (fan out all = experiment 05) | 6 / 6 | 100% | 47.0% | $0.13 | **$0.36** | 3.74× |
| 0.76 (excludes the one at 0.75) | 5 / 6 | 100% | 47.0% | $0.13 | $0.22 | 3.17× |
| 0.86 – 1.00 (only the one at 1.0) | 1 / 6 | 100% | 47.0% | $0.13 | $0.12 | 3.03× |
| > 1.00 (fan out none = experiment 06) | 0 / 6 | 100% | 47.0% | **$0.00** | **$0.00** | — |

**Pass rate, routing total cost ($0.13) and savings (47%) are identical in every row.**
Raising the threshold reduces fan-out tasks and makes the extra cost **exactly 0**.

!!! note "The table's `winner_usd` column and the routing total cost $0.13 are different values"
    `fanout_stats`' `winner_usd` sums **only the winner cost of tasks that went to compare
    mode** (`src/router/metrics.py`). So in the last row, where no task fanned out, this
    field's value is **$0.00 by definition** — no cost disappeared. In that row the router
    still picks the same model down a single ordered route, so the **routing total cost
    `total_cost_usd` stays $0.13** and the 47% savings stay with it. The column header
    carries the field name so the two are not read as one quantity.

## Why the extra calls do not help on this workload

On deterministic offline signals, ordered mode starts with the cheapest candidate and
takes the first one that passes. Compare mode evaluates every candidate and selects
that same cheapest passing model. The additional calls produce neither a different
winner nor a higher pass rate on this workload.

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

Savings and pass rate are **the same** as experiment 05. The new
`fanout_tax_ceiling` check pins *"this config must not fan out (tax ≈ 0)."* If the
threshold is lowered and fan-out returns, CI fails this contract.

!!! note "New capability — a contract beyond two sides"
    Experiment 04 introduced `max_delta_pct` to cap reported savings. Experiment 06
    adds `max_tax_ratio` to cap extra candidate-call cost. Together with the
    savings and pass-rate floors, CI catches both "inflating to look cheap" and
    "quietly growing fan-out cost." For the fields, see
    [experiment config (YAML)](../manual/experiments.md).

## See it in the web app — the fan-out threshold panel

We added a **Fan-out threshold** panel to the dashboard. It reads the sweep data from `GET /fanout-sweep` (live) or `fanout-sweep.json` (static export):

- **purple bars** = extra fan-out cost at each threshold ($0.36 → $0.00, a ratio of 3.74× → 0.00×),
- **green/blue dotted lines** = pass rate and savings (unchanged across thresholds),
- **table** = exact fan-out task count · pass rate · savings · extra cost · ratio.

The panel puts exact values behind this experiment's one-line result: the extra-call
cost comes down while the pass rate and savings stay put.

[See it in the live demo →](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1)

## Reading this number honestly

This experiment shows that the **extra candidate-call cost is controllable**, and
on this workload the useful setting is to turn those calls off. That conclusion is
limited to a **deterministic projection**: here best-of-N produces no better winner
than ordered escalation. In a real system, ensemble or voting **can raise quality**,
which this repository does not model. Before paying the extra $0.36 (3.74× the
winner cost), measure the quality it buys. This experiment varies that cost; experiment
05 establishes its size.

## When to use this experiment

- When deciding whether to turn on ensemble / best-of-N and choosing a threshold from
  the **cost curve** for "how much to fan out".
- To set an **extra fan-out cost ceiling** (`max_tax_ratio`) so CI blocks a quiet
  cost increase.
- To tune the router's fan-out threshold **per workload from config**.

## Reproduce this experiment

```bash
pip install -e .
cost-router experiment run adaptive          # human-readable summary (incl. the zero-tax contract)
cost-router experiment run adaptive --json    # contract checks + fan-out stats
cost-router experiment run ensemble           # the control — same workload, fan out everything (3.74×)
```
