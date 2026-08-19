# Experiment 13 · Comparing the router's three modes · run 3 (a paid test that found a gap in our own rate card)

!!! abstract "One-line summary"

    A third **paid 4-arm measured comparison** ran the router's Cost · Balanced ·
    Quality modes and a direct `gpt-5.6-sol` arm on the same 24 coding tasks, this
    time with the raised transport timeouts. The measurement itself came out clean —
    **287 of 288 cells graded, every arm at pass rate 1.0** — and the preregistered
    cost order held. What the run exposed was ours, not the router's: **our rate card
    enumerated the wrong scope**, so 12 calls in the Balanced arm landed on
    `gpt-5.6-terra`, a model with no row in the card. Those cells were withheld
    fail-closed, and that arm is **cost-incomplete**: it reports, but it carries no
    savings claim.

!!! danger "This page records a real paid run"

    Total spend **$4.196595 / budget $20.00**, keyless Entra, sequential execution in a
    deterministic dispatch order (task-major → repeat → arm). `max_output_tokens` is the only
    request parameter that comes from the plan; sampling temperature is the service default,
    which this repository neither sets nor records.
    Preregistration `454c8159` committed **before** the results;
    `plan_hash sha256:33821119…6b0b50` matches the run manifest. Prompt and response
    text is not published — the sealed snapshot stays local (gitignored), and only
    `output_sha256` rides in the public trail.

## What was asked

- **Situation (why):** [experiment 12](12-router-modes-measured.md) cleared every gate, but 11 of its
  288 cells timed out at the 90-second read ceiling while the slowest success finished
  at 81.8 s. The proposal to raise the ceiling was recorded and left unapplied. This run
  applies it under its own preregistration.
- **Task (what):** the same four arms — `router-cost` (Model Router in Cost mode) ·
  `router-balanced` (Model Router in Balanced mode) · `router-quality` (Model Router in
  Quality mode) · `direct-premium` (calling the premium model directly · `gpt-5.6-sol`)
  — on the same 24 curated coding tasks. `24 tasks × 4 arms × n=3 = 288 cells`,
  deterministic exec-signal grading.
- **Changed from run 2:** transport timeouts **read 90 → 180 s, overall 120 → 240 s**, set in
  the operator's local run config — the repo's committed defaults are still 90/120, so a fresh
  clone does not inherit them. PR #101 is what makes such a setting reach the socket at all:
  before it, the plan's timeouts were sealed into the manifest while the client quietly kept
  its own. Nothing else changed. The change moves `plan_hash`, so it required a new
  preregistration and a new approval — which is why this is a separate experiment and not an
  edit to experiment 12.

## Result — grading coverage · pass rate · cost per arm

| arm | routing mode | grading coverage | task pass rate | unpriced share | measured cost |
|---|---|---|---|---|---|
| `router-cost` | Cost | 98.6% (71/72) | 100% (24/24) | 0% | $0.075117 |
| `router-balanced` | Balanced | 100% (72/72) | 100% (24/24) | **16.7% (12/72)** | $1.327674 · *cost-incomplete* |
| `router-quality` | Quality | 100% (72/72) | 100% (24/24) | 0% | $1.405974 |
| `direct-premium` | — (`gpt-5.6-sol`) | 100% (72/72) | 100% (24/24) | 0% | $1.387830 |

- **Aggregate grading coverage 99.65% (287/288)** · 288 attempts, 287 completed calls ·
  429 throttles **0** · **1 timeout** (HTTP 408).
- **Preregistered cost order held**: `cost < balanced < premium ≤ quality`
  (`$0.075117 < $1.327674 < $1.387830 ≤ $1.405974`).
- Run-level invalidation criteria (coverage < 90% for any arm; budget abort before 90%;
  attrition preventing 90%) — **none triggered**. The run is valid; one arm is
  claim-blocked.

