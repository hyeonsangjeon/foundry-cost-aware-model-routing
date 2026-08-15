# Preregistration — 03D-2 Model Router mode comparison, re-run (curated-24 coding)

**Fixed before any 03D-2 result exists.** This is a **separate document** from the
first-run preregistration
([`prereg-03d-router-modes.md`](prereg-03d-router-modes.md)), which governed the
run that was **voided** (model-router-quality grading coverage 79.2% < 90%; see
lab-notebook 실험 11). This re-run applies two configuration fixes and re-commits
predictions *before* re-executing. Per BOLT-03 §8 the plan hash binds this file's
blob and commit; a modification after approval invalidates the run.

> **The failure/invalidation gates below are UNCHANGED from the first run.**
> Only the *predictions* are updated, using what the void run measured. The gates
> (coverage 90%, min_pass 0.60, max_drop 10 pp, budget \$20) are **not relaxed**
> after seeing the void results — relaxing a gate to rescue a prior outcome is
> exactly what preregistration exists to prevent.

- **experiment_spec_hash:** `54d54a6c76dbb09e81c6d6cece42ae1f21e627215ed2ca21b47583cfecec089b`
  (hash of the execution-affecting draft with preregistration fields excluded —
  step 1 of the §8 non-circular order; supersedes the first run's
  `a2c24e08…` because the rate card and `max_output_tokens` changed).
- **Resource / endpoint:** `aoai-foundry-iq-demo-ext` (`rg-foundry-iq-demo-ext`),
  `https://aoai-foundry-iq-demo-ext.cognitiveservices.azure.com/`, Entra keyless.
- **Routing-mode evidence:** management-plane GET at api-version
  `2026-07-15-preview` (the only version that surfaces `properties.routing.mode`;
  an absent `routing` block is the Balanced default). Live modes matched the
  approved arms: cost=Cost, balanced=Balanced(absent block), quality=Quality;
  direct = gpt-5.6-sol/2026-07-09.

## What changed since the voided first run (and why)

Two fixes, both derived from the void run's telemetry, each changing the plan hash:

1. **Rate card — Grok cached-input rate pinned.** `grok-4-1-fast.cached` moved
   `null → 0.2` (= its input rate). The void run routed 125/288 cells to
   `grok-4-1-fast-reasoning`, all of which returned cached input tokens; with
   `cached: null` the `composite_cost` cached-token fail-closed guard withheld
   cost on every one, leaving router-cost/router-balanced cost-incomplete. An
   Azure Retail lookup on 2026-08-06 (`contains(meterName,'Grok') AND
   contains(meterName,'Cach')`) returned **0 rows across all regions** — there is
   no Grok cache-discount SKU, so cached input bills at the standard input meter.
   Pinning `cached = input` is sourced from that absence, **not guessed**.
2. **`max_output_tokens` 2048 → 8192.** In the void run, 20 OpenAI-reasoning cells
   (9 `gpt-5`, 6 `gpt-5.5`, 5 `gpt-5.6-sol`) spent the entire 2048-token budget on
   reasoning and emitted **no final code** (output=0 → ungraded), which drove
   model-router-quality coverage to 79.2%. The only *uncapped* evidence
   (`grok-4-1-fast` reasoning reached 5,400 tokens) sizes the demand; 8192 gives
   headroom for ~5,400 reasoning + output on these short tasks.

## Fixed run bindings

```yaml
experiment_spec_hash: 54d54a6c76dbb09e81c6d6cece42ae1f21e627215ed2ca21b47583cfecec089b
workload_fingerprint: sha256:391d2f705e8b52c3826d20d80ef2c37b3c1e8a6eb69e8bd41bb2685ce46c0656
workload_path: benchmarks/original-coding/tasks.jsonl   # curated-24, 24 tasks (unchanged)
rate_card_hash: sha256:ff6f5378e14d4e78fa50488c6e0dafa7564dbe0293dcc9e6ea9b4411946919c3
rate_card_path: samples/pricing/foundry-ext-router.yaml  # v2, USD, per-1M-tokens (Grok cached now pinned)
arm_set:
  - router-cost      # deployment model-router-cost      (routing mode = Cost)
  - router-balanced  # deployment model-router           (routing block absent = Balanced)
  - router-quality   # deployment model-router-quality   (routing mode = Quality)
  - direct-premium   # deployment gpt-5.6-sol/2026-07-09  (non-router baseline)
repetitions: 3               # n=3  -> planned_cells = 24 x 4 x 3 = 288
max_output_tokens: 8192      # raised from 2048 (see change 2 above); bounds reasoning+output
random_seed: 20260729        # counterbalanced arm order, fixed seed, sequential dispatch
transport_attempts_per_cell: {base: 1, max: 5}   # max_retries=4; not an exact call count
grader: {kind: exec-signals, version: 1}          # deterministic
budget_usd: "20.00"          # hard cap; reaching it stops the run + writes a partial snapshot

quality_gate:                # IDENTICAL to the first run — not relaxed
  min_pass_rate: 0.60                 # absolute floor for any arm entering a savings claim
  max_pass_rate_drop_vs_premium: 10   # percentage points (NOT relative %), vs direct-premium
  unit: percentage_points
  evaluate: [per_required_router_arm, aggregate]

estimand:                    # IDENTICAL to the first run
  analysis_unit: task                 # paired at the task level
  repeat_aggregation: majority_pass_of_n     # a task passes iff >= 2 of 3 repeats pass
  denominator_policy: all_planned_cells_including_missing_and_ungraded
  missing_cell_policy: count_against_grading_coverage_never_dropped
  failure_policy: count_as_zero        # a failed/errored attempt scores 0, never dropped
  cost_per_pass_formula: total_known_cost_usd / passed_tasks
  paired_statistic: task_level_paired_delta_vs_direct_premium   # Wilcoxon signed-rank on paired task deltas
  primary_comparison: task_level
```

