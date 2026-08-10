# Experiment 09 · The model the Foundry router actually picked (`measured = true`)

!!! abstract "One-line summary"
    Experiments 01–08 were all **offline projections over synthetic telemetry**
    (`measured = false`, placeholder models). This experiment crosses that boundary —
    it **really sends** five curated prompts to a real **Azure AI Foundry Model
    Router** deployment and reads the **actual model** the router picked and the
    **actually billed token usage** (authenticated with **Microsoft Entra ID, no
    key**). Result: a single `model-router` deployment really forked, task by task, to
    **`gpt-5.4` (3) and `grok-4-1-fast-reasoning` (2)**. This is the repository's first
    `measured = true` experiment, and **latency here is real wall-clock too** (in
    contrast to the illustrative projection of experiment 08).

<figure markdown="span">
  ![Azure AI Foundry router architecture — with keyless Entra authentication, the router selects a backend](../assets/azure-architecture.svg)
  <figcaption>The router picks a backend from its own roster and returns the model it actually used in `response.model` — it even routes to backends we never deployed.</figcaption>
</figure>

## What this experiment is — from projection to measurement

- **Situation (why):** all eight of the repository's experiments were honestly
  `measured = false` — deterministic projections over **placeholder** models like
  `mini-fast` and `premium-max`, with no network and no credentials. Powerful, but one
  question always tagged along: *"so when it's wired to real Foundry, what model does
  the router **actually** pick?"*
- **Task (what):** for this work alone we provisioned a new **keyless (Entra-only)
  AIServices resource**, deployed one real **`model-router`** plus **GPT‑5.4-family
  candidates** (`gpt-5.4-nano` · `gpt-5.4-mini` · `gpt-5.4`), and then **really
  called** five curated prompts through the [live bridge](../manual/foundry-live.md).
- **Experiment (what it verifies):** (1) does a single `model-router` deployment fork
  to **different real models** per task, (2) does the response **prove** that choice,
  and (3) does all of this happen with **no key, only an Entra token** — all three,
  **yes**.