!!! warning "One number on this page is not the site's headline number"

    The run summary's `savings_pct` (**94.7%**) compares the **cheapest cost-complete
    arm against the most expensive one** — here Cost against Quality. The site's
    published **95.2%** is a different comparison: Cost against `direct-premium`, in
    [experiment 12](12-router-modes-measured.md). Two runs, two baselines. They are
    not versions of each other and must not be swapped.

## Which backends actually answered

| arm | backends actually routed |
|---|---|
| `router-cost` | **`grok-4-1-fast-reasoning` 100%** (71/71 priced cells) |
| `router-balanced` | `gpt-5.6-sol` 83% (60/72) · **`gpt-5.6-terra` 17% (12/72)** |
| `router-quality` | `gpt-5.6-sol` 100% (72/72) |
| `direct-premium` | `gpt-5.6-sol` 100% (72/72) |

The Balanced row is where the cost came from, and it is worth reading beside the same
row in experiment 12, which ran the same workload, the same seed and the same
deployments:

| `router-balanced` served by | experiment 12 | experiment 13 |
|---|---|---|
| `grok-4-1-fast-reasoning` | 83% | **0%** |
| `gpt-5.4` · `gpt-5.5` | 17% | 0% |
| `gpt-5.6-sol` · `gpt-5.6-terra` | 0% | **100%** |
| arm total cost | $0.305492 | $1.327674 |

Balanced mode sent every cell to the premium 5.6 family in this run and none to Grok;
in run 2 it did the reverse. **We are not claiming a cause.** The timeout change
lets slow calls finish, but it is not a routing knob, and the router's selection policy
is not ours to inspect. What the two rows do establish is that **an arm's cost is not a
stable property of its mode** — it is a property of what the roster happened to serve
that day. That is the single most important caveat on any router cost figure here,
including the published ones.

## Finding 1 — the rate card enumerated the wrong scope

Twelve of the Balanced arm's 72 calls were served by **`gpt-5.6-terra`**. The card had no
row for it, `composite_cost`'s fail-closed guard withheld the amount rather than guessing,
and the arm total became incomplete.

The router selecting `terra` is **ordinary product behaviour** — Model Router picks a
backend per request from its own managed roster, and that roster is not ours to enumerate
in advance. The defect is on our side: when the card was built, the scope was
"router candidate list + the models we deployed," and under that scope `gpt-5.6` was
recorded as one model. It is three — **`sol` · `terra` · `luna`** — and only one was
written down.

!!! note "The first diagnosis was wrong, and the correction is the point"

    The initial read was "that model can't be purchased." Checking Azure directly showed
    the opposite: `gpt-5.6-terra` is in the catalogue, and its meters carry
    `effectiveStartDate 2026-07-01` — **44 days before this run**. The public rate
    existed the whole time. Nothing was missing upstream; our enumeration was short.

## Finding 2 — the same gap was wider than the one cell that surfaced it

The card was then checked against a different reference — **what is actually deployed in
the account**, rather than what the router might choose. Five more deployments had no
priced row:

`DeepSeek-V4-Pro` · `Kimi-K2.6` · `Mistral-Large-3` · `Cohere-command-a-plus` · `Phi-4-reasoning`

**DeepSeek is the instructive one.** The card listed `V3.1` and `V3.2`; the account runs
`V4-Pro`. Similar names read as coverage, and a scan by eye passed over it.

One deployment is left unpriced **on purpose**: `text-embedding-3-large`. The region
carries no meter for the plan in use, and an embedding model has no output tokens while a
rate row requires both input and output. Rather than force a shape that does not fit, the
card records **why the row is absent**.

## The fix — a dated card, not an edited one

The existing card could not be corrected in place: earlier experiments pin its digest, so
changing one character would retroactively break records that are already sealed. The
correction is therefore a **new dated file**, and the old one stays exactly as it was.

- All **23** pre-existing rate rows — **61 cited retail meters** between them — were
  re-fetched from Azure Retail and compared: **61/61 identical**. The change is an
  addition (7 new rows), not a repricing.
