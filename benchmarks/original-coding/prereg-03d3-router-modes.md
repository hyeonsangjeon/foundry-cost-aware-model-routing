# Preregistration — 03D-3 Model Router mode comparison, Fix C re-run (curated-24 coding)

**Fixed before any 03D-3 result exists.** This is a **separate document** from the
preregistrations of the voided first run
([`prereg-03d-router-modes.md`](prereg-03d-router-modes.md)) and of the publishable
re-run ([`prereg-03d2-router-modes.md`](prereg-03d2-router-modes.md), `plan_hash
d640dc07`). This run applies **Fix C**
([`fix-c-timeout-proposal.md`](fix-c-timeout-proposal.md)) and re-commits
predictions *before* re-executing. Per BOLT-03 §8 the plan hash binds this file's
blob and commit; a modification after approval invalidates the run.

> **The failure/invalidation gates below are UNCHANGED from the first and second
> runs.** Only the *predictions* are updated, using what 03D-2 measured. The gates
> (coverage 90%, min_pass 0.60, max_drop 10 pp, budget \$20) are **not relaxed**
> after seeing 03D-2's results — relaxing a gate to rescue or extend a prior
> outcome is exactly what preregistration exists to prevent.

> **03D-2 is not invalidated by this run.** 03D-2 remains publishable as measured.
> See "Change 2" below: its *configured* transport cutoffs (90/120) were identical
> to the client's hardcoded defaults, so its sealed plan and its effective
> behavior agreed. 03D-3 supersedes it only as the Fix C follow-up.

- **experiment_spec_hash:** `cffaac91316e370c1ec5316b1679df01a81ace958911e01c5baaccd88b389dff`
  (hash of the execution-affecting draft with preregistration fields excluded —
  step 1 of the §8 non-circular order; supersedes 03D-2's `54d54a6c…` because the
  transport read/overall timeouts changed). The same computation reproduces
  03D-2's recorded `54d54a6c…` from the 90/120 draft, so the convention is
  verified rather than asserted.
- **Resource / endpoint:** `aoai-foundry-iq-demo-ext` (`rg-foundry-iq-demo-ext`),
  `https://aoai-foundry-iq-demo-ext.cognitiveservices.azure.com/`, Entra keyless.
- **Routing-mode evidence:** management-plane GET at api-version
  `2026-07-15-preview` (the only version that surfaces `properties.routing.mode`;
  an absent `routing` block is the Balanced default). Arms to be re-verified live
  by `doctor --check-identity` immediately before approval: cost=Cost,
  balanced=Balanced(absent block), quality=Quality; direct = gpt-5.6-sol/2026-07-09.

## What changed since 03D-2 (and why)

Two changes. Only the first is a knob; the second is the wiring defect that made
the first meaningless, found while preparing this run.

1. **Fix C — transport read/overall timeouts raised.** `read_timeout_seconds`
   90 → **180**, `overall_timeout_seconds` 120 → **240**;
   `connect`/`write`/`pool` unchanged at 10/30/10. 03D-2 completed 288/288 but
   **11 cells (3.8%) failed HTTP 408**, every one of them registering
   90.0–90.7 s — i.e. all hit the **read** limit and none reached the 120 s
   overall limit, making `read_timeout_seconds` the single binding knob. The
   timeouts fell **only on router arms** (cost 4, balanced 3, quality 4,
   direct-premium 0), whose reasoning backends run 2–3× the premium arm's tail.
   The slowest *successful* call was **81.8 s** — successful cells ran right up
   to the 90 s wall. 180 s is ≈ 2.2× that and 2.4× the p99 of 74.8 s. This is the
   proposal document's primary recommendation; its conservative alternative
   (150/200) was **not** selected.

2. **The plan's transport cutoffs now actually reach the socket.** Until this
   run, `benchmark run --live` constructed the live client without passing the
   plan's timeouts, so `AzureModelRouterClient` fell back to the hardcoded
   `TransportTimeouts()` defaults (read 90 / overall 120) while the configured
   values were still bound into `plan_hash` and sealed into the manifest. Fix C
   would therefore have been recorded as applied and had **no effect on any
   call**. Fixed in `src/router/cli.py` (`_live_measure_client`, passing
   `TransportTimeouts.from_retry(plan.execution["retry"])`) with a regression
   test in `tests/test_live_config.py`. **This does not change `plan_hash`** —
   the resolved plan is config-derived and the code path is not hashed — so it is
   recorded here as execution-affecting evidence instead. For 03D-2 the
   configured values coincided with the defaults, so its results are unaffected.

