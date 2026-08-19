# Prompt cache observed in the sealed runs

!!! note "Post-hoc observation · not a preregistered result"
    This page is not a results dashboard. The preregistration for these runs carried
    no cache prediction and no cache gate. Everything below comes from re-reading the
    sealed `traces.jsonl` **after** the results were already in. Zero paid calls were
    made, nothing under `results/` changed, and no published figure moved. Measured
    results that passed a preregistration gate live on the
    [Routing-mode measured results dashboard](03d-results.md); this page is
    deliberately kept out of that place because it is a different kind of claim.

## 1 · What this is

- **Zero paid calls.** The only inputs are the three sealed snapshots' `traces.jsonl`
  and the workload file that produced them.
- `tokens.cached` is present and non-null in **288 of 288 cells** in every one of the
  three runs.
- The re-aggregation reproduces the sealed `summary.json` `cache` block to four
  decimals — **41.2378% · 42.6570% · 23.0228%** for experiments 11 · 12 · 13. This is
  therefore a re-read of an already-sealed value, not a fresh computation beside it.
- Only HTTP 200 rows are aggregated: **845 rows** of 864. The 19 non-200 rows are all
  HTTP 408 and carry `tokens.input == 0`, so they cannot move a ratio.

**Experiment 11 is VOID, and every table below labels it so.** Experiment 11 fell
below its preregistered **grading coverage** bar — the share of cells that returned an
answer that could be graded. That verdict is about grading, not about token
accounting: the cache figures here come from the same `usage` block that priced the
run, and the void does not put them in question. What experiment 11 cannot support is
the arm comparison it was planned for; what is re-read here is not that run's
conclusion but the cache record its traces left behind. The run is kept and labelled
rather than deleted, which is how this repository treats a void measurement
([Experiment 11 · prereg VOID](../lab-notebook/11-router-modes-void.md)).

!!! info "The angle, stated once"
    Cache questions about a *specific model or gateway* ask whether a given model path
    reuses a prefix. This page asks something else: whether a **repeated request
    through one router** lands on the same backend and carries a cache record across
    repeats. Same word, different angle — do not read the numbers here as evidence
    about any model's caching behaviour.

## 2 · Read this before any table below

**A missing field is recorded as zero, so a zero cannot be read.** When the API
response does not report cached tokens at all, the collector writes `0` — exactly the
same value it writes when the API reports that nothing was cached. The two states are
indistinguishable once they are in the trace.

The mechanism, for the record: `_nested_usage_field` (`src/router/foundry_live.py:1003`)
returns `0.0` when the field is absent, and the collector reads
`usage.prompt_tokens_details.cached_tokens` through it (`:950`). So a row with
`cached == 0` may mean either of:

1. the API returned `cached_tokens: 0` — nothing was reused; or
2. the response carried no `prompt_tokens_details` at all — nothing was reported.

**The sealed snapshot cannot separate them.** `raw_outputs/outputs.jsonl` stores only
`content` · `model` · `output_sha256` · `pass` · `repeat_idx` · `task_id`; the original
usage payload is not retained anywhere in the snapshot, so there is nothing left to
re-read that would decide it.

!!! warning "How to read every 0.00% below"
    Each `0.00%` in this page means **"recorded as zero in the trace"** — never "no
    cache hit occurred." Any sentence that turns one of those zeros into a statement
    about caching behaviour is outside what this data supports.

## 3 · What the traces show

### 3-1 · The backend did not change between repeats

For every router arm × task combination, all three repeats recorded the same
`pricing.resolved_model`.

| Experiment | `router-cost` | `router-balanced` | `router-quality` | Combinations that changed |
|---|---|---|---|---|
| 11 (VOID) | 24/24 same | 23/23 same | 24/24 same | **0** |
| 12 | 23/23 same | 23/23 same | 23/23 same | **0** |
| 13 | 24/24 same | 24/24 same | 24/24 same | **0** |

