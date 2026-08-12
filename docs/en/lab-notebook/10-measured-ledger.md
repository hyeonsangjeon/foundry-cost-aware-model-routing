# Experiment 10 · Sealing and re-verifying the measurement record (`measured = true`)

!!! abstract "One-line summary"
    [Experiment 09](09-live-routing-proof.md) recorded the model and usage returned by
    real calls. This experiment writes that existing run to a canonical ledger. A hash
    chain detects changed bytes, and a sealed rate card lets verification recalculate
    every cost from the recorded usage. The committed 5-row ledger
    [`samples/ledger/arena-measured.ledger.jsonl`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/ledger/arena-measured.ledger.jsonl)
    returns `status: PASS` with one command and no credentials or network. **Changing
    even a single byte breaks verification.** The strict offline ledger
    (`measured = false`) remains **entirely untouched**, so the two honesty labels stay
    separate.

## What this experiment is — beyond measured, to **auditable**

- **Situation (why):** experiment 09 was the repository's first `measured = true`, but the
  measurement record was a **flat append-only JSONL**. It had no hash chain and no
  cost replay. The offline experiments (01–08) already have the
  [reproducibility contract](index.md#shared-methodology), but the measured record
  could not answer *"has this number not
  been tampered with, and does it really derive from the recorded tokens?"*
- **Task (what):** seal the measured arena run into a **canonical hash-chain ledger**
  ([`MeasuredJsonlLedger`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/src/router/ledger/measured.py)).
  Each row stores a `record_hash` over its canonical payload, links to the prior row
  with `previous_hash`, and embeds the rate card used for its cost
  (`pricing_snapshot`). Verification is a single line: `cost-router ledger
  measured-replay`.
- **Experiment (what it verifies):** (1) is **tampering with a measured run detected**,
  (2) does cost **replay deterministically** from the recorded **usage × the sealed
  rate**, and (3) does all of this happen **without touching the strict offline ledger** —
  all three, **yes**.

!!! note "This page's ledger re-seals measured usage — it is not new spend"
    The committed sample **re-seals** the token usage that was **already measured and
    committed** in experiment 09 / [the arena](08-arena.md)
    ([`samples/responses/foundry-arena-measured.json`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/responses/foundry-arena-measured.json))
    into canonical ledger form — it makes no new Azure call to demonstrate verification
    (zero cost). The sealing logic is **identical** to what the live path
    (`foundry arena --live --ledger`) uses, and it is **byte-for-byte reproducible** because
    `captured_at` is pinned to the capture timestamp. The command to build a new live ledger
    is in [How to reproduce](#how-to-reproduce).

## Two checks every row must pass

Every row must pass **two independent checks**:

| Guarantee | What it stops | Mechanism |
| --- | --- | --- |
| **Tamper detection** | Silently changing any recorded byte | A `record_hash` over the canonical payload + a `previous_hash` chain to the prior row — change one character and the chain breaks |
| **Deterministic cost replay** | Passing a forged cost off as real | The **sealed `pricing_snapshot`** is embedded in the row → verification **re-derives** each call's cost as `usage × that rate card` and checks it matches. Usage is fixed evidence; cost is a pure function of it |

The two audits are **deliberately separate**: the
[offline ledger](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/src/router/ledger/record.py)
holds only `measured = false` projections; this measurement ledger holds only
`measured = true` measured usage. The shared code is only **pure hash primitives**
(`stable_hash` / `canonical_json`), so the hashes are byte-for-byte identical across the two
audits while neither blurs the other's honesty label.

## The end-to-end flow — from a live call to re-verification

```text
  ┌────────────────────────┐   measured usage        ┌───────────────────────────────────┐
  │  foundry arena --live   │ ──(real tokens)──────▶  │  MeasuredJsonlLedger               │
  │  (keyless Entra calls)  │                         │  · seal each row with record_hash  │
  │  cheapest·premium·      │   sealed rate card       │  · chain rows via previous_hash    │
  │  ensemble·router        │ ──(pricing_snapshot)──▶ │  · embed usage×rate into each row  │
  └────────────────────────┘                         └────────────────┬───────────────────┘
                                                                       │  append-only JSONL
                             ┌───────────────────────────────────┐     ▼
   status: PASS / FAIL  ◀──  │  ledger measured-replay           │   arena-measured.ledger.jsonl
                             │  · verify chain integrity         │
                             │  · re-derive cost: usage×sealed   │
                             └───────────────────────────────────┘
```

The key point: the ledger is **self-contained**. Verification needs no original workload, no
network, no credentials, not even an external rate YAML — each row already carries the rate
card that graded it.

## Anatomy of a measurement-ledger row

One row of `arena-measured.ledger.jsonl` (one arena task = all four arms) looks like this:

| Field | Meaning |
| --- | --- |
| `schema_version` | Ledger schema version (currently `1`) |
| `captured_at` | Sealing time (ISO-8601) |
| `pricing_version` · `pricing_hash` | The sealed rate card's version and its SHA-256 fingerprint |
| **`pricing_snapshot`** | The whole rate card this row was graded against (base rates + rates per model that appears) — **the basis for cost replay** |
| **`outcome`** | One measured arena result: `task_id` · `arms{cheapest·premium·ensemble·router}` · each arm's `calls[]` (model · **measured usage** · cost · latency) · `labels.measured = true` |
| **`previous_hash`** | The prior row's `record_hash` (the first row is `null` = genesis) |
| **`record_hash`** | SHA-256 over all of the above — this row's **tamper-detection seal** |

The committed sample's first row, for example: `task_id = t-0001`, arms =
`cheapest·ensemble·premium·router`, `labels = {measured: true, provenance: live, cost_basis:
list-price, spend_source: provider-usage}`, `pricing_snapshot.models = [gpt-5.4, gpt-5.4-mini,
gpt-5.4-nano, grok-4-1-fast-reasoning]`, `previous_hash = null` (genesis).

### The hash chain (the committed 5 rows)

Each row's `record_hash` becomes the next row's `previous_hash`, forming an **unbroken
chain** — delete, insert, or modify any row and the chain breaks right there:

```text
  t-0001   previous_hash = null (genesis)   record_hash = 2ebe46b76991…
  t-0003   previous_hash = 2ebe46b76991…    record_hash = 9f70f421498e…
  t-0004   previous_hash = 9f70f421498e…    record_hash = a3d0d95451ff…
  t-0005   previous_hash = a3d0d95451ff…    record_hash = 89b6da64fa12…
  t-0006   previous_hash = 89b6da64fa12…    record_hash = 8847b126d77e…
```

## Verification — `status: PASS` in one line

```bash
cost-router ledger measured-replay --ledger samples/ledger/arena-measured.ledger.jsonl
```

```text
records: 5
replayed: 5
  → each recorded call cost re-derived from its usage × the pinned rate card
  → router arm cost is pricing incomplete — missing Router input markup
     Model Router-derived cost omits the router input-token markup component. Retained as historical output; not publishable and not usable for a savings claim.
status: PASS
```

`replayed == records` means the chain was intact across **all five rows** and every recorded
call cost was re-derived from the sealed rate card to an exact match. The last two lines
indicate the router arm is subject to the pricing annotation — if this ledger has a router row
but the annotation can't be read, verification **closes to `status: FAIL`** (fail-closed).

## Catching tampering — two independent lines of defense

!!! danger "Demo A — cost forgery (not re-sealed): `record_hash` mismatch"
    Secretly change one of the router arm's sealed amounts from `$0.014502`§ to `$0.000001`
    and **do not re-seal**, and the canonical payload no longer matches the `record_hash`, so
    it's caught immediately:

    ```text
    error: invalid measured ledger record at …:3: measured ledger record_hash does not match its canonical payload
    status: FAIL
    ```

!!! danger "Demo B — forge then re-seal (hash valid): cost replay catches it"
    A cleverer attacker who forges the cost and then **recomputes the `record_hash` too**
    passes tamper detection. But a second line of defense remains — verification **re-derives**
    the cost from the sealed `pricing_snapshot`, and the forged value doesn't match `usage ×
    rate`:

    ```json
    {
      "issues": ["arms.router.calls[0].cost_usd"],
      "record_hash": "c566e85cbd18f66e…",
      "task_id": "t-0001"
    }
    ```
    ```text
    status: FAIL
    ```

    The hash chain catches *which bytes* changed. Cost replay checks *whether the cost
    matches the recorded usage*. A forged value fails at least one check while the
    sealed rate card is fixed.

## The honesty boundary — what is measured and what is not

!!! warning "What is measured · what is not"
    - **Measured (real):** the **model** the router picked and the per-call **token usage** —
      the values actually billed by real keyless Entra calls in experiment 09 / the arena
      (`provenance = live`, `spend_source = provider-usage`).
    - **The rates for cost are illustrative (list price).** The tokens are measured, but the
      rates are the public list price
      ([`foundry-5series.yaml`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/pricing/foundry-5series.yaml))
      — **not your tenant's real bill** (`cost_basis = list-price`). Seal a real rate YAML and it
      replays with those values.
    - **The `router` arm amount is incomplete on top of that.** That rate card has **no router
      input-markup line item**, so a routed call's amount is missing one billing item. It is not
      an approximation but **incomplete**, so it's excluded from cost and savings claims (see the
      § in the headline table above). `cheapest` · `premium` · `ensemble`, which call a single
      deployment directly, are **unaffected**.
    - **Re-verification is valid regardless of this flaw.** `measured-replay` checks *"does this
      amount replay from the sealed rate card"* — the fact that the rate card itself is incomplete
      was attached as an annotation rather than by touching the ledger, so all existing hashes still
      verify.
    - **Accuracy is ungraded.** No grader was attached, so whether each answer was right or wrong
      is not in this ledger (the same boundary as experiment 09).
    - **The offline ledger is immutable.** Measured rows go only into this canonical measurement
      ledger and **never** leak into the strict offline ledger (`measured = false`).

## The measured-snapshot headline (the values this ledger sealed)

The four-arm totals of the arena snapshot the ledger froze (measured usage × list rates):

| arm | strategy | total | mean latency‡ |
| --- | --- | ---: | ---: |
| `cheapest` | always the smallest tier | `$0.001191`† | 9.08 s |
| `premium` | always one premium call | `$0.015368`† | 4.11 s |
| **`router`** | **a single `model-router` deployment** | **`$0.020806`**§ | 12.18 s |
| `ensemble` | fan out to 3, then pick the best | `$0.022046`† | 8.33 s |

The models the router actually ran: **`gpt-5.4` × 3 · `grok-4-1-fast-reasoning` × 2**.
†Rates are illustrative, tokens are measured. ‡Measured wall-clock. (The same capture as the
experiment 08 comparison and the experiment 09 measurement.)

!!! danger "§ The `router` row is **incomplete** — do not compare amounts across arms"
    Model Router billing is composite: a **router input-token markup** plus the chosen sub-model's
    input·output. This capture applied sub-model rates only, so the `router` total is a value
    **missing one billing line item**. The ledger bytes, record hashes, and chain hashes are
    **preserved exactly as the originals** (which is why `measured-replay` still returns `PASS`),
    and this fact was attached with a separate versioned annotation
    [`samples/annotations/legacy-router-pricing.annotation.json`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/annotations/legacy-router-pricing.annotation.json).
    `measured-replay`, the report, and the dashboard **load and enforce** this annotation, and if
    it is missing or inconsistent the router cost display **closes fail-closed**. We **did not
    reprice**, because no applicable markup rate at the time is **pinned anywhere in the
    repository** — rather than invent an amount by estimation, we leave the original amount as
    history and exclude it from claims. The other three arms (`cheapest` · `premium` · `ensemble`)
    call a single deployment directly, so they are not subject to the markup and are
    **unaffected**.

## Experiment 09 ↔ Experiment 10

| | Experiment 09 (measured routing) | Experiment 10 (this one) |
| --- | --- | --- |
| What it proves | **what** the router picked (model · usage) | that the measurement record is **tamper-proof and re-verifiable** |
| Output | a live snapshot JSON | a **hash-chain canonical ledger** (`.jsonl`) |
| Verification | response-ID fingerprint (by eye) | `measured-replay` — chain + cost replay (by machine) |
| Reproduction | a live re-run (numbers vary) | **the committed ledger re-verifies offline, deterministically** (`PASS` pinned) |
| Honesty label | `measured = true` | `measured = true` — **the strict offline ledger is immutable** |

If experiment 09 was *"what does the router really pick,"* experiment 10 is *"so that no one can
quietly change that measurement record later, and so that anyone can check it themselves."*

## How to reproduce

```bash
# 1. Re-verify the committed measured ledger in place — offline, deterministic, PASS pinned
cost-router ledger measured-replay --ledger samples/ledger/arena-measured.ledger.jsonl

# 2. Rebuild the committed ledger from the capture artifact — byte-for-byte identical (offline, zero cost)
python scripts/build_measured_ledger_sample.py

# 3. Build a brand-new measurement ledger live — real keyless Entra calls (incurs cost)
cost-router foundry arena --live --max-output-tokens 3000 \
  --pricing samples/pricing/foundry-5series.yaml \
  --ledger  runs-arena.ledger.jsonl
#   → auto-verified right after flush: "ledger: +5 measured row(s) … (hash-chain + cost-replay: OK)"
```

Step 3, like experiment 09, needs credentials and a network, and tokens and cost vary from call
to call. Steps 1 and 2 are a **deterministic audit** that reproduces anywhere — and that is the
heart of this experiment.

---

**Related docs:** [experiment 09 · measured routing](09-live-routing-proof.md) (what it picked) ·
[experiment 08 · arena](08-arena.md) (the offline comparison) ·
[live measurement bridge](../manual/foundry-live.md) ·
[Foundry hands-on configuration](../manual/foundry-setup.md) · [dev log](/foundry-cost-aware-model-routing/ko/lab-notebook/devlog/)
