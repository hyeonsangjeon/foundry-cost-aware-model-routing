# Experiment 12 · Comparing the router's three modes · run 2 (measurement succeeded)

!!! abstract "One-line summary"
    [Experiment 11](11-router-modes-void.md) attempted the repository's first paid 4-arm
    measured comparison, but a preregistration I committed **before** seeing the results set a
    grading-coverage gate that one arm failed to clear, so it was ruled **VOID** (quality
    grading coverage 79.2% < 90%). This experiment fixed **only the two causes** that negative
    result pinpointed (Fix A · Fix B) and **re-ran with the same gate and the same estimand**.
    The result: **all four arms cleared the gate — publishable.** Grading coverage recovered
    from 79.2% to **96.18%**, and **the cost order the preregistration wrote down in advance
    (`cost < balanced < premium ≤ quality`) matched the measurement.** Spend **$3.27 / $20**,
    replay byte-for-byte identical, unpriced **0%**. Experiment 11's "discipline forced a void"
    and this experiment's "a valid result came out under discipline" should be read side by
    side — the point is that **the same gate was applied twice, without loosening.**

!!! warning "This page also records a real paid run — spend the operator approved"
    Just like experiment 11, this re-run is **a real Azure inference run executed after passing
    explicit approval gates**. Total spend **$3.269553 / budget $20.00**, keyless Entra,
    sequential execution, counterbalanced arm order, fixed seed. The prompt and response **text
    is not published** — the sealed snapshot stays local (gitignored), and only `output_sha256`
    (grading evidence) rides in the public trail.

## What was fixed — only the two causes the negative result pointed to

Experiment 11 produced three findings, and this re-run fixed **the two causes that voided the
run**. The gate, estimand, workload, and seed were **not changed at all.**

| Fixed | Why it was a problem in experiment 11 | Effect in this re-run |
| --- | --- | --- |
| **Fix A — `grok-4-1-fast.cached: 0.2`** (rate card) | Grok returned cached input, but Azure Retail has no cached meter, so cost was withheld fail-closed → unpriced 43.4% | **unpriced 0%.** the cost and balanced arms are priced cost-complete |
| **Fix B — `max_output_tokens` 2048 → 8192** (config) | reasoning models spent the budget on reasoning and emitted no code → quality grading coverage 79.2% | **grading coverage recovered to 96.18%.** every arm clears the 90% gate |

Both fixes change the config / rate card, so **`plan_hash` changes**, and the [new
preregistration (`prereg-03d2-router-modes.md`)](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/benchmarks/original-coding/prereg-03d2-router-modes.md)
was re-committed and re-approved **before seeing the results** — the failure criteria
(coverage 90%, min_pass 0.60, max_drop 10pp, budget $20) are **kept as-is, without loosening.**

## Result — coverage · pass rate · cost · cost-per-pass per arm

<figure markdown="span">
  ![Horizontal bars of total cost per arm: router-cost $0.06, router-balanced $0.31, direct-premium $1.34, router-quality $1.56, each bar annotated with pass rate and cost-per-pass](/foundry-cost-aware-model-routing/assets/03d/arm-cost-comparison.en.svg)
  <figcaption>Total cost per arm — router-cost is cheapest and router-quality is most expensive. Each bar also shows pass rate and cost per pass. These are the same measured values as the table below.</figcaption>
</figure>

| arm | routing mode | grading coverage | task pass rate | measured cost | cost_complete | cost-per-pass |
| --- | --- | --- | --- | --- | --- | --- |
| `router-cost` | Cost | 94.4% (68/72) | 95.8% (23/24) | **$0.064867** | ✅ | **$0.00282** |
| `router-balanced` | Balanced | 95.8% (69/72) | 95.8% (23/24) | $0.305492 | ✅ | $0.01328 |
| `direct-premium` | — (`gpt-5.6-sol`) | 100% (72/72) | 100% (24/24) | $1.340535 | ✅ | $0.05586 |
| `router-quality` | Quality | 94.4% (68/72) | 95.8% (23/24) | $1.558659 | ✅ | $0.06777 |

- **Total spend $3.269553 / $20** · 288/288 completed (partial=false) · 429 throttles **0** ·
  11 timeouts (HTTP408) · aggregate grading coverage **96.18% (277/288)** · unpriced **0%** ·
  replay **byte-for-byte identical** (`cost_mismatches: []`).
- **Cost order: `cost ($0.065) < balanced ($0.305) < premium ($1.341) < quality ($1.559)`.**

## Quality-gate verdict — **all four arms PASS → publishable**

<figure markdown="span">
  ![Cost vs pass-rate scatter: direct-premium sits upper-left of router-quality (cheaper and higher pass rate), showing router-quality is dominated; router-cost is furthest left at the same pass rate](/foundry-cost-aware-model-routing/assets/03d/cost-vs-quality-scatter.en.svg)
  <figcaption>Cost vs pass-rate scatter — the further upper-left, the cheaper and more accurate. router-cost holds the same pass-rate band at the lowest cost, while router-quality is dominated by direct-premium (more expensive without a higher pass rate).</figcaption>
</figure>

| gate | criterion | result |
| --- | --- | --- |
| grading coverage (per arm) | ≥ 90% | lowest arm 94.4% → **PASS** |
| minimum pass rate (per arm) | ≥ 0.60 | lowest 0.958 → **PASS** |
| pass-rate drop vs premium | ≤ 10 pp | router 0.958 vs premium 1.000 = **4.17 pp** → **PASS** |
| budget | ≤ $20 | $3.27 → **PASS** |