## Fixed run bindings

```yaml
experiment_spec_hash: cffaac91316e370c1ec5316b1679df01a81ace958911e01c5baaccd88b389dff
workload_fingerprint: sha256:391d2f705e8b52c3826d20d80ef2c37b3c1e8a6eb69e8bd41bb2685ce46c0656
workload_path: benchmarks/original-coding/tasks.jsonl   # curated-24, 24 tasks (unchanged)
rate_card_hash: sha256:ff6f5378e14d4e78fa50488c6e0dafa7564dbe0293dcc9e6ea9b4411946919c3
rate_card_path: samples/pricing/foundry-ext-router.yaml  # v2, USD, per-1M-tokens (unchanged)
arm_set:
  - router-cost      # deployment model-router-cost      (routing mode = Cost)
  - router-balanced  # deployment model-router           (routing block absent = Balanced)
  - router-quality   # deployment model-router-quality   (routing mode = Quality)
  - direct-premium   # deployment gpt-5.6-sol/2026-07-09  (non-router baseline)
repetitions: 3               # n=3  -> planned_cells = 24 x 4 x 3 = 288
max_output_tokens: 8192      # unchanged from 03D-2
random_seed: 20260729        # fixed seed, sequential dispatch
transport_attempts_per_cell: {base: 1, max: 5}   # max_retries=4; not an exact call count
transport_timeouts:          # THE CHANGE (seconds)
  connect: 10
  read: 180                  # was 90
  write: 30
  pool: 10
  overall: 240               # was 120
grader: {kind: exec-signals, version: 1}          # deterministic
budget_usd: "20.00"          # hard cap; reaching it stops the run + writes a partial snapshot

quality_gate:                # IDENTICAL to the first and second runs — not relaxed
  min_pass_rate: 0.60                 # absolute floor for any arm entering a savings claim
  max_pass_rate_drop_vs_premium: 10   # percentage points (NOT relative %), vs direct-premium
  unit: percentage_points
  evaluate: [per_required_router_arm, aggregate]

estimand:                    # IDENTICAL to the first and second runs
  analysis_unit: task                 # paired at the task level
  repeat_aggregation: majority_pass_of_n     # a task passes iff >= 2 of 3 repeats pass
  denominator_policy: all_planned_cells_including_missing_and_ungraded
  missing_cell_policy: count_against_grading_coverage_never_dropped
  failure_policy: count_as_zero        # a failed/errored attempt scores 0, never dropped
  cost_per_pass_formula: total_known_cost_usd / passed_tasks
  paired_statistic: task_level_paired_delta_vs_direct_premium   # Wilcoxon signed-rank on paired task deltas
  primary_comparison: task_level
```

## What 03D-2 measured (the baseline these predictions are updated from)

| arm | total cost | pass rate | \$/pass | grading coverage | timeouts |
| --- | ---: | ---: | ---: | ---: | ---: |
| `router-cost` | \$0.06 | 95.8% (23/24) | \$0.0028 | 94.4% (68/72) | 4 |
| `router-balanced` | \$0.31 | 95.8% (23/24) | \$0.0133 | 95.8% (69/72) | 3 |
| `direct-premium` | \$1.34 | 100.0% (24/24) | \$0.0559 | 100% (72/72) | 0 |
| `router-quality` | \$1.56 | 95.8% (23/24) | \$0.0678 | 94.4% (68/72) | 4 |

Run totals: \$3.269553 / \$20.00, 288/288 cells, **0** throttles, 11 timeout cells,
aggregate grading coverage 96.18% (277/288), every arm `cost_complete=true`
(unpriced 0%). Timed-out tasks: `toll-schedule` (cost ×3, balanced ×3, quality ×1),
`dedupe-stable` (quality ×3), `weekday-label` (cost ×1).

## Expected result direction and reasoning (committed before 03D-3 results)

1. **Timeout elimination is the primary thing expected to change.** With
   `read_timeout_seconds = 180` now actually reaching the socket, I expect the 11
   timeout cells to complete and **timeout count to fall to 0–2**, lifting
   aggregate grading coverage from 96.18% toward **≥ 99%** and every arm's
   coverage to ≥ 97%. The censored cells are known to need > 90 s, and sibling
   repeats of the same tasks finished at 71.1 s and 74.8 s, so the demand sits
   just past the old wall. If timeouts persist at 180 s, the cause is not the
   boundary but something structural (a genuine hang or a backend stall), and
   that is a finding to report, not to re-tune.

