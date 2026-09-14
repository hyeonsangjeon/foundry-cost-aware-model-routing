# Experiment 11 · Comparing the router's three modes · run 1 (measurement failed)

!!! abstract "One-line summary"
    An **arm** is one comparison strategy evaluated against the same workload under the
    same measurement plan. This first **paid 4-arm measured comparison** ran the router's
    Cost · Balanced · Quality modes and a direct `gpt-5.6-sol` arm on the same 24 coding
    tasks — 24 tasks × 4 arms × 3 repeats = 288 planned cells. The preregistration — the
    workload, hypotheses and pass/fail criteria, committed before the paid run — required
    every arm to clear the grading-coverage gate.

    **The run is VOID on two independently sufficient grounds.** The `router-quality` arm
    reached a grading coverage of **79.2%, below the 90% floor**. Separately, **43.4% of
    the run's cells were unpriced**, so the run is cost-incomplete and could not carry a
    cost comparison even at full grading coverage. Either failure alone voids the planned
    comparison. The run still recorded that quality cost more than premium, that Cost mode
    used Grok, and that reasoning consumed the output budget.
    [Experiment 09](09-live-routing-proof.md) records router choice, and
    [experiment 10](10-measured-ledger.md) records how measured usage is sealed.

!!! warning "This page records a real paid run — the only approved spend"
    Unlike experiments 01–10, which were offline projections or re-seals of already-captured
    usage, this experiment is **a real Azure inference run executed after passing explicit
    approval gates: operator approval, then approval of the hashed run plan**. The
    **priced-cell total was $3.467533 against a $20.00 budget**. That total sums only the
    cells this run could price: **125 of its 288 cells were withheld unpriced**, so their
    charges are absent from it, and it is not an Azure invoice total. Keyless
    Entra, sequential execution in a deterministic dispatch order (task-major → repeat → arm).
    `max_output_tokens` is the only request parameter that comes from the plan; sampling
    temperature is the service default, which this repository neither sets nor records.
    The prompt and response **text is not published**
    — the sealed snapshot stays local (gitignored), and only `output_sha256` (grading
    evidence) rides in the public trail (the same source-preservation contract as
    [experiment 10](10-measured-ledger.md)).

## What was asked — "do the three modes really split on cost and quality?"

- **Situation (why):** the router has three routing modes, `Cost` / `Balanced` / `Quality`.
  Offline projections merely **assumed** "Cost is cheap and Quality is accurate"; whether
  cost and pass rate really split in that order **by measurement** on the same workload had
  never been verified.
- **Task (what):** wire four arms — `router-cost` (Model Router in Cost mode; mode=Cost) ·
  `router-balanced` (Model Router in Balanced mode; no routing block = the Balanced default) ·
  `router-quality` (Model Router in Quality mode; mode=Quality) · `direct-premium` (calling
  the premium model directly · `gpt-5.6-sol`) — onto the 24 curated coding tasks in
  [`benchmarks/original-coding`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/tree/main/benchmarks/original-coding).
  `24 tasks × 4 arms × n=3 = 288 cells`, deterministic exec-signal grading, cost computed with
  the v2 synthetic rate card.
- **Discipline (pinned first):** before seeing the results, the quality gate, estimand,
  predicted direction, and void criteria were committed to
  [`prereg-03d-router-modes.md`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/benchmarks/original-coding/prereg-03d-router-modes.md).
  **The timestamp is the proof** — it can't be edited later to fit the results.

<figure markdown="span">
  ![Cost vs pass-rate scatter (experiment 12, the publishable re-run): direct-premium costs less and has a higher pass rate than router-quality; router-cost has the lowest cost at the same pass rate](/foundry-cost-aware-model-routing/assets/03d/cost-vs-quality-scatter.en.svg)
  <figcaption>For contrast — this scatter is <strong>experiment 12's (the publishable re-run)</strong> cost vs pass rate. Experiment 11 is VOID at the grading-coverage gate and has no publishable chart of its own, so we show experiment 12's result — produced after fixing the two causes — as a contrast. Directly below is experiment 11's voided measured table.</figcaption>
</figure>

## Result — grading coverage · pass rate · cost per arm

| arm | routing mode | grading coverage | task pass rate | unpriced share | measured cost |
| --- | --- | --- | --- | --- | --- |
| `router-cost` | Cost | 95.8% (69/72) | 95.8% (23/24) | **95.8%** (all Grok) | — · *cost-incomplete* |
| `router-balanced` | Balanced | 94.4% (68/72) | 95.8% (23/24) | **77.8%** (56/72 Grok) | $0.259 · *cost-incomplete* |
| `router-quality` | Quality | **79.2% (57/72)** ❌ | 79.2% (19/24) | 0% | $1.791 |
| `direct-premium` | — (`gpt-5.6-sol`) | 93.1% (67/72) | 91.7% (22/24) | 0% | $1.417 |

