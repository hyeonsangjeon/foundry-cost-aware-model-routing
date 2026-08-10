# Measurement Protocol

The repository's experiments 01–08 are **offline projections over synthetic telemetry**
(`labels.measured = false`). The `cost-router measure` runner (`src/router/measure.py`) that this
page specifies is the procedure that turns that projection into **measurement** — it sends real
prompts to a real Azure deployment, reads the **token usage that was actually billed**, computes
cost as that usage × unit price, and seals it in a **fingerprinted, deterministic snapshot**.

!!! danger "Honesty boundary — deliberately strict"
    - **`measured = true` is granted only to a live call that just happened (`provenance = live`).**
      The mock, recorded, and replay paths stay `provenance = test|recorded` and `measured = false`.
      No committed artifact impersonates `measured = true`.
    - **We measure spend, but measure quality only when a grader is present.** Without a grader,
      coverage falls back to an offline-signal projection, and that fact is labeled in the summary.
    - **Live mode is local-only.** CI and automation pipelines run only `measure replay` (no
      credentials needed). A live call must pass operator approval + a budget cap + the prereg gate,
      all three.

---

## 1. Two tracks (D1) — keep projection and measurement separate

| Track | Label | Source | Where |
| --- | --- | --- | --- |
| **projection** | `measured = false` | synthetic signals × illustrative unit prices, deterministic | experiments 01–08 |
| **measured** | `measured = true` | real token usage × unit prices, live calls | `measure --live` snapshots |

The core content is the **gap itself** between the two tracks. When measurement disagrees with the
projection, we don't hide it — we publish it alongside the **direction of the gap we wrote down in
advance in the prereg**.

---

## 2. Command surface

```bash
# 1) Print only the dry-run cost-estimate table and exit (exit 2) — no live calls
cost-router measure run <experiment>

# 2) Only after operator approval: a measured sweep → the §3 snapshot
cost-router measure run <experiment> --live --budget-usd <cap> --yes

# 3) Recompute the summary byte-identically from the snapshot alone, no credentials (CI checks this)
cost-router measure replay --run results/measured/<exp>/<run-id>

# 4) Check a measured snapshot against a range/floor contract (deterministic)
cost-router measure verify --run results/measured/<exp>/<run-id> --contract <contract.yaml>
```

Without `--live`, `measure run` **always prints only the estimate table and exits 2** (the same
safe default as `foundry arena`). Candidates come from `--candidates` or the fleet's ensemble slate,
and unit prices resolve in the order `--pricing` > `FOUNDRY_PRICING_PATH` > the bundled default.

---

## 3. Snapshot specification (§3)

A live run writes **five files** under `results/measured/<exp>/<run-id>/`.

```
manifest.json          # run metadata + SHA-256 fingerprints of every file
prereg.md              # the pre-registered expectations committed "before" the live run (§3.3)
traces.jsonl           # raw record, 1 line = 1 call attempt
summary.json           # coverage · cost · savings · strategy breakdown · latency · 429/retry/cache · failure list
pricing.snapshot.yaml  # seals, verbatim, the unit prices used for this run
```

### 3.1 `manifest.json` fields

`schema_version`, `run_id`, `exp_id`, `timestamp`, `runner_version`, `git_commit`,
`endpoint` (host only, path/key masked), `region`, `deployments`, `candidates` (model/deployment/provider),
`n`, `budget_usd`, `partial`, `stopped_reason`, `measured_cost_usd`, `retry` (backoff parameters),
`pricing_path`, `pricing_version`, `prereg` (commit_hash/committed_at/bypassed/note),
`labels.measured`, `fingerprints` (per-file `sha256:…`).

### 3.2 `traces.jsonl` required fields — 1 line = 1 call attempt

`run_id, exp_id, task_id, repeat_idx(1..n), candidate_model, attempt_idx,`
`tokens:{input,cached,output,reasoning}, latency_ms, http_status, retries,`
`backoff_ms_total, cost_usd, pass|fail, score, fail_reason(nullable), labels:{measured}, ts`

If a 429 is retried, it leaves **one line per attempt**, and when retries are exhausted it marks
`fail_reason="throttle_exhausted"`; the retry itself is marked `fail_reason="throttled_429"` as a
matter of policy.

On the v2 paid path, a cell routed to a **backend whose unit price is unconfirmed** doesn't invent an
amount — it's recorded **fail-closed** as `cost_usd=null` + `pricing.priced=false` (with the reason)
(§6.1).

### 3.3 `prereg.md` minimum contents (D8)

Expected coverage / expected savings rate (a range) · **the expected direction of the gap vs. the
projection and a one-line reason** · what counts as a "failure" in this run · the budget cap.

### 3.4 Sample size and evidence tier (`evidence_tier`)

How many prompts must you run before you can call a result a "result" — this threshold isn't one we
set, it follows **Microsoft's Model Router evaluation guide** verbatim.

