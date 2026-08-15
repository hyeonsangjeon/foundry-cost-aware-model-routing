# Fix C — transport read/overall timeout proposal (03D-2 follow-up)

> **Status: APPLIED for the 03D-3 run — but not as a repo default.** The proposed
> values (`read 180 / overall 240`) were set in the operator's `.foundry.local.yaml`,
> which is gitignored (`.gitignore:98`); the committed defaults in
> `src/router/run_plan.py`, `src/router/foundry_live.py` and `foundry.example.yaml`
> are still **90 / 120**, so a fresh clone does not inherit this run's timeouts. What
> shipped in the repo is the **plumbing**: PR #101 makes the resolved plan's timeouts
> actually reach the socket (`eafc1a1`) — before it, an operator-approved timeout
> change was a silent no-op that the sealed manifest nonetheless reported as applied.
>
> Raising the timeout changes `benchmark.retry`, which is part of the resolved run
> plan, so it **changed `plan_hash`** and therefore required a **new preregistration +
> re-approval** (the same discipline used for Fix A / Fix B). That is `454c8159`, and
> the run it approved is
> [experiment 13](../../docs/en/lab-notebook/13-router-modes-rate-card-gap.md)
> (`plan_hash sha256:33821119…6b0b50`). **Everything below this banner is the
> proposal as written before the run** — the evidence and the predictions are kept
> unedited so they can be read against what actually happened.

## Problem — the 8192 cap surfaced a fixed-timeout constraint

The 03D-2 measured re-run (`plan_hash d640dc07`, publishable) completed 288/288
with **11 cells (3.8%) failing HTTP 408 (timeout)**. Fix B raised
`max_output_tokens` 2048 → 8192 to stop reasoning models from truncating before
emitting code (the void-run failure mode). That worked for coverage
(79.2% → 96.18%), but longer generations then began to exceed the **fixed
`read_timeout_seconds: 90`**, converting "truncated output" into "no output via
timeout" on the hardest tasks.

The timeouts fell **only on router arms** — never on `direct-premium`
(`gpt-5.6-sol`), whose slowest call was 33.5 s. Router arms route to slower
reasoning backends (`grok-4-1-fast-reasoning`, `gpt-5`, `gpt-5.5`) and add
routing latency, so their tail runs 2–3× longer.

## Evidence — this run's latency distribution

### Every timeout hit the **read** limit, not the overall limit

All 11 failures registered a latency of **90.0–90.7 s** and `http_status 408`.
None reached the 120 s `overall_timeout`. **`read_timeout_seconds: 90` is the
single binding knob.**

| arm | timeouts | tasks (repeats) |
| --- | --- | --- |
| router-cost | 4 | toll-schedule (1,2,3), weekday-label (3) |
| router-balanced | 3 | toll-schedule (1,2,3) |
| router-quality | 4 | toll-schedule (3), dedupe-stable (1,2,3) |
| direct-premium | 0 | — |

### Successful-cell latency (seconds)

| arm | n | p50 | p95 | p99 | max |
| --- | --- | --- | --- | --- | --- |
| router-cost | 68 | 16.2 | 54.5 | 81.8 | **81.8** |
| router-balanced | 69 | 12.4 | 59.8 | 81.1 | 81.1 |
| router-quality | 68 | 12.0 | 38.9 | 71.1 | 71.1 |
| direct-premium | 72 | 4.2 | 26.6 | 33.5 | 33.5 |
| **all success** | 277 | — | 53.8 | 74.8 | **81.8** |

The slowest **successful** call was **81.8 s** (`grok-4-1-fast-reasoning`) — i.e.
successful cells ran right up to the 90 s wall, and cells needing more than 90 s
were cut off.

### How much more did the timed-out cells need? (censored estimate)