- The set of deployments is now **committed as a file**, and a test fails the build when
  something is deployed without a priced row. The next occurrence is caught at commit
  time rather than in a cost column after a paid run.

Both halves shipped as PRs: the dated card and the 5.6 family in **#104**, the
deployed-set capture and the test that fails CI without it in **#105**.

!!! warning "The new check is a floor, not full coverage"

    Every one of these gaps was found **by hand, reading logs**. That is luck, not
    process — which is what the check replaces. But the check compares against
    **deployments**, and `terra` was never deployed to this account: it arrived from the
    router's own roster. So a deployment-based check would not have caught the cell that
    started this. Two layers, and only one of them runs before the money is spent:

    | gap | caught by | when |
    |---|---|---|
    | deployed, no priced row (e.g. `DeepSeek-V4-Pro`) | deployed-set test | at commit — before spend |
    | routed from the managed roster, no priced row (e.g. `gpt-5.6-terra`) | `composite_cost` fail-closed | during the run — after spend |

    The floor is asserted in the test itself so a green build is not read as "everything
    is covered."

## Secondary result — the raised timeout did what the proposal predicted

The timeout change was made to test one hypothesis: that the 11 timeouts in experiment 12
were the ceiling, not the workload.

| | experiment 12 (read 90 s) | experiment 13 (read 180 s) |
|---|---|---|
| timeout cells | 11 / 288 | **1 / 288** |
| aggregate grading coverage | 96.18% | **99.65%** |
| lowest arm pass rate | 0.958 (23/24) | **1.000 (24/24)** |

The single remaining timeout (`router-cost` · `align-frames` · repeat 1) recorded
`latency_ms 180096.8` — it hit the new read ceiling, not the 240 s overall budget, the
same pattern the 90 s cells showed at 90.0–90.7 s.

This supports a claim experiment 12 could only argue: its **4.17 pp pass-rate gap was a
latency artefact, not a code-quality difference**. With the ceiling raised, every arm
solved every task.

!!! note "What this does not do"

    It does not update experiment 12. That run measured what it measured at 90/120, its
    figures stand as published, and this is a separate measurement under a separate
    approved plan.

## What this run does not claim

- **A savings rate for the Balanced arm.** It has 12 unpriced cells, so
  `cost_complete = false` and `savings_claim_allowed = false` for that arm, per the
  fail-closed contract. Applying the corrected card to those cells yields
  **$1.3633722 (+$0.0356982, +2.69%)** — recorded here as a **reference figure computed
  outside this run's `plan_hash`**, not as its measured cost. The run's card is the card
  the run was approved with.
- **That the corrected card retroactively validates anything.** Nothing in an earlier
  run's record was recomputed, and no published figure moved.
- **Full price coverage.** See the floor note above.
- **A general result.** 24 tasks · one tenant · one region · one run ·
  `evidence_tier = directional`. Routing is chosen per request and will differ between
  runs; the arm totals here are one observation of that behaviour, not its expectation.

## Reproduction · evidence

- **Preregistration (public · committed):** [`prereg-03d3-router-modes.md`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/benchmarks/original-coding/prereg-03d3-router-modes.md)
  — gate, estimand, predicted direction, and invalidation criteria pinned with a
  timestamp before the results. The prediction of `unpriced 0%` was **wrong**, and the
  preregistration had already ruled that a *reported finding, not a rate to be guessed*.
- **Sealed snapshot (local · gitignored):** manifest, summary, traces and source text
  sealed and bound to `plan_hash`; `measure replay` re-confirms byte-for-byte identity.
- **Invariant:** this run does not touch the bytes of the offline ledger
  (`measured = false`), experiment 10's measurement ledger, or the experiment 12 record.

The cache tokens left in this run's sealed traces were re-aggregated after the fact, with
zero paid calls — [Prompt cache observed in the sealed runs](../manual/prompt-cache-observed.md).
It is a post-hoc observation outside the preregistration gate, and no figure on this page
changed.