2. **This run is a direct test of 03D-2's published claim — and can falsify it.**
   The 03D results page states the 4.17 pp pass-rate gap "comes from this
   latency-profile difference, not from code quality." That predicts the three
   router arms recover to **24/24 (100%)** once their timed-out cells complete,
   closing the gap to **0 pp**. I therefore expect all four arms at or near
   100%. **If the recovered cells complete but fail grading, the gap was
   partly real quality difference and the published sentence is wrong** — that
   outcome will be reported as-is and the page corrected. I am genuinely
   uncertain here; this is the prediction most worth being wrong about.

3. **Costs rise slightly; the ordering holds.** Cells that timed out produced no
   billable output; completing them adds tokens. I expect
   **cost < balanced < direct-premium < quality** to persist, with `router-cost`
   still cheapest by a wide margin and `router-quality` still the most expensive
   — i.e. the counter-intuitive 03D-2 finding (Quality mode costs *more* than
   calling premium directly) is expected to **replicate**. Absolute totals should
   land near 03D-2's (\$3.27) — I expect **\$3.3–\$4.5**, far under the \$20 cap.

4. **Routing behavior and cost-completeness unchanged.** Workload, seed, rate
   card, deployments, and `max_output_tokens` are all unchanged, so I expect the
   same backend selection (Grok-dominated Cost/Balanced) and **`cost_complete=true`
   with unpriced 0% for all four arms** again. Any unpriced cell fails closed as
   before and blocks that arm's savings claim.

5. **Wall-clock rises; that is expected, not a fault.** A cell that would have
   been cut at 90 s may now run to 180 s. The run should take longer than 03D-2's
   without that meaning anything is wrong. Budget, not time, is the gate.

6. **Best guess on the headline.** `router-cost` again gives the best
   cost-per-pass and `direct-premium` the worst. If prediction 2 holds, the
   savings claim gets *stronger* than 03D-2's because the pass-rate gap that
   qualified it disappears. A null or reversed result is acceptable and will be
   reported as-is.

## Failure / invalidation criteria (fixed in advance — UNCHANGED)

Identical to [`prereg-03d-router-modes.md`](prereg-03d-router-modes.md) and
[`prereg-03d2-router-modes.md`](prereg-03d2-router-modes.md). Repeated here so
approval binds them; **not weakened** after two prior runs.

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
  timeout count (the headline diagnostic this run), budget consumed, graded
  coverage, the count of cells still hitting `max_output_tokens` with no output,
  and per-arm latency p50/p95/p99/max so the new tail is visible.

## Unpriced-cell handling (fail-closed, 03Z-b preserved — UNCHANGED)

- A cell whose router-resolved backend has **no pinned rate** in the v2 card has
  its cost **withheld**: `cost_usd = null`, never 0.0 and never a guessed/default
  rate.
- The attempt is still **graded** — grading is independent of pricing — so an
  unpriced cell contributes to pass rate but is **excluded from cost and
  cost-per-pass**. An arm with any unpriced cell is `cost_complete = false` and
  **excluded from savings claims** entirely.
- The **per-arm unpriced fraction is reported**. 03D-2 achieved 0%; I expect the
  same. If it is not 0%, that is a reported finding, not a rate to be guessed.
- Reservation before dispatch is bounded by the \$20.00 budget cap; settlement
  withholds unpriced amounts as above.

## §8 hash order (recorded for verification)

1. `experiment_spec_hash` computed over the execution draft with preregistration
   fields excluded → `cffaac91316e370c1ec5316b1679df01a81ace958911e01c5baaccd88b389dff`.
   (Convention verified: the identical computation reproduces 03D-2's recorded
   `54d54a6c…` from the 90/120 draft.)
2. This file committed as its own commit (timestamp = preregistration evidence).
3. Clean tracked blob + commit resolved from git and pinned into
   `.foundry.local.yaml`.
4. Final `plan_hash` recomputed with the committed preregistration evidence bound
   into the resolved plan; that hash is what `benchmark run --approve-plan` checks.
5. Plan + hash presented for human approval. **No paid call before that approval.**