- **Priced-cell total $3.467533 / $20 budget** — the sum over the cells that could be
  priced, excluding the **125 of 288 cells withheld unpriced**, and not an Azure invoice
  total. · 288/288 cells completed (partial=false) · 429 throttles
  **0** · 7 timeouts (HTTP408, handled per the retry policy) · replay **byte-for-byte
  identical** (`cost_mismatches: []`).
- The `router-cost` arm's amount reads **—**, not $0.00: every one of its priced cells was
  withheld, so the arm has **no amount**, which is not the same as an amount of zero.
- **Aggregate grading coverage is 90.6% (261/288), which just clears 90%**, but the gate is
  *per-arm*. `router-quality` reached **79.2%**, so the whole comparison is voided on that
  ground alone.
- **43.4% of cells were unpriced** (125 of 288, all routed to Grok). That makes the run
  cost-incomplete, which independently blocks the cost comparison the run was planned for.

## The preregistered prediction was wrong — **recorded as-is, not edited**

The preregistration predicted `cost ≤ balanced ≤ quality ≤
premium` for spend and
expected quality to have the highest pass rate. The measurement differed in two ways:

- **Cost:** `quality ($1.791) > premium ($1.417)`. Quality mode's premium sub-model
  choice was **more expensive** than direct premium, with no measured quality advantage.
- **Pass rate:** quality was the **lowest** (0.792). Finding (2) below explains why,
  so this number should not be read as a direct quality ranking.

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

### (2) Reasoning used the output budget before code appeared

`max_output_tokens = 2048`, and in **20 cells** the OpenAI-family reasoning models (`gpt-5` ·
`gpt-5.5` · `gpt-5.6-sol`) **spent that entire budget on reasoning tokens and produced not one
character of final code** (truncated at reasoning=2048 → output=0 → ungradable). Fifteen of
these 20 clustered in the quality arm, dragging quality grading coverage down to 79.2% — **the
direct cause that voided the run**. (Grok, by contrast, used up to 5,400 reasoning tokens and
still produced a gradable body — output accounting differed by provider.)

### (3) The "missing rate" diagnosis was wrong; the guard withheld Grok cost correctly

Seeing the router go to Grok while cost was withheld, I first suspected
"the card is missing a Grok rate," but investigation showed that was the **wrong
diagnosis**:

- The Grok base rate (`input $0.2 / output $0.5 /1M`) is **already in the card** and matches
  Azure Retail exactly.
- In the measurement the Grok cells returned **100% cached input tokens**, but **Azure Retail
  has no cached meter for Grok** (0 rows across all regions and all services — confirmed
  authoritatively). So the card's `cached: null` is **correct**.
- `composite_cost`'s **cached-token missing-rate guard** detected "there are cached tokens but no
  cached rate" and withheld the cost claim rather than guessing at the missing rate. That
  fail-closed behaviour is not a bug: it is the
  [rate-card honesty contract](10-measured-ledger.md) working as designed.

## Why the VOID result is still useful

This run failed its preregistered gate but left usable evidence:

- **The preregistration voided itself.** The gate committed in advance (any arm's grading
  grading coverage below 90% → void) fired on, of all things, the quality arm that looked most
  "expensive" on the surface. Had the rule been written after the results were visible, there
  would have been a temptation to loosen it; the timestamp stopped that.
- **Integrity is perfect.** 288/288 completed, within budget (priced-cell total $3.47 against $20), replay byte-for-byte
  identical, zero tamper mismatches. The data is trustworthy — it's just that **this
  configuration** can't support a savings claim.
- **The negative result and three findings identify the next changes.** They show what
  must be fixed before a valid comparison can run.

!!! danger "What this run does not claim"
    - **Savings rate**: two separate failures block it. `router-quality` grading coverage did
      not clear the gate, and 43.4% of cells were unpriced, so **the comparison itself is
      void**. `savings_claim_allowed = false`.
    - **Mode ranking**: the cost and pass-rate order is contaminated by finding (2)'s grading
      loss, so it is not a conclusion.
    - **Grok cost**: the Grok cells in the cost and balanced arms were withheld fail-closed —
      no amount (not 0, but **unknown**).

## Next — the two things the re-run ([experiment 12](12-router-modes-measured.md)) must fix

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
