# Experiment 03 · What you lose by using only the cheapest model

!!! abstract "One-line summary"
    "Wouldn't deleting the expensive models entirely save even more?" — the policy built that way looks cheaper on paper, but coverage collapses **100% → 67% (−33%p)**. **Cost is only comparable once coverage is pinned.** All numbers are `measured = false`.

!!! info "Terminology — 'coverage' on this page means pass rate"
    In this experiment, **coverage** means the **pass rate** — the share of tasks that pass (are resolved) (the offline CLI's `coverage` field). It differs from the **grading coverage** (the share of graded cells) used separately in the measured results (experiments 11 · 12 · 03D) → [glossary](../manual/glossary.md).

## What this experiment is

- **Situation (when):** the moment an optimization proposal lands — "wouldn't deleting the expensive fallback model save more?"
- **Task (what):** run a regression comparison of a candidate policy with the expensive fallback deleted (`experiments/policies/cost-cut.yaml`) against the bundled seed policy on the **same shared signals**.
- **Experiment (what it tests):** how badly a naive cost cut breaks coverage (100% → 67%) — that is, why a cost comparison that doesn't pin coverage is meaningless.

This experiment runs in the opposite direction from the previous two. Where experiments 01 · 02 showed *"routing pays off,"* this one honestly exposes **what you lose when routing is mistuned**.

## The tempting "optimization"

The seed policy carries an expensive fallback model (`deep-reasoner`, `premium-max`) for each class. The easiest saving idea is to **just delete them**. Then the router can never escalate to an expensive model, so cost seems bound to drop.

The candidate policy that embodies this idea is [`experiments/policies/cost-cut.yaml`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/experiments/policies/cost-cut.yaml) — it deletes the expensive fallback from `plan`, `validate`, and `repo_patch`.

- **base:** bundled seed policy (`src/policy/seed_policy.yaml`)
- **candidate:** `experiments/policies/cost-cut.yaml` (expensive fallback deleted)
- **evaluation:** 100 synthetic tasks, both policies scored on the **same shared signals** (`--synth`)

## Run

```bash
cost-router policy regression --candidate experiments/policies/cost-cut.yaml --synth
```

## Result — the coverage cliff

```text
regression (candidate vs base):
  tasks: 100 (base 100)
  coverage: 67.0% (base 100.0%, delta -0.3300)
  routed_total_usd: 0.727969 (base 1.659167, delta -0.931198)
  baseline_total_usd: 1.191187
  delta_pct vs baseline: 38.9% (base 25.5%)
```

| Metric | base (seed) | candidate (cost-cut) |
| --- | --- | --- |
| Tasks | 100 | 100 |
| **Coverage** | **100.0%** | **67.0%** (−33%p) |
| Routing cost | $1.66 | $0.73 |

> The hero baseline for this comparison ($2.23 → $1.66, −25.5%) is canonically in [offline experiment results](../manual/projection-results.md).

## Reading this number honestly

The candidate policy's routing cost ($0.73) **is genuinely lower** than base ($1.66). But that isn't a saving — it's **the result of not doing the work**: 33% of tasks lost any model that passes their own checks. With the expensive fallback gone, the "guaranteed clean last candidate" is gone too.

!!! danger "Don't compare delta_pct at face value"
    The report's `delta_pct vs baseline` compares **each policy against its own naive baseline**. Because cost-cut deleted the expensive models, even that baseline drops (`$1.19` vs the seed's `$2.23`). So "38.9% > 25.5%" is **not a better saving** — it is an illusion against a weakened baseline. **A cost comparison that doesn't pin coverage is meaningless.**

This is why the seed policy keeps the expensive fallback. Those models are rarely chosen on most tasks (so they barely affect normal cost), but on a handful of hard tasks they are the **safety net that holds coverage at 100%**. The core claim of cost-aware routing is *"same coverage, lower cost,"* and a saving that breaks coverage doesn't qualify.

## When to use this experiment

- When you want to check for a **coverage regression** before touching a policy.
- When a "let's delete the expensive model" proposal lands and you want to show its cost **in numbers**.
- When explaining to the team that routing isn't a silver bullet but **a tuning of trade-offs**.

!!! note "Use it as a regression guard"
    `cost-router policy regression` also works as a guard that protects policy changes in CI — if a candidate policy drops coverage, it shows up immediately in review. For the field descriptions, see [experiment config (YAML)](../manual/experiments.md) and `cost-router policy regression --help`.

## Reproduce this experiment

```bash
pip install -e .
cost-router policy validate --policy experiments/policies/cost-cut.yaml   # OK
cost-router policy regression --candidate experiments/policies/cost-cut.yaml --synth
```
