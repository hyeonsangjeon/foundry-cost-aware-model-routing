# Workload inventory — what can be measured (B1)

This table lays out the **workloads (task sets)** the repository currently holds, whether
each one **carries prompts and validation**, and which experiments run on it. The purpose is
narrow: to pin down honestly **which experiments can be measured right now (`measured =
true`) and which are still projection only (`measured = false`)**.

## Current workloads

| Workload | Tasks | Prompts? | Machine validation (`validation`)? | Experiments using it | Measurable? |
| --- | --- | --- | --- | --- | --- |
| `samples/telemetry/mixed-coding-workload.sample.jsonl` | 100 | ❌ none | ❌ none | 01 Hero · 02 Curated · 05 Ensemble · 06 Fan-out dial · 07 Single-call · limits · adaptive | ❌ **projection only** |
| `samples/telemetry/curated-arena-live.sample.jsonl` | 5 | ▲ separate fixture | ❌ (human-facing `acceptance` strings) | 08 Arena · 09·10 live routing | ✅ **measured (09·10)** · coverage ungraded |
| `samples/prompts/curated-arena.sample.json` | 5 | ✅ `{title, prompt, acceptance}` | ❌ | prompt source for the arena/live runs above | — (prompt fixture) |

### How to read it

- **No prompts** = the task rows are just telemetry (`{task_id, class, difficulty, domain,
  tokens}`), with no `system_prompt`/`user_prompt` to send to a model. So this workload
  **can't call a real model** and can only *project* routing from offline signals
  (`measured = false`).
- **Human-facing `acceptance`** = the curated arena fixture has acceptance-criteria
  sentences a person reads, not rules a machine uses to auto-decide pass/fail. Scoring
  measured coverage needs **machine-readable `validation` rules** ([validation
  rules](customize.md) · `router.validation`).

## So which experiments are measurable today?

**The projection track (experiments 01–08) is still projection** — the 100-task telemetry
above has no prompts, so it can only *project* routing from offline signals (`measured =
false`). But **the measured track (experiments 09·10·11·12) has already been measured with
`measured = true`.** Experiments 09·10 captured and sealed real Foundry routing on
`curated-arena-live` (5 tasks) above, and `curated-24` (24 tasks) — which carries prompts
plus machine validation — is what experiments 11·12 used to run the paid 4-arm measurement:
experiment 11 actually spent $3.47 and experiment 12 spent $3.27 (budget $20 each). Here is
the current state of the measured workloads:

| Measured workload | Size | `evidence_tier` | Target experiments | State |
| --- | --- | --- | --- | --- |
| `curated-24` | medium (24) | **`directional`** | 11 · 12 (03D) | ✅ **measured** (11 $3.47 · 12 $3.27; 11 fell short of its prereg and is VOID) |
| `hero-100-prompts` | 100 | first candidate for a stronger tier | 01 | 🚧 **draft, pending approval** |

!!! quote "Where the sample-size threshold comes from"
    Microsoft's Model Router evaluation guide advises that **100 or more** workload prompts
    are needed for a statistically reliable result, and that **fewer than 30** give only a
    directional signal. That is why the 24-prompt `curated-24` is `evidence_tier =
    directional`.
    Source: <https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/model-router#evaluate-model-router-for-your-workload>
    (accessed **2026-07-29**) · for the full rule, see [Measurement protocol §3.4](measurement-protocol.md)

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
    so experiments 11·12 ran as paid measurement (`measured = true`) — experiment 11 was
    judged **VOID** for falling short of its prereg, but a void measurement is still a
    measurement — and experiments 09·10 are `measured = true` from live routing capture. By
    contrast, `hero-100-prompts` is still a draft pending approval, so the projection track's
    (experiments 01–08) figures remain `measured = false` projections. The tasks and prompts
    of a measured workload are content design, so they go up **as a draft and are finalized
    only after operator approval** — we don't fix the tasks after seeing the results (the
    lesson of exp04).
