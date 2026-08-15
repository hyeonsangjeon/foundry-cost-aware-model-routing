# Preregistration — 03D Model Router mode comparison (curated-24 coding)

**Fixed before any result exists.** This document is committed *before* the paid
live run so that no analysis choice, aggregation, or narrative can be selected
after seeing the numbers. Per BOLT-03 §8 the plan hash binds this file's blob and
commit; a modification after approval invalidates the run.

- **experiment_spec_hash:** `a2c24e082475c064aac30d6dcf7c8a5b0fe1f9a9348605001dd8a11ebb99ebe6`
  (hash of the execution-affecting draft with preregistration fields excluded —
  step 1 of the §8 non-circular order).
- **Resource / endpoint:** `aoai-foundry-iq-demo-ext` (`rg-foundry-iq-demo-ext`),
  `https://aoai-foundry-iq-demo-ext.cognitiveservices.azure.com/`, Entra keyless.
- **Doctor preflight (0 inference, `--check-identity`):** token_acquired = true,
  data_plane_rbac_verified = true, deployment_config_verified = true.
- **Routing-mode evidence:** management-plane GET at api-version
  `2026-07-15-preview` (the only version that surfaces `properties.routing.mode`;
  an absent `routing` block is the Balanced default). Live modes matched the
  approved arms: cost=Cost, balanced=Balanced(absent block), quality=Quality;
  direct = gpt-5.6-sol/2026-07-09.

## Fixed run bindings

```yaml
experiment_spec_hash: a2c24e082475c064aac30d6dcf7c8a5b0fe1f9a9348605001dd8a11ebb99ebe6
workload_fingerprint: sha256:391d2f705e8b52c3826d20d80ef2c37b3c1e8a6eb69e8bd41bb2685ce46c0656
workload_path: benchmarks/original-coding/tasks.jsonl   # curated-24, 24 tasks
rate_card_hash: sha256:54b21e48d64cbcc7f5545a3e2230b4139912a144c6b680861446b9a4c4c4b707
rate_card_path: samples/pricing/foundry-ext-router.yaml  # v2, USD, per-1M-tokens
arm_set:
  - router-cost      # deployment model-router-cost      (routing mode = Cost)
  - router-balanced  # deployment model-router           (routing block absent = Balanced)
  - router-quality   # deployment model-router-quality   (routing mode = Quality)
  - direct-premium   # deployment gpt-5.6-sol/2026-07-09  (non-router baseline)
repetitions: 3               # n=3  -> planned_cells = 24 x 4 x 3 = 288
random_seed: 20260729        # counterbalanced arm order, fixed seed, sequential dispatch
transport_attempts_per_cell: {base: 1, max: 5}   # max_retries=4; not an exact call count
grader: {kind: exec-signals, version: 1}          # deterministic
budget_usd: "20.00"          # hard cap; reaching it stops the run + writes a partial snapshot

quality_gate:
  min_pass_rate: 0.60                 # absolute floor for any arm entering a savings claim
  max_pass_rate_drop_vs_premium: 10   # percentage points (NOT relative %), vs direct-premium
  unit: percentage_points
  evaluate: [per_required_router_arm, aggregate]

estimand:
  analysis_unit: task                 # paired at the task level
  repeat_aggregation: majority_pass_of_n     # a task passes iff >= 2 of 3 repeats pass
  denominator_policy: all_planned_cells_including_missing_and_ungraded
  missing_cell_policy: count_against_grading_coverage_never_dropped
  failure_policy: count_as_zero        # a failed/errored attempt scores 0, never dropped
  cost_per_pass_formula: total_known_cost_usd / passed_tasks
  paired_statistic: task_level_paired_delta_vs_direct_premium   # Wilcoxon signed-rank on paired task deltas
  primary_comparison: task_level
```

## Expected result direction and reasoning (committed before results)

These are predictions, fixed in advance. **They may turn out wrong; recording
them is what prevents fitting a story to the numbers afterward.**