## Errata — implementation facts, appended after the run (2026-08-15)

**This section is an append. Not one character above it was changed.** The
predictions, gates, and invalidation criteria stand exactly as committed before
the results existed.

The header of this document says: *"the plan hash binds this file's blob and
commit; a modification after approval invalidates the run."* That clause is about
altering what was predicted and presenting it as the original. This append does
not do that, and the binding still checks out:

- The approved plan pinned blob `8584e1f8c6031d7be6b03d01a9e292c83d57bab5` at
  commit `454c8159e6e3666a6b24982ef30766ea73059f22`. Both are content-addressed
  git objects; this append cannot reach either. The approved text is retrievable
  and re-verifiable at any time:

  ```
  git show 454c8159e6e3666a6b24982ef30766ea73059f22:benchmarks/original-coding/prereg-03d3-router-modes.md | git hash-object --stdin
  # -> 8584e1f8c6031d7be6b03d01a9e292c83d57bab5
  ```

- The run's `plan_hash`, `sha256:33821119558063e83d9d255fb3fd72130519fe597288e11fdce909e6346b0b50`,
  is computed over the resolved `execution` mapping, whose `preregistration` block
  holds that pinned `{path, blob, commit}` **as literal values from the run
  config** — it is not recomputed from this file's current contents. Resolving the
  same config after this append still yields the same `plan_hash`, and it still
  matches the sealed manifest.

Appending does change the *working-tree* blob of this file. The pinned object is
the record; this file is the record plus a note. If the two must be the same
object for some future check, use the pinned one.

### What this document claimed

Line 83, verbatim:

```yaml
random_seed: 20260729        # fixed seed, sequential dispatch
```

Note that this third preregistration had already dropped the "counterbalanced arm
order" wording carried by
[`prereg-03d-router-modes.md`](prereg-03d-router-modes.md) and
[`prereg-03d2-router-modes.md`](prereg-03d2-router-modes.md). Those two documents
have their own errata. Nothing about counterbalancing was claimed here.

### What the implementation actually was

Verified at commit `f2d6f08694e4eabd46d111c7d9d53e48a4802ec6`.

| The comment said | What the code does |
|---|---|
| *fixed seed* | **No seed reaches the model API.** `random_seed` has exactly one writer (`run_plan.py:909`) and no reader on the execution path; its only effect is that it sits in `execution`, so it salts `plan_hash` — which is why changing it would have forced a new approval while changing nothing about the requests sent. Neither request surface carries a seed: `foundry_live.py:565-568` sends `model`, `messages`, `max_completion_tokens`; `foundry_live.py:586-589` sends `model`, `messages`, `max_tokens`. |
| *sequential dispatch* | **Accurate.** `measure.py:1404-1407` dispatches one cell at a time, task-major → then repeat → then arm. That order is deterministic, it never consults `random_seed`, and `measure.py:1407` walks `candidates` in the order the `arms:` list gives them, identically on every task and every repeat. |

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

**No.** The spend, the per-arm costs, the 99.65% grading coverage, the pass rates,
the timeout count, and the preregistered cost ordering are all unchanged.

- Each is a direct measurement of executed cells, or a ratio of such
  measurements. No seed enters any of those computations, so there is nothing to
  recompute.
- The change this run was designed to test — the transport cutoffs, read 90 → 180
  and overall 120 → 240 — is unaffected by this errata. Those values are real,
  they are in `execution["retry"]`, and the read cutoff is enforced on the socket.
  (`overall` is not enforced by anything: `to_httpx()` builds only the connect,
  read, write, and pool cutoffs, and no runner-side deadline exists. That is a
  separate, separately documented fact, not part of this correction.)
- The rate-card finding this run produced — `gpt-5.6-terra` having no priced row,
  and the fail-closed withholding that followed — has no dependency on a seed or
  a dispatch order either.

**What was actually lost is a property, not a number.** "Fixed seed" asserted a
reproducibility guarantee this stack cannot deliver: with no seed on the wire, the
service choosing the backend, and the sampling temperature left at the service
default, re-executing this plan is not expected to reproduce these outputs. This
run is in fact the sharpest evidence of that — the same workload, the same
deployments, and the same deterministic dispatch order sent Balanced's cells to an
entirely different backend mix than experiment 12 did. What *is* byte-reproducible
is the sealed artifact set, and `measure replay` re-verifies it against the
recorded fingerprints.
