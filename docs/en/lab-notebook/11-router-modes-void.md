# Experiment 11 · Comparing the router's three modes · run 1 (measurement failed)

!!! abstract "One-line summary"
    If [experiment 09](09-live-routing-proof.md) proved the router's **choice** and
    [experiment 10](10-measured-ledger.md) proved the **sealing and audit** of that spend,
    this experiment attempts the repository's first **paid 4-arm measured comparison** — it
    wires the router's three modes (Cost · Balanced · Quality) and a premium direct arm
    (`gpt-5.6-sol`) onto the same 24 coding tasks and measures **pass rate against cost**.
    The result: **the run is VOID.** A preregistration I committed **before** seeing the
    results set a grading-coverage gate, and one arm failed to clear it (quality grading
    coverage **79.2% < 90%**). The value of this experiment is not a clean savings number but
    that **the preregistration actually stopped after-the-fact narrative-fitting** — and that
    along the way **a prediction was overturned** (quality cost more than premium) and **three
    unexpected findings** came out. A valid negative result is an asset to **record**, not
    discard.

!!! warning "This page records a real paid run — the only approved spend"
    Unlike experiments 01–10, which were offline projections or re-seals of already-captured
    usage, this experiment is **a real Azure inference run executed after passing explicit
    approval gates (STOP 1 · STOP 2)**. Total spend **$3.467533 / budget $20.00**, keyless
    Entra, sequential execution, fixed seed. The prompt and response **text is not published**
    — the sealed snapshot stays local (gitignored), and only `output_sha256` (grading
    evidence) rides in the public trail (the same source-preservation contract as
    [experiment 10](10-measured-ledger.md)).

## What was asked — "do the three modes really split on cost and quality?"

- **Situation (why):** the router has three routing modes, `Cost` / `Balanced` / `Quality`.
  Offline projections merely **assumed** "Cost is cheap and Quality is accurate"; whether
  cost and pass rate really split in that order **by measurement** on the same workload had
  never been verified.
- **Task (what):** wire four arms — `router-cost` (mode=Cost) · `router-balanced` (no routing
  block = the Balanced default) · `router-quality` (mode=Quality) · `direct-premium`
  (`gpt-5.6-sol` direct) — onto the 24 curated coding tasks in
  [`benchmarks/original-coding`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/tree/main/benchmarks/original-coding).
  `24 tasks × 4 arms × n=3 = 288 cells`, deterministic exec-signal grading, cost computed with
  the v2 synthetic rate card.
- **Discipline (pinned first):** before seeing the results, the quality gate, estimand,
  predicted direction, and void criteria were committed to
  [`prereg-03d-router-modes.md`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/benchmarks/original-coding/prereg-03d-router-modes.md).
  **The timestamp is the proof** — it can't be edited later to fit the results.

<figure markdown="span">
  ![Cost vs pass-rate scatter (experiment 12 publishable re-run): direct-premium sits upper-left of router-quality (cheaper and higher pass rate), showing router-quality is dominated; router-cost is furthest left at the same pass rate](/foundry-cost-aware-model-routing/assets/03d/cost-vs-quality-scatter.en.svg)
  <figcaption>For contrast — this scatter is <strong>experiment 12's (the publishable re-run)</strong> cost vs pass rate. Experiment 11 is VOID at the grading-coverage gate and has no publishable chart of its own, so we show experiment 12's result — produced after fixing the two causes — as a contrast. Directly below is experiment 11's voided measured table.</figcaption>
</figure>

## Result — grading coverage · pass rate · cost per arm

| arm | routing mode | grading coverage | task pass rate | unpriced share | measured cost |
| --- | --- | --- | --- | --- | --- |
| `router-cost` | Cost | 95.8% (69/72) | 95.8% (23/24) | **95.8%** (all Grok) | $0.00 · *cost-incomplete* |
| `router-balanced` | Balanced | 94.4% (68/72) | 95.8% (23/24) | **77.8%** (56/72 Grok) | $0.259 · *cost-incomplete* |
| `router-quality` | Quality | **79.2% (57/72)** ❌ | 79.2% (19/24) | 0% | $1.791 |
| `direct-premium` | — (`gpt-5.6-sol`) | 93.1% (67/72) | 91.7% (22/24) | 0% | $1.417 |

- **Total spend $3.467533 / $20** · 288/288 cells completed (partial=false) · 429 throttles
  **0** · 7 timeouts (HTTP408, handled per the retry policy) · replay **byte-for-byte
  identical** (`cost_mismatches: []`).
- **Aggregate grading coverage is 90.6% (261/288), which just clears 90%**, but the gate is
  *per-arm* — with `router-quality` collapsing to **79.2%**, the whole comparison is voided.

## The preregistered prediction was overturned — **recorded as-is, not edited**

The predicted direction written into the preregistration was `cost ≤ balanced ≤ quality ≤
premium` (spend), with quality expected to have the highest pass rate. The measurement
**overturned this on two counts**:

- **Cost inversion:** `quality ($1.791) > premium ($1.417)`. Quality mode's premium sub-model
  choice was **more expensive** than direct premium, and it wasn't offset by a quality edge.