## Expected result direction and reasoning (committed before 03D-2 results)

These predictions are **updated from the first run using what the void run
measured** — the point of re-committing is that they may again be wrong, and
recording them prevents fitting a story to the re-run's numbers. Where a first-run
prediction was falsified, the new prediction says so explicitly.

1. **Coverage recovery is the primary thing expected to change.** With
   `max_output_tokens = 8192`, I expect the OpenAI-reasoning cells that previously
   truncated at 2048 to now emit final code, so **every required arm's grading
   coverage clears 90%** — specifically model-router-quality, which was the sole
   arm that voided the first run at 79.2%. If quality still falls < 90%, 8192 was
   insufficient and the re-run voids again (reported as-is, not rescued).

2. **Raw per-call cost ordering — first-run prediction was WRONG, updated.** The
   first run predicted `cost ≤ balanced ≤ quality`, with `direct-premium` the most
   expensive. Measured, **quality (\$1.79) exceeded direct-premium (\$1.42)**. I now
   expect **cost < balanced < direct-premium ≤ quality**: Quality mode's premium
   sub-model picks plus longer 8192-token outputs make it the **most expensive**
   arm, not premium. Absolute costs for all arms should rise vs the void run
   because the higher cap lets more reasoning/output tokens bill.

3. **Grok dominance persists; Cost/Balanced become cost-complete.** The void run
   routed **100% of Cost-mode** cells and 77.8% of Balanced cells to
   `grok-4-1-fast-reasoning`; the workload, seed, and deployments are unchanged, so
   I expect the **same routing behavior**. Because Grok cached input is now priced
   (change 1), I expect **router-cost and router-balanced to be cost-complete for
   the first time** (≈ 0 unpriced cells; the void run had ZERO Claude cells, and
   every other routed backend — gpt-5, gpt-5.5, gpt-5.4, gpt-5.6-sol — is already
   card-covered). router-cost should be the **cheapest** arm.

4. **Pass-rate ordering — void figures were confounded; expect quality to recover.**
   The void run's pass rates (cost 95.8%, balanced 95.8%, quality **79.2%**,
   premium 91.7%) were distorted by the reasoning-cap output loss, which hit
   quality hardest (15 of its cells emitted no code). With the cap fixed I expect
   **quality's pass rate to recover into the ~90%+ range** and be at or near the
   top, with all four arms clearing the 0.60 floor and router-cost the one most at
   risk of the 10 pp non-inferiority margin. I am **least confident** here because
   it depends on how the recovered cells actually grade.

5. **A savings claim is now possible — best guess, still uncertain.** Unlike the
   first run (cost/balanced cost-incomplete, quality void), I expect the re-run to
   yield cost-complete cost and balanced arms. My single best guess is that
   **router-cost gives the best cost-per-pass** (cheap Grok routing + high pass
   rate) and **direct-premium the worst** (top price, near-ceiling pass rate cannot
   offset the gap). This can still invert if a cheaper mode's pass rate drops, or
   if any arm re-acquires unpriced cells. A null or reversed result is acceptable
   and will be reported as-is.

## Failure / invalidation criteria (fixed in advance — UNCHANGED from first run)

Identical to [`prereg-03d-router-modes.md`](prereg-03d-router-modes.md). Repeated
here verbatim so approval binds them; **not weakened** after the void.

- **Run-level invalidation (comparison void, partial snapshot still reported):**
  - Grading coverage < **90%** of planned cells for any required arm.
  - The run aborts on the \$20.00 budget before completing ≥ **90%** of planned cells.
  - 429/timeout attrition that prevents ≥ 90% graded coverage after the fixed
    retry policy (base 1, max 5 transport attempts/cell) is exhausted.