> **100 or more** workload prompts are needed for a statistically reliable result, and
> **fewer than 30** give only a directional signal.
>
> — Microsoft Learn, *Evaluate model router for your workload*,
> <https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/model-router#evaluate-model-router-for-your-workload>
> (accessed **2026-07-29**)

So this repository attaches an `evidence_tier` to every workload:

| Workload | Prompts | `evidence_tier` | Basis |
| --- | --- | --- | --- |
| `curated-24` | 24 | **`directional`** | fewer than 30 — directional signal only |
| `hero-100-prompts` | 100 | **first candidate** for a stronger tier | meets the 100-or-more recommendation |

!!! note "Citation-preservation rule"
    The URL and the **access date (2026-07-29)** are preserved together everywhere this threshold is
    attributed to Microsoft. Even if the source later changes, we **keep the access date** and
    distinguish the evidence policy this repository maintains from the current vendor guide.

---

## 4. Determinism and fingerprints

- **n = 3** (default): a cell is (task × arm × sample n), and each (task × arm) combination is
  measured n=3 times to report variance.
- **Deterministic replay (§3.4)**: `measure replay` recomputes `summary.json` **byte-identically**
  from `traces.jsonl` + `pricing.snapshot.yaml` alone (no credentials needed). CI checks only this
  replay.
- **Fingerprints**: every snapshot file's exact bytes are hashed with SHA-256 and recorded in
  `manifest.fingerprints`. If a fingerprint mismatches on replay, it's judged tampering.
- **Serialization**: JSON uses `indent=2, sort_keys=True, ensure_ascii=False` + a newline, and traces
  are one canonical (sorted-key, compact) record per line — pinned so both paths produce the same
  bytes.

---

## 5. Throttling, cache, billing

- **429 backoff**: exponential backoff (defaults `max_retries=5`, `base_backoff_ms=500`,
  `backoff_factor=2`, cap `max_backoff_ms=30000`). The parameters are sealed in the manifest so replay
  reproduces the retry accounting.
- **Cached tokens**: `tokens.cached` is **recorded separately** from input tokens and billed
  separately at the cache price.
- **All-calls billing (D2)**: fan-out (ensemble) strategies bill **the sum of every candidate,
  including the losers** (`billing = sum-all-fanout`). They don't create a "count only the winner"
  illusion — this is the measured basis for the ensemble tax.
- **Budget guard**: when cumulative measured cost reaches `--budget-usd`, it stops immediately, saves
  the partial result as a normal snapshot, and leaves `manifest.partial = true` · `stopped_reason`.
  `--resume <run-id>` skips finished cells and runs to completion from there.

---

## 6. Unit-price source and freshness

- Unit prices use **public models and public prices** only. In the bundled
  `samples/pricing/foundry-ext-full.yaml`, the OpenAI-family rows follow the public Azure list price,
  and the partner rows are **round-number placeholders (not quotes)** kept to make the arithmetic
  transparent — drop in your negotiated rates for real accounting.
- Every published figure carries the **pricing-snapshot date**. `measure verify` raises a
  **non-fatal warning (freshness)** if a snapshot is older than 90 days.

### 6.1 Rate-card schema — v1 (offline experiments) vs. v2 (bench/paid measurement)

This repository deliberately lets **two rate-card schemas** coexist. Which path uses which is fixed.

| Path | Schema | Billing method | Unconfirmed backend |
| --- | --- | --- | --- |
| Offline experiments 01–08 (`replay` · `evals` · `hero` · `compare` · `experiment`) | v1 `PricingTable` (`samples/pricing/*.yaml`) | simple per-table in/out prices, no markup | **fail-open** via the `default` fallback (fine for synthetic experiments) |
| Bench/paid measurement (`benchmark plan` · `benchmark run --live` · `measure run --live` · the live cockpit) | v2 `RateCardV2` (`schema_version: 2`, e.g. `samples/pricing/foundry-ext-router.yaml`) | exact alias map + Model Router **input-token markup** (router arm) + sub-model in/out composed | if not in rates, **fail-closed**: `cost_usd=null`, `cost_complete=false`, excluded from savings claims |

- **Schema decision**: if the card has a top-level `schema_version` key it's read as v2, otherwise v1.
  v1's `version:` is a free revision integer, preserved as-is with no effect on `plan_hash`.
- **Why fail-closed**: leaving the v1 `default` fallback on a paid path would attach an arbitrary
  unit price to a price-unconfirmed backend (e.g. the 5 Claude models with no rate in Azure Retail),
  reviving the "savings figure with no source" that 03Z retired. So the bench path **doesn't fill in a
  price it doesn't know** — it seals that cell as unpriced and blocks the run's savings claim with
  `savings_claim_allowed=false`.
