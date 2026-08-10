# Audit ledger

Routing decisions are recorded in an **append-only, hash-chained JSONL ledger**, and verified
by replaying the stored selection inputs and comparing the canonical final payload **byte for
byte**. Verification passes only when every decision reproduces and required-field completeness
is at least 99%.

## Recording

```bash
cost-router replay --synth --ledger reports/routing.jsonl
cost-router route-once --task-id t-0003 --synth --ledger reports/one.jsonl
cost-router hero --ledger reports/hero.jsonl
```

## Verifying (replay)

```bash
cost-router ledger replay --ledger reports/routing.jsonl
```

```text
records: 100
matched: 100
completeness: 100.0%
status: PASS
```

## The measured ledger — the same integrity, for measured runs

The offline ledger is contractually `measured = false`. Real live calls (the 4-way arena and
the like) accumulate in a **separate measured ledger** (`src/router/ledger/measured.py`,
`MeasuredArenaLedger`), which **never touches the offline ledger** and gets the same two
guarantees:

- **Tamper detection** — each line is sealed with the canonical payload's `record_hash` and
  linked to the previous line by `previous_hash` (the same hash primitive as the offline ledger
  → byte-for-byte identical hashes).
- **Deterministic cost replay** — each line carries the `pricing_snapshot` used to score it, so
  verification recomputes every call's cost from the **recorded usage × that rate table** and
  confirms the match. The measured usage is fixed evidence, the cost is a pure function of it —
  the same spirit as the offline ledger "replaying decisions from stored inputs."

```bash
cost-router ledger measured-replay --ledger runs/arena.jsonl
```

```text
records: 5
replayed: 5
  → each recorded call cost re-derived from its usage × the pinned rate card
  → router arm cost is pricing incomplete — missing Router input markup
     Model Router-derived cost omits the router input-token markup component. Retained as historical output; not publishable and not usable for a savings claim.
status: PASS
```

The last two lines appear only when the ledger has a row recorded with the `model-router`
deployment — because the router-derived amount is **incomplete**, missing the router input
markup. If such a row exists but the pricing annotation can't be read or a hash mismatches,
verification **closes with `status: FAIL`**.

!!! note "The two ledgers are separated on purpose"
    The offline ledger holds offline projections only; the measured ledger holds measured usage
    only. All they share is the pure hash primitive, so neither one blurs the other's
    strictness/honesty labels.

## Correcting a sealed record without editing it — pricing annotation

A sealed ledger is **immutable**. But what if it later comes out that *"the rate basis used to
compute this amount was itself incomplete"*? Editing the bytes would break the hash and, worse,
**fabricate evidence**. So the repository leaves the original untouched and appends a
**versioned annotation**.

There is a real case of this:
[`samples/annotations/legacy-router-pricing.annotation.json`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/annotations/legacy-router-pricing.annotation.json)

- **What was wrong** — Azure Model Router billing is **composite**: the router input-token
  markup + the input/output of the chosen sub-model. The committed rate card **has no markup
  line**, so a routed call's amount is missing one billing component. It's not an approximation
  — it's **incomplete**.
- **What is fine** — token usage, the model the router chose, latency, authentication, and the
  hash-chain integrity. The arms that call a single deployment directly (`cheapest` · `premium` ·
  `ensemble`) aren't subject to the markup, so their amounts are **unaffected**.
- **Why it wasn't repriced** — the markup rate applicable at capture time is pinned nowhere in
  the repository. Back-solving it by estimate would be **inventing a historical cost**, so we
  keep the original amount as historical output and exclude it only from cost/savings claims.

The annotation names its target artifact by **path + `sha256` + byte size**, and for the ledger
it also records **five record hashes and the chain head**. The loader re-reads and re-hashes the
file on every call, so if the artifact changed or the annotation was tampered with, it fails
immediately.

```json
"effects": {
  "pricing_incomplete": true,
  "publishable": false,
  "savings_claim_allowed": false
},
"reprice": { "repriced": false }
```