1. **Routers vs direct-premium (cost-per-passed-task).** I expect at least one
   router arm (most likely `router-cost` or `router-balanced`) to achieve a
   **lower** cost-per-passed-task than `direct-premium`, because the Model Router
   should down-route many of the 24 short coding tasks to cheaper underlying
   models while the premium arm always pays the top gpt-5.6-sol rate. This is
   **conditional**: if the router routes heavily to unpriced Claude backends, the
   affected arm becomes cost-incomplete (below) and cannot support a savings
   claim, which would blunt or reverse the expected advantage.

2. **Raw per-call cost ordering across modes.** I expect
   **cost ≤ balanced ≤ quality** in mean per-call cost: Cost mode biases toward
   cheaper models, Quality mode toward stronger/pricier ones, Balanced between.
   `direct-premium` is expected to be the most expensive per call.

3. **Pass rate ordering.** I expect
   **router-cost ≤ router-balanced ≤ router-quality ≤ direct-premium** in task
   pass rate. `direct-premium` (the strongest single model) should have the
   highest pass rate; `router-quality` should be closest among routers;
   `router-cost` is the most at risk of breaching the 10 pp non-inferiority
   margin. I expect all four to clear the 0.60 absolute floor on this curated set,
   but I am least confident about `router-cost`.

4. **Cost-per-pass ordering is genuinely uncertain.** Even though raw cost should
   order cost < balanced < quality, cost-per-pass can invert if a cheaper mode's
   lower pass rate inflates its denominator. My single best guess is that
   `router-balanced` gives the best cost-per-pass (good quality retention at
   materially lower cost), with `direct-premium` the worst (highest price, and a
   near-ceiling pass rate cannot offset the price gap) — **unless** routers incur
   unpriced Claude cells and are excluded.

5. **A negative result is a real possibility and is acceptable.** If markup
   (0.14/1M input) plus underlying-model rates exceed premium's effective rate on
   these short tasks, or if unpriced routing removes too many cells, the routers
   may show **no** cost advantage. That outcome will be reported as-is.

## Failure / invalidation criteria (fixed in advance)

The run is reported regardless of direction. The following bound what may be
**claimed** from it, and what voids the comparison entirely:

- **Run-level invalidation (comparison void, partial snapshot still reported):**
  - Grading coverage < **90%** of planned cells for any required arm (too many
    missing/errored/never-dispatched cells to trust that arm's comparison).
  - The run aborts on the $20.00 budget before completing ≥ **90%** of planned
    cells (truncated sweep → partial, non-publishable comparison).
  - 429/timeout attrition that prevents ≥ 90% graded coverage after the fixed
    retry policy (base 1, max 5 transport attempts/cell) is exhausted.
- **Savings-claim blocked for an arm (arm still reported):**
  - The arm is **cost-incomplete** — it has ≥ 1 unpriced cell (see below). Per
    the 03B/03Z-b fail-closed contract, only cost-complete arms enter the savings
    comparison, so *any* unpriced cell blocks that arm's savings claim.
  - The arm fails the quality gate: pass_rate < 0.60, or pass-rate drop vs
    `direct-premium` > 10 percentage points.
  - Effective-parameter divergence marks the comparison `confounded=true`
    (per §10) — blocks the savings claim for the affected arm(s).
- **Reported diagnostics (not gates):** per-arm unpriced fraction, 429 count,
  timeout count, budget consumed, graded coverage.

## Unpriced-cell handling (fail-closed, 03Z-b preserved)

- A cell whose router-resolved backend has **no pinned rate** in the v2 card
  (the 5 Claude models are absent from Azure Retail and therefore omitted, plus
  any other unpriced backend) has its cost **withheld**: `cost_usd = null`, never
  0.0 and never a guessed/default rate.
- The attempt is still **graded** — grading is independent of pricing — so an
  unpriced cell contributes to pass rate but is **excluded from cost and
  cost-per-pass**. An arm with any unpriced cell is `cost_complete = false` and
  is **excluded from savings claims** entirely (no partial cost is fabricated).
- The **per-arm unpriced fraction is reported** so the reader can see how much of
  a router arm's traffic went to backends this card cannot price.
- Reservation before dispatch is bounded by the $20.00 budget cap (a router's
  pick is unknown pre-call, so the cell is reserved against the cap, not a
  per-cell guess); settlement withholds unpriced amounts as above.

## §8 hash order (recorded for verification)

1. `experiment_spec_hash` computed over the execution draft with preregistration
   fields excluded → `a2c24e082475c064aac30d6dcf7c8a5b0fe1f9a9348605001dd8a11ebb99ebe6`.
2. This file committed as its own commit (timestamp = preregistration evidence).
3. Clean tracked blob + commit resolved from git.
4. Final `plan_hash` recomputed with the committed preregistration evidence bound
   into the resolved plan; that hash is what `benchmark run --approve-plan` checks.

## Errata — implementation facts, appended after the run (2026-08-15)

**This section is an append. Not one character above it was changed.** The
predictions, gates, and invalidation criteria stand exactly as committed before
the results existed, for the same reason experiment 11's VOID verdict was never
deleted. The approved bytes stay retrievable:

```
git show 1f0a334104d50dc74116a20071dffb3fa4b3d66a:benchmarks/original-coding/prereg-03d-router-modes.md
```

That is blob `2b9afe6706c7070ecdd4dffbe7e39814ff481e7a` — the object the approved
plan pinned. Git blobs are content-addressed, so this append cannot reach it. It
does change the *working-tree* blob of this file: the pinned object is the record,
this file is the record plus a note.

### What this document claimed

Line 35, verbatim:

```yaml
random_seed: 20260729        # counterbalanced arm order, fixed seed, sequential dispatch
```

### What the implementation actually was

Verified at commit `f2d6f08694e4eabd46d111c7d9d53e48a4802ec6`.

| The comment said | What the code does |
|---|---|
| *counterbalanced arm order* | **No counterbalancing exists.** No rotation, Latin square, or per-task arm permutation appears anywhere in the repository. `measure.py:1407` walks `candidates` in the order the `arms:` list gives them (`run_plan.py` `candidates()` builds that list in plan order and never sorts it), identically on every task and every repeat. |
| *fixed seed* | **No seed reaches the model API.** `random_seed` has exactly one writer (`run_plan.py:909`) and no reader on the execution path; its only effect is that it sits in `execution`, so it salts `plan_hash`. Neither request surface carries a seed — `foundry_live.py:565-568` sends `model`, `messages`, `max_completion_tokens`; `foundry_live.py:586-589` sends `model`, `messages`, `max_tokens`. |
| *sequential dispatch* | **Accurate.** `measure.py:1404-1407` dispatches one cell at a time, task-major → then repeat → then arm. That order is deterministic, and it never consults `random_seed`. |

Two further facts the comment implies but that do not hold:

- **This repository does not fix the sampling temperature.**
  `AzureModelRouterClient.temperature` defaults to `None` (`foundry_live.py:520`)
  and the kwarg is sent only when it is not `None` (`foundry_live.py:570-571`).
  No construction site in `src/`, `scripts/`, or `tests/` sets it, so the
  parameter is never sent: the service default applies, and this repository
  neither pins that value nor records what it was.
- **`max_output_tokens` is the only request parameter that comes from the plan**
  (`run_plan.py:900`, read at `cli.py:2722`).

### Does any recorded figure change?

**No. No number moves, and no number was ever derived from either claim.**

- Every recorded cell outcome, cost, and coverage figure is a direct measurement
  of what actually executed. What executed was the deterministic task-major
  order — the same order a reader would infer from "sequential dispatch" alone.
  Nothing was recomputed under an assumption of counterbalancing or of a seeded
  RNG, because no code path reads either.
- This run was **VOID** for an unrelated, separately recorded reason (43.4% of
  cells unpriced under the fail-closed pricing guard). This errata neither
  revives the run nor changes why it was voided.

**What was actually lost is a control, not a number.** "Counterbalanced arm order"
asserted that order effects were neutralized by design. They were not: arm
position was constant across every task and every repeat, so an order effect here
is *uncontrolled* rather than *balanced out*. "Fixed seed" asserted a
reproducibility property this stack cannot deliver: with no seed on the wire, the
service choosing the backend, and the sampling temperature left at the service
default, re-executing this plan is not expected to reproduce these outputs. What
*is* byte-reproducible is the sealed artifact set, and `measure replay` re-verifies
it against the recorded fingerprints.