- **Pass-rate inversion:** quality was the **lowest** (0.792). The arm expected to be most
  accurate came in last — though this number is itself an artifact of finding (2) below and
  should not be read at face value.

!!! quote "Why we don't retro-edit predictions"
    Erase a wrong prediction and rewrite it to fit the results, and any run can be made to look
    like a "success." The whole reason a preregistration exists is to **structurally block**
    exactly that temptation. So here we write "it differed from the prediction" — and that is
    the most honest sentence in this experiment.

## Three unexpected findings

### (1) It was **Grok**, not Claude

The preregistration predicted the unpriced risk would come from the **absence of the five
Claude models** (they genuinely aren't in Azure Retail). In the measurement, where the router
actually went was **`grok-4-1-fast-reasoning`** — **125 of 288 cells (43.4%)**, and in
particular **Cost mode was 100% Grok**. Cells routed to Claude: **0**. The predicted risk did
not appear, and an unpredicted backend became the cause of unpriced cells.

### (2) Reasoning swallowed the output whole

`max_output_tokens = 2048`, and in **20 cells** the OpenAI-family reasoning models (`gpt-5` ·
`gpt-5.5` · `gpt-5.6-sol`) **spent that entire budget on reasoning tokens and produced not one
character of final code** (truncated at reasoning=2048 → output=0 → ungradable). Fifteen of
these 20 clustered in the quality arm, dragging quality grading coverage down to 79.2% — **the
direct cause that voided the run**. (Grok, by contrast, used up to 5,400 reasoning tokens and
still produced a gradable body — output accounting differed by provider.)

### (3) The Grok unpriced cells weren't a "missing rate" — they were **fail-closed working correctly**

This is the most important correction. Seeing the router go to Grok while cost was withheld, I
first suspected "the card is missing a Grok rate," but investigation showed that was the **wrong
diagnosis**:

- The Grok base rate (`input $0.2 / output $0.5 /1M`) is **already in the card** and matches
  Azure Retail exactly.
- In the measurement the Grok cells returned **100% cached input tokens**, but **Azure Retail
  has no cached meter for Grok** (0 rows across all regions and all services — confirmed
  authoritatively). So the card's `cached: null` is **correct**.
- `composite_cost`'s **cached-token fail-closed guard** detected "there are cached tokens but no
  cached rate" and **withheld the cost instead of guessing** — this is not a bug but the
  [03Z-b honesty contract](10-measured-ledger.md) working as designed.

## Why VOID is an asset

This run **failed cleanly** — that is the point:

- **The preregistration voided itself.** The gate I committed (any arm's grading coverage <90%
  → void) fired on, of all things, the quality arm that looked most "expensive" on the surface.
  Had it been after seeing the results, there'd have been a temptation to loosen this rule, but
  the timestamp stopped that.
- **Integrity is perfect.** 288/288 completed, within budget ($3.47/$20), replay byte-for-byte
  identical, zero tamper mismatches. The data is trustworthy — it's just that **this
  configuration** can't support a savings claim.
- **The negative result + three findings become design input for the next experiment.** This
  run told us exactly what to fix to make a valid comparison.

!!! danger "What this run does not claim"
    - **Savings rate**: `router-quality` grading coverage failed to clear the gate, so **the
      comparison itself is void**. `savings_claim_allowed = false`.
    - **Mode ranking**: the cost and pass-rate order is contaminated by finding (2)'s grading
      loss, so it is not a conclusion.
    - **Grok cost**: the Grok cells in the cost and balanced arms were withheld fail-closed —
      no amount (not 0, but **unknown**).

## Next — the two things 03D-2 must fix

| To fix | Why | Effect |
| --- | --- | --- |
| **Raise `max_output_tokens`** (2048 → proposed 8192) | reasoning models spent the budget on reasoning and emitted no code | restore quality grading coverage above 90% → validate the comparison |
| **Decide how to handle Grok cached input** | Retail has no Grok cached meter → withheld fail-closed | price the Grok cells in the cost and balanced arms → make the savings comparison possible |

Both fixes change the config / rate card, so **`plan_hash` changes and a new preregistration +
re-approval are required** — not touching the gate to fit the prior results, but repeating the
same discipline of **re-pinning before seeing the results**.

---

!!! note "Reproduction · evidence"
    - **Preregistration (public · committed):**
      [`benchmarks/original-coding/prereg-03d-router-modes.md`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/benchmarks/original-coding/prereg-03d-router-modes.md)
      — the gate, estimand, prediction, and void criteria are pinned with a timestamp **before**
      the results.
    - **Sealed snapshot (local · gitignored):** the manifest, summary, traces, and source text are
      sealed and bound to `plan_hash`, and `measure replay` re-confirms **byte-for-byte identity**.
      The source text is not published, by contract.
    - **Invariant:** this paid run **does not touch** the bytes of the offline ledger
      (`measured = false`) or [experiment 10](10-measured-ledger.md)'s measurement ledger — the
      three audits are kept separate so none blurs the other's honesty label.
