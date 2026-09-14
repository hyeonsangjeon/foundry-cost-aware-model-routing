# Workload inventory — what can be measured

This table lays out the **workloads (task sets)** the repository currently holds, whether
each one **carries prompts and validation**, and which experiments run on it. The purpose is
narrow: to pin down honestly **which experiments can be measured right now (`measured =
true`) and which are still projection only (`measured = false`)**.

## Current workloads

| Workload | Tasks | Prompts? | Machine validation (`validation`)? | Experiments using it | Measurable? |
| --- | --- | --- | --- | --- | --- |
| `samples/telemetry/mixed-coding-workload.sample.jsonl` | 100 | ❌ none | ❌ none | 01 Try-cheap-first routing · 02 Curated · 05 Ensemble · 06 Fan-out threshold · 07 Single-call · limits · adaptive | ❌ **projection only** |
| `samples/telemetry/curated-arena-live.sample.jsonl` | 5 | ▲ separate fixture | ❌ (human-facing `acceptance` strings) | 08 Four-way comparison (the `arena` command) · 09·10 live routing | ✅ **measured (09·10)** · pass rate ungraded |
| `samples/prompts/curated-arena.sample.json` | 5 | ✅ `{title, prompt, acceptance}` | ❌ | prompt source for the four-way comparison/live runs above | — (prompt fixture) |

### How to read it

- **No prompts** = the task rows are just telemetry (`{task_id, class, difficulty, domain,
  tokens}`), with no `system_prompt`/`user_prompt` to send to a model. So this workload
  **can't call a real model** and can only *project* routing from offline signals
  (`measured = false`).
- **Human-facing `acceptance`** = the curated four-way comparison fixture has acceptance-criteria
  sentences a person reads, not rules a machine uses to auto-decide pass/fail. Scoring
  a measured pass rate needs **machine-readable `validation` rules** ([validation
  rules](customize.md) · `router.validation`).

## So which experiments are measurable today?

**The projection track (experiments 01–08) is still projection** — the 100-task telemetry
above has no prompts, so it can only *project* routing from offline signals (`measured =
false`). But **the measured track (experiments 09·10·11·12·13) has already been measured with
`measured = true`.** Experiments 09 and 10 captured and sealed real Foundry routing on
`curated-arena-live` (5 tasks) above. `curated-24` (24 tasks) — which carries prompts
plus machine validation — is what experiments 11, 12 and 13 used for the paid 4-arm
measurement, an **arm** being one comparison strategy evaluated against the same workload
under the same measurement plan. Each of those runs measured 24 tasks × 4 arms × 3
repeats = 288 planned cells. Experiment 11's **priced-cell total was $3.47** (excluding
the 125 of 288 cells it withheld unpriced) and experiment 12's was **$3.27** with nothing
withheld; the budget was $20 each. A priced-cell total sums only the cells a run could
price and is not an Azure invoice total. Here is the current state of the measured workloads:

| Measured workload | Size | `evidence_tier` | Target experiments | State |
| --- | --- | --- | --- | --- |
| `curated-24` | medium (24 tasks → 288 planned cells per run) | **`directional`** | 11 · 12 · 13 | ✅ **measured** (priced-cell totals: 11 $3.47 with 125 cells withheld · 12 $3.27 with none withheld · 13 $4.20 with 12 withheld; 11 is VOID — its quality arm missed the grading-coverage floor and 43.4% of its cells were unpriced) |
| `hero-100-prompts` | 100 (proposed) | would be the first candidate for a stronger tier | 01 | ⛔ **proposed — the file does not exist in this repository** |

!!! quote "Where the sample-size threshold comes from"
    Microsoft's Model Router evaluation guide advises that **100 or more** workload prompts
    are needed for a statistically reliable result, and that **fewer than 30** give only a
    directional signal. That is why the 24-prompt `curated-24` is `evidence_tier =
    directional`.
    Source: <https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/model-router#evaluate-model-router-for-your-workload>
    (accessed **2026-07-29**) · for the full rule, see
    [Measurement protocol §3.4](measurement-protocol.md)

Because for these two workloads **the prompts are the experiment** (same pipeline, different
prompts = a different experiment), the manifest seals a **workload fingerprint**
(`workload_fingerprint`, SHA-256): if the prompts change, the gap view treats it as a
different experiment. For the schema, validation rules, and swap points, see the
[customization guide](customize.md); for a schema example, see
`samples/workloads/curated.template.jsonl`. For any workload, **before** you run it,
`cost-router measure catalog --workload <file>` previews the outgoing prompts, validation
rules, candidates, and estimated cost with zero paid calls.

!!! note "Honesty boundary"
    This table is the **current implemented state**. `curated-24` is approved and finalized,
    so experiments 11, 12 and 13 ran as paid measurement (`measured = true`). Experiment 11
    was judged **VOID**, but a void measurement is still a measurement. Experiments 09 and 10
    are `measured = true` from live routing capture.

    `hero-100-prompts` is **a proposal, not a file**: no such workload exists in this
    repository yet, so nothing can be measured against it and the projection track's
    figures (experiments 01–08) remain `measured = false` projections. The tasks and
    prompts of a measured workload are content design, so any such workload goes up **as a
    draft and is finalized only after operator approval** — we do not fix the tasks after
    seeing the results (the lesson of experiment 04).