The **grading-coverage gate that voided the comparison in experiment 11 passed on every arm**
this time, and the remaining gates were met too, so this run is **publishable as a savings
comparison.**

## The preregistered prediction was **right** — write the prediction first, the result after

The cost-direction prediction written into the re-run preregistration was **`cost < balanced <
direct-premium ≤ quality`** (a prediction updated to reflect experiment 11's measurement, where
quality cost more than premium). The measurement **confirmed it exactly**: `cost ($0.065) <
balanced ($0.305) < premium ($1.341) < quality ($1.559)`.

!!! quote "Why this doesn't contradict experiment 11's 'overturning'"
    Experiment 11's prediction was a hypothesis from **before the first measurement** (`cost ≤
    balanced ≤ quality ≤ premium`), and it was overturned. This re-run's prediction is a new
    hypothesis (`premium ≤ quality`) that **learned from** that overturning, and this time it was
    right. Each document pins its prediction of the moment with a timestamp — experiment 11's
    account was **not edited.** The reason Quality mode costs more than direct premium is the
    same: **the router markup rides on top of the premium sub-model choice** and exceeds the
    direct call.

## A reproduced finding — **Cost mode 100% Grok, two runs in a row**

<figure markdown="span">
  ![Stacked bars of the backends actually routed per arm: router-cost is 100% grok-4-1-fast-reasoning; router-quality splits across gpt-5 and gpt-5.5 with no grok; direct-premium is 100% gpt-5.6-sol](/foundry-cost-aware-model-routing/assets/03d/backend-distribution.en.svg)
  <figcaption>The backends actually routed per arm — Cost mode sends every cell to Grok, Quality mode splits across the gpt family with no Grok. This renders the table below as a figure.</figcaption>
</figure>

| arm | backends actually routed (top) |
| --- | --- |
| `router-cost` | **`grok-4-1-fast-reasoning` 100%** (68/68) |
| `router-balanced` | `grok-4-1-fast-reasoning` 83% · `gpt-5.4` 13% · `gpt-5.5` 4% |
| `router-quality` | `gpt-5` 57% · `gpt-5.5` 43% (Grok 0) |
| `direct-premium` | `gpt-5.6-sol` 100% |

Cost mode sending **every cell to Grok** was **reproduced back to back** across experiment 11
(void) and this re-run. The preregistration wrote in advance that it "expects the same routing
behavior," and the measurement confirmed it.

## The 11 timeout cells — **counted doubly conservatively** (working only against the router)

When the 8192 cap (Fix B) was on, reasoning cells took longer to generate, and 11 cells exceeded
the **fixed timeouts (read 90s / overall 120s)** — **all in router arms** (cost 4 · balanced 3 ·
quality 4), with direct-premium at 0 (its longest was 33.5s). By task: `toll-schedule` 7 ·
`dedupe-stable` 3 · `weekday-label` 1.

These cells are counted **doubly conservatively**:

- **Excluded from coverage** — with no body, `output_sha256 = None` → dropped from the
  grading-coverage numerator.
- **And simultaneously failed on pass rate** — counted as `pass = False`, docking pass rate too.

That is, the router arms' **4.17 pp pass-rate drop is entirely due to timeouts, not code
quality** — and even so, we did not reinterpret the gate favorably; we judged it publishable
**with the penalty applied as-is.**

!!! danger "What this run does not claim (limits — read these together)"
    - **Statistical confidence**: 24 tasks = `evidence_tier` **directional**. Confirming it
      statistically would need **~100** tasks. This result points a direction; it does not give a
      confidence interval.
    - **No generalization**: a single tenant · a single region · **one measurement**. Do not carry
      these numbers to another workload, time, or region.
    - **Timeout asymmetry**: the fixed timeout works against **the router arms only** (a structural
      trait: the router goes to slower reasoning backends with routing latency added on top). Do not
      read the pass-rate gap as a "quality difference."
    - **The savings narrative is specific to this configuration**: clearing the gate does not
      guarantee savings on an arbitrary workload.

## Next — a Fix C candidate (what this run newly surfaced)

The only blemish in this re-run is the **11 timeout cells** above. The longest successful-cell
latency was 81.8s (Grok reasoning) and p99 was 74.8s, yet **all 11 cells hit the read_timeout 90s
wall exactly** (they never reached overall 120s). So `read_timeout` is the **only binding
constraint**, and the [Fix C proposal](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/benchmarks/original-coding/fix-c-timeout-proposal.md)
suggests read 90→180s / overall 120→240s. This too is a config change, so **`plan_hash` changes
and a new preregistration + re-approval are required** — whether to apply it is the operator's
call (a proposal only).

---

!!! note "Reproduction · evidence"
    - **Preregistration (public · committed):**
      [`benchmarks/original-coding/prereg-03d2-router-modes.md`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/benchmarks/original-coding/prereg-03d2-router-modes.md)
      — the gate, estimand, **updated prediction**, and void criteria are pinned with a timestamp
      **before** the results.
    - **Sealed snapshot (local · gitignored):** the manifest, summary, traces, and source text are
      sealed and bound to `plan_hash` (`sha256:d640dc07…91d2921e`), and `measure replay`
      re-confirms **byte-for-byte identity** (`cost_mismatches: []`). The source text is not
      published, by contract.
    - **Invariant:** this paid run **does not touch** the bytes of the offline ledger
      (`measured = false`) or [experiment 10](10-measured-ledger.md)'s measurement ledger.
      Experiment 11's void verdict account is also **preserved as-is.**