!!! danger "This is not a contract experiment or a deterministic reproduction — it's a live measurement snapshot"
    Experiments 01–08 are **offline, deterministic** experiments with `expect`
    floors/ceilings, so CI reproduces the same numbers every time. This experiment is
    different in kind — it's a **live call**, so tokens, cost, and latency vary from
    call to call (that's the essence of `measured = true`), and the table here is **a
    single measured snapshot**. The repository's default paths, CI, and tests don't run
    this experiment (a no-op without credentials and a network) and remain pure
    standard-library and deterministic.

## How it was done — a single deployment, the router forking inside

The key point is that **there is only one deployment to call (`model-router`)**. We
don't pick a specific model — the Model Router reads the prompt, routes **internally**
to a suitable backend model, and returns that choice in the **response's `model`
field**.

```text
                         ┌────────────────────────────────────────────────┐
  5 prompts     ──────▶  │  single deployment:  model-router (2025-11-18)  │
  (model=model-router)   │  — the router reads the task, picks a backend — │
                         └───────────────────┬───────────────┬────────────┘
                                             │               │
                    response.model =         ▼               ▼
                            gpt-5.4-2026-03-05         grok-4-1-fast-reasoning
                            (t-0003·0004·0005)          (t-0001·0006)
```

- **Request:** `chat.completions.create(model="model-router", …)` — always the router
  deployment name.
- **Proof:** the response's `response.model` holds the **backend model the router
  actually ran**. This value is the ground truth
  ([`_response_model`](../manual/foundry-live.md)).
- **usage:** the response's **actual `usage`** tokens are recorded as-is
  (`_usage_from_response`) — not synthetic tokens. Multiplying those by a rate yields
  an amount that is incomplete for the router arm alone (see below).
- **Auth:** the resource has `disableLocalAuth=true` (key auth off), so calls go
  **without an API key** — only an Entra token for the `az login` identity
  (`https://cognitiveservices.azure.com/.default`).

## Result — the model the router actually picked (measured snapshot)

!!! danger "The cost column in this table is **incomplete** — do not use it for a cost claim"
    Model Router billing is **composite**: a **router input-token markup** plus the
    **input·output** charges of the **sub-model** the router picked. This capture priced
    it with sub-model rates only, so the `cost†` column below is **missing one billing
    line item**. It is not an approximation — it is **incomplete**. We leave the original
    amounts as history and exclude them from any cost or savings claim. The rationale and
    scope are pinned in the versioned annotation
    [`samples/annotations/legacy-router-pricing.annotation.json`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/annotations/legacy-router-pricing.annotation.json),
    and the renderer, publisher, and replay **enforce** it (if the annotation is missing or
    inconsistent, the router cost output is closed). **Model selection, usage, latency, and
    auth are unaffected.**

| task | class | requested deployment | **model the router actually served** | in | out | reasoning | cost† | latency‡ |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| t-0001 | generate | `model-router` | **`grok-4-1-fast-reasoning`** | 54 | 0 | 1078 | `$0.004326`† | 11.11 s |
| t-0003 | repo_patch | `model-router` | `gpt-5.4-2026-03-05` | 72 | 541 | 10 | `$0.002276`† | 6.72 s |
| t-0004 | plan | `model-router` | `gpt-5.4-2026-03-05` | 50 | 1032 | 158 | `$0.004810`† | 12.19 s |
| t-0005 | validate | `model-router` | `gpt-5.4-2026-03-05` | 53 | 543 | 76 | `$0.002529`† | 7.10 s |
| t-0006 | test | `model-router` | **`grok-4-1-fast-reasoning`** | 59 | 0 | 1293 | `$0.005187`† | 10.84 s |

†An **incomplete** historical amount, missing the router input markup. ‡Measured
wall-clock.

**Tally of the models the router used:** `gpt-5.4-2026-03-05` × 3 ·
`grok-4-1-fast-reasoning` × 2. `selection = azure-model-router` · `provenance = live` ·
`measured = true` · `spend_source = provider-usage`. The routing distribution was
**identical** across two independent runs (the task→model mapping was stable); only
tokens, cost, and latency varied from call to call — the essence of a live measurement.

## Proof it's real — the response-ID format differs by model

The two backends return **response IDs in different formats** — a strong fingerprint,
impossible to fake with a mock, that different real backends served them:

| serving model | response-ID format | example |
| --- | --- | --- |
| `gpt-5.4-2026-03-05` | OpenAI-standard `chatcmpl-…` | `chatcmpl-E3cromf…` |
| `grok-4-1-fast-reasoning` | pure UUID | `cca8d752-05f4-40…` |

And real answer text came back too (`finish_reason = stop`, no truncation):

- **t-0001 · grok** — a Python code block that really implements `slugify()` with `import re`.
- **t-0006 · grok** — a real `unittest` test for `merge_intervals`.
- **t-0003·0004·0005 · gpt-5.4** — a repo-patch plan · a cursor-pagination design · a retry-diff review, all really written.

## The honesty boundary — what is measured and what is not

!!! warning "What is measured · what is not"
    - **Measured (real):** ① the **model** the router picked (response `model`), ② the
      **token usage** (response `usage`), ③ **latency** (wall-clock — measured here,
      unlike the projection of experiment 08), ④ **keyless Entra auth**.
    - **Not measured:** **accuracy (pass/fail).** We did not inject a `grader`, so whether
      each answer was *correct* was not graded → `coverage_measured = false`. Only by
      wiring in a real apply/compile/test harness does accuracy become measured too.
    - **Router-derived cost is incomplete.** The tokens are measured, but the amount for a
      routed call is computed with **sub-model rates only** and is **missing the router
      input markup**. It is not an approximation but an **incomplete** value with one
      billing line item missing, so we keep it as history only and exclude it from cost and
      savings claims. The rates themselves are illustrative, too, so this is **not your
      tenant's real bill**. The arms that call a single model directly (`cheapest` ·
      `premium` · `ensemble`), by contrast, are not subject to the markup and are
      **unaffected**.
    - **A live snapshot.** This resource was created for this work, and the numbers in the
      table are a single measured snapshot. Re-run it and the routing decision stays the
      same, but tokens, cost, and latency may change.

## Experiments 01–08 ↔ Experiment 09