**212 combinations, 0 changes.** The backend varied *by task*, but not between the
repeated requests of one task. This is the one figure on the page that the §2
limitation does not touch — it reads a model name, not a token count.

It is also an observation, not a contract. Nothing in this repository requests or
guarantees that stability (§5).

### 3-2 · Recorded cache ratio per arm

Every ratio is `sum(tokens.cached) / sum(tokens.input)` over HTTP 200 rows, not a mean
of per-row ratios.

| Arm | 11 (VOID) | 12 | 13 |
|---|---|---|---|
| `router-cost` | **93.11%** | **96.47%** | **97.01%** |
| `router-balanced` | 81.23% | 81.32% | 0.00% |
| `router-quality` | 0.00% | 0.00% | 0.00% |
| `direct-premium` | 0.00% | 0.00% | 0.00% |
| **Whole run** | 41.24% | 42.66% | 23.02% |

Every `0.00%` in this table and the ones that follow reads as **"recorded as zero in
the trace"** (§2) — it does not distinguish "nothing was reused" from "nothing was
reported."

### 3-3 · Holding the backend fixed

The split by backend has no exceptions in either direction.

| Backend | Experiment | Rows | Rows with `cached > 0` | cached / input |
|---|---|---|---|---|
| `grok-4-1-fast-reasoning` | 11 (VOID) | 125 | **125 (100%)** | **95.93%** |
| `grok-4-1-fast-reasoning` | 12 | 125 | **125 (100%)** | **97.68%** |
| `grok-4-1-fast-reasoning` | 13 | 71 | **71 (100%)** | **97.01%** |
| gpt-family (5 deployments) | 11 · 12 · 13 | 524 total | 0 | 0.00% |

All 321 rows resolved to the Grok backend carry `cached > 0`; all 524 gpt-family rows
carry `cached == 0`. No row crosses the line.

Composition per arm, with the ratio **inside** each slice in the last column:

| Experiment | Arm | Backend | Share of arm's rows | cached / input in the slice |
|---|---|---|---|---|
| 11 (VOID) | `router-cost` | `grok-4-1-fast-reasoning` | 100.00% | 93.11% |
| 11 (VOID) | `router-balanced` | `grok-4-1-fast-reasoning` | 82.35% | **99.41%** |
| 11 (VOID) | `router-balanced` | `gpt-5.4` · `gpt-5.5` | 13.24% · 4.41% | 0.00% |
| 12 | `router-cost` | `grok-4-1-fast-reasoning` | 100.00% | 96.47% |
| 12 | `router-balanced` | `grok-4-1-fast-reasoning` | 82.61% | **99.10%** |
| 12 | `router-balanced` | `gpt-5.4` · `gpt-5.5` | 13.04% · 4.35% | 0.00% |
| 13 | `router-cost` | `grok-4-1-fast-reasoning` | 100.00% | 97.01% |
| 13 | `router-balanced` | `gpt-5.6-sol` · `gpt-5.6-terra` | 83.33% · 16.67% | 0.00% |

**With the backend held fixed, the arm that spread its requests is not the lower one.**
Comparing only the Grok slices: `router-balanced` recorded 99.41% against
`router-cost`'s 93.11% in experiment 11, and 99.10% against 96.47% in experiment 12.

The reason `router-balanced` looks lower than `router-cost` at arm level in §3-2 is
arithmetic: rows recorded as zero sit in its denominator, and `router-cost` has none.
Why the composition came out that way, and why the Grok slices ranked as they did, is
not something this page addresses.

### 3-4 · Experiment 12 → 13, where the balanced composition turned over

| | 12 | 13 |
|---|---|---|
| `router-balanced` backends | Grok 82.61% · `gpt-5.4` 13.04% · `gpt-5.5` 4.35% | `gpt-5.6-sol` 83.33% · `gpt-5.6-terra` 16.67% |
| Grok share of the arm | 82.61% | **0.00%** |
| `router-balanced` recorded ratio | 81.32% | **0.00%** |
| Whole run | 42.66% | 23.02% |
| *(control)* `router-cost` backends | Grok 100.00% | Grok 100.00% |
| *(control)* `router-cost` recorded ratio | 96.47% | 97.01% |

