# Routing-mode measured results · 03D Results

> **`measured=true`, a paid measured run.** The result of running four arms (the three
> routing modes + the direct-premium baseline) against the same 24 coding tasks at n=3
> on real Azure AI Foundry. 288 cells, sealed snapshot, replay-verified byte-identical.
> Every number on this page comes not from an offline projection but from **one real
> measurement** — powerful, therefore, but narrow. Read the limits below first.

!!! warning "Limits to read first — do not generalize"
    - **24 tasks = evidence_tier `directional`.** A directional signal, not statistical
      confidence. A statistical conclusion would need ~100 problems.
    - **Single tenant · single region · one measurement.** replay guarantees
      *reproduction* but not a population estimate.
    - **Timeouts count against the router arms only.** The router backends have longer
      latency (p50 12–16s) and hit the fixed timeout; direct-premium (4.2s) does not.
      The **4.17%p** pass-rate gap below comes from this latency-profile difference, not
      from code quality.
    - **Do not generalize to other workloads.** This result is limited to this
      workload · this tenant · this one measurement.

!!! info "Honesty labels"
    - `measured=true` — real Foundry calls and usage (tokens, latency). Not
      synthetic/projected.
    - `unpriced 0%` — every cell priced at pinned rates (`cost_complete=true`).
    - `coverage 96.18%` (277/288) — the share of content-graded cells (**grading
      coverage**). Arm low of 94.4% (all clear the 90% gate).
    - `evidence_tier=directional` — 24 tasks, directional.
    - `replay verified` — sealed-snapshot byte-identical replay, `plan_hash
      sha256:d640dc07…`, the prereg commit precedes the run.

Actual spend **$3.27 / $20.00** budget · 288/288 cells · **0** 429 throttles · 11
timeout cells (HTTP 408).

---

## 1 · Arm comparison — cost · pass rate · cost-per-pass

![Horizontal bars of total cost per arm: router-cost $0.06, router-balanced $0.31, direct-premium $1.34, router-quality $1.56, each bar annotated with pass rate and cost-per-pass](/foundry-cost-aware-model-routing/assets/03d/arm-cost-comparison.svg)

The key contrast is **the cheapest router mode vs the direct-premium baseline**:
`router-cost` holds a task pass rate of 95.8% while being **95.2% cheaper** than
direct-premium (full-precision calculation). The pass-rate gap is within **4.17%p**,
and even that gap is entirely due to timeouts, as shown below.

| Arm | Mode | Total cost | Pass rate | $/pass | Grading coverage |
| --- | --- | ---: | ---: | ---: | ---: |
| `router-cost` | Cost | $0.06 | 95.8% (23/24) | $0.0028 | 94.4% |
| `router-balanced` | Balanced | $0.31 | 95.8% (23/24) | $0.0133 | 95.8% |
| `direct-premium` | — | $1.34 | 100.0% (24/24) | $0.0559 | 100.0% |
| `router-quality` | Quality | $1.56 | 95.8% (23/24) | $0.0678 | 94.4% |

*Deployment mapping — `router-cost`→`model-router-cost` · `router-balanced`→`model-router` ·
`direct-premium`→`gpt-5.6-sol` · `router-quality`→`model-router-quality`. Every arm is
`cost_complete=true` (unpriced 0%), with every cell priced at pinned rates.*

!!! note "Pass rate and grading coverage are different metrics — different denominators"
    The **pass rate** in the table (e.g. 23/24) is *task*-based — the share of tasks
    that passed (were solved). The **grading coverage** (e.g. 68/72) is *cell*-based —
    the share of cells actually graded (measurement completeness). A timeout cell drops
    out of grading coverage **and at the same time** counts as a failure in the pass
    rate, so unlike offline the two values diverge — which is why `router-cost` has a
    pass rate of 95.8% (23/24) and a grading coverage of 94.4% (68/72) that differ. Not
    a typo, but separate values with different definitions. For the definitions see the
    [Glossary](glossary.md).

!!! note "Two savings baselines — don't mix them"
    - **The headline 95.2%** = `router-cost` ($0.06) vs **`direct-premium`** ($1.34).
      Savings against the common real-world "just call the best model directly."
    - The **`savings_pct=95.8%`** in the public bundle (`published.json`) is a different
      baseline — best-arm vs **naive/worst-arm** (`router-quality` $1.56). Best vs worst
      arm.
    - The two numbers answer different questions. This page uses the **direct-premium
      baseline** — closer to practice — as the headline, and publishes the bundle value
      as-is too. The savings rate is computed from full-precision amounts, not display
      rounding (displayed amounts to 2 places; sub-cent and unit-price averages to 4).

---

## 2 · Cost × quality — the quality mode is dominated by direct-premium

![Cost vs pass-rate scatter: direct-premium sits upper-left of router-quality (cheaper and higher pass rate), showing router-quality is dominated; router-cost is furthest left at the same pass rate](/foundry-cost-aware-model-routing/assets/03d/cost-vs-quality-scatter.svg)