- **Savings-claim blocked for an arm (arm still reported):**
  - The arm is **cost-incomplete** — it has ≥ 1 unpriced cell. Per the 03B/03Z-b
    fail-closed contract, any unpriced cell blocks that arm's savings claim.
  - The arm fails the quality gate: pass_rate < 0.60, or pass-rate drop vs
    `direct-premium` > 10 percentage points.
  - Effective-parameter divergence marks the comparison `confounded=true` (per
    §10) — blocks the savings claim for the affected arm(s).
- **Reported diagnostics (not gates):** per-arm unpriced fraction, 429 count,
  timeout count, budget consumed, graded coverage, and — new for 03D-2 — the
  count of cells that still hit the raised `max_output_tokens` cap with no output.

## Unpriced-cell handling (fail-closed, 03Z-b preserved — UNCHANGED)

- A cell whose router-resolved backend has **no pinned rate** in the v2 card has
  its cost **withheld**: `cost_usd = null`, never 0.0 and never a guessed/default
  rate. Pinning Grok's cached rate (change 1) removes the *known* unpriced cause
  from the void run; it does **not** weaken this contract — any backend still
  absent from the card (e.g. the 5 Claude models, which took 0 cells last time)
  fails closed exactly as before.
- The attempt is still **graded** — grading is independent of pricing — so an
  unpriced cell contributes to pass rate but is **excluded from cost and
  cost-per-pass**. An arm with any unpriced cell is `cost_complete = false` and
  **excluded from savings claims** entirely.
- The **per-arm unpriced fraction is reported**. I expect it to be ~0 this run;
  if it is not, that is a reported finding, not a rate to be guessed.
- Reservation before dispatch is bounded by the \$20.00 budget cap; settlement
  withholds unpriced amounts as above.

## §8 hash order (recorded for verification)

1. `experiment_spec_hash` computed over the execution draft with preregistration
   fields excluded → `54d54a6c76dbb09e81c6d6cece42ae1f21e627215ed2ca21b47583cfecec089b`.
2. This file committed as its own commit (timestamp = preregistration evidence).
3. Clean tracked blob + commit resolved from git.
4. Final `plan_hash` recomputed with the committed preregistration evidence bound
   into the resolved plan; that hash is what `benchmark run --approve-plan` checks.

## Errata — implementation facts, appended after the run (2026-08-15)

**This section is an append. Not one character above it was changed.** The
predictions, gates, and invalidation criteria stand exactly as committed before
the results existed. This document is the preregistration of the **publishable**
re-run, so it is the one whose figures reach the site; that is the reason to add
the note here rather than quietly fix a comment. The approved bytes stay
retrievable:

```
git show ea3a55165dd0cfaccbe965019b7197e4675b78ca:benchmarks/original-coding/prereg-03d2-router-modes.md
```

That is blob `4158ca8ab1b5cda4290e289c1d27a68114e58e9a` — the object the approved
plan pinned. Git blobs are content-addressed, so this append cannot reach it. It
does change the *working-tree* blob of this file: the pinned object is the record,
this file is the record plus a note.

### What this document claimed

Line 64, verbatim:

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
  (`run_plan.py:900`, read at `cli.py:2722`). This run did change that value
  (2048 → 8192, change 2 above), and that change is real and did reach the wire.

### Does any recorded or published figure change?

**No.** The published savings figure from this run and every per-arm cost,
coverage, and pass-rate number are unchanged.

- Those numbers are direct measurements of executed cells, divided by other
  direct measurements. Neither counterbalancing nor a seed appears anywhere in
  how a cost, a coverage ratio, or a pass rate is computed, so there is no
  recomputation to do.
- The dispatch order that executed was the deterministic task-major order. No
  result was derived by assuming a different one.
- The gate outcomes and the pass/fail verdict of this preregistration are decided
  by the coverage, pass-rate, and cost-order criteria fixed above. None of them
  reads a seed or an arm ordering.

**What was actually lost is a control, not a number.** "Counterbalanced arm order"
asserted that order effects were neutralized by design. They were not: arm
position was constant across every task and every repeat, so an order effect in
this run is *uncontrolled* rather than *balanced out*. "Fixed seed" asserted a
reproducibility property this stack cannot deliver: with no seed on the wire, the
service choosing the backend, and the sampling temperature left at the service
default, re-executing this plan is not expected to reproduce these outputs. The
published pages for this run already say the routing mix is not a fixed property
of a mode and varies run to run — that caveat is the honest form of what the
"fixed seed" comment wrongly promised. What *is* byte-reproducible is the sealed
artifact set, and `measure replay` re-verifies it against the recorded
fingerprints.