**The two moved together.** Grok disappeared from the balanced arm's composition and
that arm's recorded ratio went to zero in the same interval, while `router-cost` — whose
composition did not change — did not move.

That is the whole claim. This page does not say one caused the other, does not rule out
a third factor, and does not decide whether the zero in the right-hand column is a
non-reuse or a non-report. The two runs are also eight days apart, and the traces do
not say whether that matters.

### 3-5 · Within the three repeats

Dispatch is task-major, then repeat, then arm (`run_plan.py:912`), so the second
request for a prompt always goes out after the first. Aggregating `router-cost`, whose
rows are 100% Grok in all three runs:

| Experiment | Repeat 1 | Repeat 2 | Repeat 3 |
|---|---|---|---|
| 11 (VOID) | 83.64% | 95.67% | **100.00%** |
| 12 | 89.61% | 100.00% | **100.00%** |
| 13 | 90.79% | 100.00% | **100.00%** |

No task moved the other way:

| Experiment | Tasks | repeat 2 > repeat 1 | repeat 2 = repeat 1 | repeat 2 < repeat 1 |
|---|---|---|---|---|
| 11 (VOID) | 24 | 11 | 11 | **0** |
| 12 | 23 | 10 | 13 | **0** |
| 13 | 24 | 10 | 13 | **0** |

At cell level: among task × arm combinations that resolved to the Grok backend, the
count whose repeats 2 and 3 recorded `cached == input` — the whole prompt logged as
cached:

| Experiment | Whole prompt cached at repeats 2 · 3 | Combinations |
|---|---|---|
| 11 (VOID) | **40** | 43 |
| 12 | **41** | 42 |
| 13 | **24** | 24 |

!!! warning "Repeat 1 is not a cold baseline"
    In all three runs the **first paid call of the run** — `span-gaps · router-cost ·
    repeat 1` — already recorded `cached = 149 / input = 155`. Nothing preceded it
    inside the run, so that value is not produced by anything on this page.
    Experiments 11 and 12 further agree on the `cached` value in 266 of their 275
    common cells.

    So the rise from repeat 1 to repeats 2 · 3 is measured **on top of an already
    non-empty state**, and the traces do not say what put it there. Read the table
    above as "repeats 2 and 3 recorded more than repeat 1," not as "the cache warmed
    up." The scope conditions in §6 — four system prompts shared across 24 tasks,
    143–359 input tokens per cell — belong with any citation of this section for the
    same reason.

## 4 · Three things this cannot settle

1. **Whether caching worked on the gpt-family rows.** Their `0` is unreadable per §2,
   and the sealed snapshot holds nothing that would decide it. **Not determinable.**
2. **Where the cache at the start of each run came from.** Every run's first cell was
   already non-empty and the traces carry no information identifying the source.
   **Not determinable.**
3. **Causation anywhere on this page.** §3-4 records that two quantities moved
   together. Which one moved which, or whether something else moved both, is outside
   what a re-read of these traces can reach.

Three further limits worth stating: the routing decision itself is not exposed in the
response or the trace, so why the router picked a given backend is unknown; the
stability in §3-1 is an observation about three runs and not a guarantee about future
ones; and no cost claim is made here, because one of experiment 11's void findings was
a missing cached rate in the rate card, and cached-rate lineage was not re-checked for
this page.