The most counterintuitive finding: **the `router-quality` ($1.56) mode is completely
dominated by `direct-premium` ($1.34)** — more expensive yet a lower pass rate (95.8%
< 100.0%). The markup the router's "quality" mode adds as it escalates to the premium
backend cannot beat a direct premium call. If you want quality, **calling
direct-premium directly is cheaper and more accurate** than the router's quality mode
— on this workload.

Conversely, `router-cost` delivers the same pass rate (95.8%) as the other router arms
at **under 1/20 the cost**. On this workload the router's value is not "raising
quality" but "holding quality + slashing cost."

---

## 3 · Backend distribution — Cost mode 100% Grok, reproduced across two runs

![Stacked bars of the backends actually routed per arm: router-cost is 100% grok-4-1-fast-reasoning; router-quality splits across gpt-5 and gpt-5.5 with no grok; direct-premium is 100% gpt-5.6-sol](/foundry-cost-aware-model-routing/assets/03d/backend-distribution.svg)

`router-cost` sent all (100%) of its graded cells to `grok-4-1-fast-reasoning`. This
**Cost-mode 100% Grok** skew **reproduced across two consecutive runs** — the prior
void run and this publishable run — directional evidence that the router policy
consistently picks the same low-cost backend in cost mode. `router-quality`, the
opposite, splits across `gpt-5` (57%) and `gpt-5.5` (43%) and uses no Grok at all.
(The distribution is over graded cells — cells whose backend was not settled because
of a timeout are excluded.)

---

## 4 · 11 timeout cells — we don't hide them

11 cells timed out with HTTP 408 (3.8% of the total). **All of them in the router arms
only** — `direct-premium` had 0.

| Breakdown | Detail |
| --- | --- |
| By arm | `router-cost` 4 · `router-balanced` 3 · `router-quality` 4 · `direct-premium` **0** |
| By task | `toll-schedule` 7 · `dedupe-stable` 3 · `weekday-label` 1 |
| Status | all 11 cells HTTP 408 (read timeout) |

A timeout cell is handled **doubly conservatively**: (1) with no content it is
**excluded** from grading coverage, and at the same time (2) it is **counted as a
failure** with pass=False. So the router arms' pass rate falls below direct-premium's
by exactly these timeouts. **The 4.17%p gap above is a latency difference, not a
code-quality one** — the router backends are slower than premium and hit the fixed
timeout (read 90s / overall 120s) first. A follow-up proposal to raise the timeout is
in the [Fix C doc](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/benchmarks/original-coding/fix-c-timeout-proposal.md) (applying it needs a new prereg + re-run).

---

## 5 · Signal separation — what each metric proves, and what it does not

To avoid over-reading the measured result, we state the boundary per metric.

| Metric (this run's value) | What it **proves** | What it **does not prove** |
| --- | --- | --- |
| `measured=true` | Real provider calls and usage (tokens, latency) actually happened and were recorded | Does not prove code quality |
| `cost_complete=true` (unpriced 0%) | Every cell priced at pinned rates | Does not prove invoice reconciliation |
| pass rate 95.8–100% | Passed a deterministic exec-signals grader | Not a general code-quality evaluation |
| savings 95.2% | Savings on this workload · this tenant · one measurement | Not a generalization to other workloads/tenants |

---

## 6 · Reproduction and provenance

- **Data source**: [`docs/assets/03d/published.json`](/foundry-cost-aware-model-routing/assets/03d/published.json), a
  masked extract of the sealed snapshot via the `measure publish` path. It holds **only
  aggregates, per-arm figures, and the backend distribution** — no prompt or response
  bodies, endpoints, or tenant identifiers (the endpoint is masked to
  `***.cognitiveservices.azure.com`, and bodies keep only `output_sha256`).
- **Charts**: the three SVGs above are **statically generated** from `published.json`
  by `scripts/build_03d_dashboard.py`. The browser fetches no data.
- **Integrity**: `plan_hash sha256:d640dc07…91d2921e` · the prereg commit precedes the
  run (D8 gate) · replay `summary_matches=true`, `cost_mismatches=[]` (byte-identical) ·
  `partial=false`.
- **Quality-gate verdict** (prereg-fixed criteria): grading coverage ≥ 90% **PASS** ·
  min_pass ≥ 0.60 **PASS** · drop vs premium ≤ 10%p (measured 4.17%p) **PASS** · budget
  **PASS** → **publishable**.
- **Prereg prediction hit**: the updated prediction was `cost < balanced < premium ≤
  quality` (by cost), and the measurement **matched** at `$0.06 < $0.31 < $1.34 <
  $1.56`. That is, the prediction that quality mode costs more than premium was
  confirmed.

The narrative record of the same run is in the lab notebook —
[Experiment 12 · Routing-mode paid measured re-run](../lab-notebook/12-router-modes-measured.md).
Read alongside the prior
[Experiment 11 · prereg VOID](../lab-notebook/11-router-modes-void.md) to see what was
fixed (rate coverage · output ceiling) and what changed.