!!! danger "Fail-closed — without it, things get quieter, not louder"
    Every surface that renders or publishes a `router` amount (the arena report, the `foundry
    live` summary, `ledger measured-replay`, the `/fleet/run` publisher, the dashboard, the static
    build) **loads and enforces** this annotation. If the file is missing, the schema is broken,
    the artifact hash mismatches, or someone flips `savings_claim_allowed` to `true` while
    `repriced: false` — the router cost/savings output **closes to the stricter side** (and
    `measured-replay` returns `status: FAIL`). There is no "delete the annotation to make the
    warning go away" workaround.

    For a reprice to become legitimate, the annotation must bring, **as evidence**,
    `reprice.rate_basis` (the markup rate, sub-rates, and effective date) and a hash-named
    `reprice.superseding_artifact`. Without those, the loader refuses — *no reprice without
    proof* is baked into the schema.

## What goes into a ledger record

Each record is one self-contained, replayable offline routing decision.

- **Policy/pricing hashes + snapshots** — pins which policy and rates made the decision
- **Normalized task profile** — class, difficulty, risk
- **Candidate order and signals** — each candidate's prior, offline signal, and acceptance
- **Gate decision** — selection mode, value, reason (budget-gate-v1)
- **Selected model and cost** — plus the honest offline label
- **Hash chain** — the integrity chain running `previous_hash` → `record_hash`

## Billing basis

The router currently selects one execution from **precomputed offline signals**. That signal
lookup is not a model call. So the ledger cost explicitly uses a `selected-execution-only` basis.

!!! warning "Live fan-out needs separate accounting"
    A future live fan-out layer (an ensemble that actually calls several candidates) must account
    for every panel/judge call **separately, each one**. Don't mistake the offline projection's
    `selected-execution-only` for a live cost. Every record keeps `labels.measured = false`.

## The signal-source seam — the offline ledger's honesty boundary

The router scores decisions against a per-task `model → {applies, compiles, tests_pass,
lint_pass}` signal map. **Where that signal comes from** is now expressed not by scattered
`synth` / `signals_path` booleans but by a single injectable object, `router.signals.SignalSource`:

| Source | `kind` | Allowed in the offline ledger? | Determinism |
| --- | --- | --- | --- |
| `synth_signal_source()` | `synth` | ✅ | deterministic derivation from workload+policy (no I/O) |
| `fixture_signal_source(path)` | `fixture` | ✅ | replay of a checked-in JSON snapshot |
| measured / live provider | `measured` · `live` | ❌ | measurement that actually ran the candidates (out of this repository's scope) |

A `SignalSource` is just a `(workload, policy) -> SignalBundle` callable. A `SignalBundle` binds
the signals to their **source (`kind`)** so the label flowing into the ledger never diverges from
the signals. Every execution entry point (`run_replay` · `run_bundled_replay` · `run_route_once`
· `run_evals`) accepts `signal_source=`, so you can swap the source without touching the flow
code.

```python
from router import run_bundled_replay, synth_signal_source

# Default (offline): synth/fixture as-is — deterministic
report = run_bundled_replay(synth=True)

# Inject a future measured provider (kind="measured")
report = run_bundled_replay(signal_source=my_measured_source)
```

**The honesty boundary (the crux):** the strict hash-chained offline ledger audits **offline
projections only**. A `kind` outside `OFFLINE_SIGNAL_KINDS = {synth, fixture}` (measured · live)
is blocked by `assert_offline_ledger_kind` **before** the record is ever created — inject a
measured signal together with `--ledger` and you get a boundary-specific error and **nothing is
recorded**. Measured spend must go to the separate measured-audit path, so that offline projections
stay uncontaminated.

## Why a ledger

Routing's headline value isn't "the cheapest bill" but getting the same coverage at a lower cost
**with an audit trail for every routing decision**. The ledger makes that audit trail
**reproducible** — you must be able to remake the same decision from the stored inputs alone for
verification to pass.