!!! abstract "Framing"
    None of this says the Model Router is bad for caching, and none of the figures
    above would support that. Distributing requests across backends and reusing a
    prefix on one backend serve different ends; **they are a trade-off, not a defect.**
    In fact, with the backend held fixed the spreading arm was not the lower one
    (§3-3), and repeated requests for the same prompt went to the same backend (§3-1).

    The precise answer to "is a cache hit guaranteed" is still **no, it is not
    guaranteed.** What this page adds is the next sentence: in these three runs over 24
    coding tasks in one tenant, no repeated request changed backend, cells that
    resolved to Grok logged the whole prompt as cached from repeat 2, and the
    gpt-family zeros remain unread.

## 5 · No cache-hint mechanism in this repository

The repository was searched file by file — no web lookup. **Nothing in an outgoing
request is set as a cache key, a session hint, or a backend-affinity signal.** Cached
tokens are only ever *read back* from the response.

There are exactly two egress sites, both in `src/router/foundry_live.py`:

1. **OpenAI-compatible chat completions** (`:591–598`) — the Model Router and gpt-5.x
   path. The complete kwargs list is `model` · `messages` · `max_completion_tokens`,
   plus `temperature` only when it is not `None`.
2. **Azure AI Model Inference** (`_complete_foundry`, `:611–616`) — the partner path.
   `model` · `messages` · `max_tokens`, and nothing else.

No `prompt_cache_key`, `user`, `safety_identifier`, `seed`, `metadata`, `store`,
`extra_headers`, or `extra_body`. No `default_headers` on either client constructor
(`AzureOpenAI` `:640–653`, `ChatCompletionsClient` `:685–701`). Messages are built as
plain `{"role", "content"}` dicts with no cache-bucket prefix. A repository-wide search
for `extra_headers`, `default_headers`, `extra_body`, `x-ms-`, `x-request-id`,
`request_id`, `correlation_id`, `session_id`, `affinity` and `sticky` returns nothing
(the single `sticky` is CSS).

The repository pins this absence itself:
`tests/test_run_plan_field_readers.py:371–376` asserts that `seed` never appears in
`foundry_live.py`'s source, and the plan's `seed.random_seed` is registered as a
reader-less field that enters `plan_hash` and no model API.

**The one mention of `prompt_cache_key` is documentation, not implementation.**
[Core concepts](concept.md) lists `prompt_cache_key` bucketing under the Govern layer
and states that the router "consumes this layer as a **dependency** from the companion
toolkit instead of reimplementing its math." There is no such dependency in
`pyproject.toml`, no bucketing code, and no call site. It is a declaration, not wiring.

The dispatch order in §3-5 is documented only as a determinism property
(`run_plan.py:912`: `"task-major, then repeat, then arm; deterministic"`). Nothing in
the code or its comments presents it as a cache optimisation, so the repeat pattern is
an observation derived from that order, not the result of a design aimed at caching.

## 6 · Scope

Everything above is bounded by this population, and no wider:

- **24 coding tasks** from `benchmarks/original-coding/tasks.jsonl` — Python 3.12
  implement/fix exercises, `source: original` · `license: MIT` ·
  `contamination_risk: low`, across five types and three difficulty levels.
- **Four distinct system prompts, shared across the 24 tasks** (11 · 5 · 4 · 4).
- **143–359 input tokens per cell** — short prompts.
- **4 arms × 3 repeats = 288 cells per run**, over **3 runs**, in a **single tenant**
  and a **single region**, observed on 2026-08-06 (two runs) and 2026-08-14 (one).

`evidence_tier = directional`. Every ratio above is a value **recorded in these 24
tasks, this tenant and these three executions** — not an estimate of a cache hit rate
in general. Short prompts and system prompts shared between tasks are conditions that
bear directly on what a cache record looks like, so they travel with any citation of
this page.

The narrative record of the runs themselves is in the lab notebook —
[Experiment 11 · prereg VOID](../lab-notebook/11-router-modes-void.md) ·
[Experiment 12 · Routing-mode paid measured re-run](../lab-notebook/12-router-modes-measured.md) ·
[Experiment 13 · router three modes · run 3](../lab-notebook/13-router-modes-rate-card-gap.md).