- **Same formula across five surfaces**: a given cell's synthetic cost is **identical** across the
  dry-run estimate · the reservation ceiling · the trace · the summary · the replay. The regression test
  `tests/test_rate_card_wiring.py` pins this identity and fail-closed (router markup · Claude unpriced ·
  v1 unchanged).
- **Tier handling**: a v2 card stores **one conservative long-tier price** per key and reserves at that
  value. If the actual tier is determined, it's reflected at settle; if it can't be determined, long is
  kept (a conservative reservation).
- A sealed snapshot also records which engine did the billing (v2 is `pricing_engine: rate_card_v2` +
  the normalized card). `measure replay` uses that marker to bring the v1/v2 engine back and guarantee
  byte-identical recomputation.

---

## 7. Budget planning (dry-run basis)

Below are planning figures from a **dry-run** of the 5-task prompt-bearing workload
(`samples/telemetry/curated-arena-live.sample.jsonl`) with
`--pricing samples/pricing/foundry-ext-full.yaml` (illustrative, 2025 snapshot) and `--n 3`. The caps
leave headroom above the estimate to absorb output-token variance.

| Experiment | Measurement basis (candidates × tasks × n) | Dry-run estimate | Recommended `--budget-usd` cap |
| --- | --- | --- | --- |
| exp02 Curated (pilot) | 11×5×3 = 165 calls | $1.03 | **$2** |
| exp07 Routing layer | `model-router` 1×5×3 = 15 | $0.21 | **$1** |
| exp03·04·06 Guardrails | 2–11 candidates ×5×3 | $0.22–$1.03 each | **$2 each** |
| exp05 Fan-out (D2) | 11×5×3 = 165 | $1.03 | **$3** |
| exp08 Arena | 11×5×3 = 165 | $1.03 | **$2** |
| exp01 Hero (100 tasks) | ⚠ requires **authoring first** a 100-task prompt workload | ≈$20.6 | **$25** |

!!! warning "The nature of these figures"
    The dollar values are planning estimates from **illustrative** unit prices (partner-row
    placeholders). To measure exp01/exp08 at their full task count, you must first author a
    prompt-bearing workload at that scale. The final budget cap is **finalized on operator approval**.

---

## 8. The `measure verify` contract (7.2)

The contract YAML checks **ranges/floors, not exact values** (the same convention as the offline
`Expectation`). Only the keys that are set are scored.

| Key | Meaning |
| --- | --- |
| `min_coverage` | coverage floor |
| `min_savings_pct` / `max_savings_pct` | savings-rate band vs. naive |
| `max_tax_ratio` | fan-out-tax (highest/lowest candidate cost ratio) ceiling |
| `min_escalation_gain` | floor on the coverage that observe-then-escalate recovers |
| `max_failure_rate` | failure-rate ceiling |

---

## 9. Live-run procedure (operator gate)

1. Confirm `cost-router foundry status` reports `credentialed: yes` (keyless Entra).
2. Pull the dry-run estimate table with `measure run <exp>` and set the **budget cap**.
3. Commit `results/measured/<exp>/prereg.md` **before the run starts** (the D8 gate).
4. After operator approval, run `measure run <exp> --live --budget-usd <cap> --yes`.
5. Replay byte-identically with `measure replay`, check against the contract with `measure verify`,
   then commit the snapshot.

## 10. Live progress indicators are diagnostic (not a verdict)

A detached live run exposes progress through `progress.json` and a one-line stdout. Beyond cell
count, cumulative cost, 429s, and failures, it also carries the **cumulative grading coverage (with
the gate baseline shown)** and the **per-arm pass status**. For example:

```
progress: 142/288 cells  $1.83  429×0  fail×2  cov 96.5% [gate 90%]  [cell_done]
         cost 34/36 · balanced 34/35 · quality 33/36 · premium 36/36
```

Its purpose is exactly one thing — **the decision to abort early**. Had we known at the 30-minute
mark that quality coverage was collapsing to 79% in the last void run, we could have aborted.

!!! danger "Changing the experiment on an interim indicator is a prereg violation"
    These values are **diagnostic, not a verdict.** The coverage gate (90%) and the quality gates
    (min_pass 0.60 / max_drop 10pp) are judged by `measure verify` **against the sealed snapshot
    only**. Looking at an interim value and changing the workload, arm, gate, or denominator is a
    pre-registration violation and voids the result. The only intervention allowed mid-run is an
    **abort (a full stop + a partial snapshot)**.

`progress.json` is written only to the gitignored run directory and is not a fingerprint target
(§4), so it affects neither the snapshot bytes nor the `plan_hash` — replay is still byte-identical.

Related documents: [Live measured bridge](foundry-live.md) · [Audit ledger](ledger.md) ·
[Experiment 09 · Live routing](../lab-notebook/09-live-routing-proof.md) · [Honesty Charter](../honesty.md)