The timed-out cells are **right-censored at 90 s** — we only know they needed
`> 90 s`. Sibling repeats of the *same* tasks that did succeed bound it from
below: `toll-schedule` (quality, rep1) finished at **71.1 s**; `weekday-label`
(cost, rep2) at **74.8 s**. Same task, different repeats, 71 s → timeout — high
tail variance right at the boundary. A modest headroom over 90 s (est. **90–150
s**) would very likely have captured them.

## Proposal

| knob | current | **proposed** | rationale |
| --- | --- | --- | --- |
| `read_timeout_seconds` | 90 | **180** | ≈ 2.2× the slowest observed success (81.8 s) and 2.4× p99 (74.8 s); covers the censored `>90 s` tail with margin for full 8192-token reasoning generations |
| `overall_timeout_seconds` | 120 | **240** | keeps `overall > read` with headroom for connect/write/pool (10/30/10 s) + one retry |
| `connect` / `write` / `pool` | 10 / 30 / 10 | unchanged | never implicated |

**Conservative alternative:** `read 150 / overall 200` (≈ 1.8× slowest success)
if faster hang-detection is preferred over eliminating every boundary timeout.

**Why not just lower `max_output_tokens` again?** That reintroduces the void-run
truncation failure. The tokens are needed; the transport budget is what must
accommodate them.

**Streaming (out of scope):** enabling response streaming would reset the read
timeout per chunk (read timeout ≈ inter-token gap instead of total generation),
structurally removing this class of timeout. That is a larger client change and
is **not** proposed here — the minimal, low-risk fix is raising the two timeouts.

## Tradeoffs & guardrails

- A longer read timeout means a genuinely hung request is detected later. This is
  bounded by the unchanged **$20 budget cap** (auto-halt + partial snapshot) and
  operator **abort**; note that timed-out cells bill **$0**, so the cost of
  waiting longer is wall-clock, not spend.
- Expect a modestly **longer wall-clock** re-run (the ~11 slow cells run to
  completion instead of failing at 90 s), but higher coverage and pass-rate:
  the current 4.17 pp router-vs-premium pass-rate gap is **entirely** the three
  fully-timed-out tasks, not code quality — so eliminating the timeouts should
  narrow it.

## If applied (not in this PR)

1. Update `benchmark.retry.read_timeout_seconds` / `overall_timeout_seconds` in
   the run config.
2. Recompute `plan_hash` (config change → new hash).
3. Write a **new preregistration** (fix the gates/estimand/expectations again
   *before* seeing results — gates stay: coverage 90%, min_pass 0.60, max_drop
   10 pp, budget $20) and re-approve.
4. Re-run under the new approved `plan_hash`.

---

## What actually happened (added after the run)

All four steps above were carried out at the proposed values rather than the
conservative alternative — but **only steps 2–4 are in the repo**. Step 1 (the
values themselves) was done in the operator's gitignored `.foundry.local.yaml`;
steps 2–4 (new `plan_hash`, new preregistration `454c8159`, re-run) are PR #101
and the run it approved. Doing step 1 first exposed a second defect: the resolved
plan's transport timeouts were never handed to the live client, so raising them in
config alone changed nothing. That plumbing fix (`eafc1a1`) is the part of Fix C
that is actually committed.

| | 03D-2 (read 90 s) | 03D-3 (read 180 s) |
| --- | --- | --- |
| timeout cells | 11 / 288 | **1 / 288** |
| aggregate grading coverage | 96.18% | **99.65%** |
| lowest arm pass rate | 0.958 (23/24) | **1.000 (24/24)** |

The prediction above — that the 4.17 pp router-vs-premium pass-rate gap was the
timeouts and not code quality — held: with the ceiling raised, every arm solved
every task. The one remaining timeout recorded `latency_ms 180096.8`, i.e. it hit
the new read ceiling and not the 240 s overall budget, the same shape the 90 s
cells showed at 90.0–90.7 s. Streaming stays out of scope and unproposed.

This document is **not** amended to reflect the outcome anywhere above this
section. The 03D-2 latency evidence and the reasoning that followed from it are
the record of what was known at proposal time.