| | Experiments 01–08 | Experiment 09 (this one) |
| --- | --- | --- |
| Data | synthetic telemetry | real prompts → real responses |
| Models | placeholders (`mini-fast`…) | **real** (`gpt-5.4` · `grok-4-1-fast-reasoning`) |
| Label | `measured = false` | **`measured = true`** |
| Latency | illustrative projection (08) | **measured wall-clock** |
| Accuracy | offline signals (`is_clean`) | ungraded (`coverage_measured = false`) |
| Reproduction | deterministic (pinned by CI) | live snapshot (varies per call) |

If experiment 08 was the **offline lens** that "looked at one problem four ways,"
experiment 09 is the **measurement** that wired that router arm into **real Foundry** to
see what the router truly picks.

## How to reproduce

Prerequisites: a keyless Entra resource with a `model-router` deployment + GPT‑5.4-family
candidates, and in `.env` `AZURE_AI_FOUNDRY_ENDPOINT` ·
`AZURE_AI_FOUNDRY_MODEL_ROUTER=model-router` · `AZURE_AI_FOUNDRY_AUTH=entra`. Then a single
`az login` (device code).

```bash
# 1. Check the connection — confirm credentialed: yes / auth: Microsoft Entra ID (keyless)
cost-router foundry status

# 2. Live run — call the curated prompts through the real router (measured = true)
cost-router foundry live --live \
  --workload samples/telemetry/curated-arena-live.sample.jsonl \
  --pricing  samples/pricing/illustrative.yaml \
  --store    runs.jsonl --json
```

Check the summary's `labels.measured = true` · `model_counts` (a count per model the
router actually picked) · `total_tokens`. A `total_cost_usd` comes out too, but the
router-derived amount is **incomplete** for the reason above, and the summary's
`router_cost_disclosure` block states that fact. Arbitrary prompts work the same way —
`--workload my-prompts.jsonl`. To measure grading too, inject a `grader` (see the
[foundry-live manual](../manual/foundry-live.md)).

## Experiment 08 as a measurement — a 4-way live arena

There's a new command that runs experiment 08's "one problem × four ways" entirely as
**real Foundry calls**. It really calls the four arms `cheapest` · `premium` · `ensemble` ·
`router` to **measure usage and latency** (accuracy ungraded — measurable by injecting a
grader). The single-model arms' amounts have the rate card applied directly, but **the
`router` arm's amount is incomplete because the router markup is missing**, so the report
does not emit any router savings figure at all.

```bash
# 4-way live arena — real cost, real latency, saved to report/ledger
cost-router foundry arena --live \
  --workload samples/telemetry/curated-arena-live.sample.jsonl \
  --pricing  samples/pricing/foundry-5series.yaml \
  --out samples/responses/foundry-arena-measured.json \
  --ledger runs-arena.jsonl
```

Measurement snapshot (captured):
[`samples/responses/foundry-arena-measured.json`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/responses/foundry-arena-measured.json)
— `router_model_mix = {gpt-5.4: 3, grok-4-1-fast-reasoning: 2}`, `measured = true`.

!!! quote "An honest observation — the live router optimizes for quality"
    Offline experiment 08 projected the router as the "cheapest correct answer," but the
    **measured router optimizes for quality, sending fairly ordinary coding problems to a
    reasoning model** — two of the five calls went to the reasoning model (`grok`). This is
    an observation about **model selection**, evidenced by the response's `model` field.
    But **you cannot compare which side is cheaper here** — the router-derived amount is
    missing the router input markup, so a cost contrast against a fan-out ensemble or a
    single `gpt-5.4` doesn't hold. Structurally, the router is 1 call / 1 charge per prompt
    while fan-out is N calls / N charges — that **call-count** difference remains, but it
    doesn't by itself imply which is cheaper. For setup and rationale, see the
    [Foundry hands-on configuration manual](../manual/foundry-setup.md).

---

**Related docs:** [Foundry hands-on configuration · per-experiment setup](../manual/foundry-setup.md) ·
[live measurement bridge](../manual/foundry-live.md) · [experiment 08 · arena](08-arena.md)
(the offline lens) · [dev log](devlog.md)
