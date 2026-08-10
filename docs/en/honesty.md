# Honesty Charter

This project keeps an **authority label** on every numeric and behavioral claim.
This page makes clear what is measured and what is projected, and what we do and
do not claim.

## The modeling vs measurement boundary

| Category | In this repo | Label |
| --- | --- | --- |
| Offline before/after | Projection over synthetic data | `measured = false` |
| Experiment spotlight / savings rate | Projection over synthetic data | `measured = false` |
| Measured experiments 09 · 10 · 11 · 12 (committed) | Real Foundry calls · `evidence_tier = directional` (11 is VOID, below its pre-registration bar) | `measured = true` |
| A live eval in your tenant | Real measurement (scope: the workload you measured) | `measured = true` |

**The offline `hero` and projection-bundle figures are projections over synthetic
data** (`measured = false`). The **measured experiments 09 · 10 · 11 · 12, by
contrast, are `measured = true` results from real Azure Foundry calls**; 09 · 10 ·
12 carry `evidence_tier = directional` (24 tasks · single tenant · one measurement),
so read them only as a directional signal. Experiment 11 is `measured = true`, but
one arm failed to clear the grading-coverage gate set by pre-registration, so it is
ruled **VOID** — void or not, a measurement is still a measurement, so it stays in
the track. That live measurement path is implemented by the
[live measurement bridge](manual/foundry-live.md) — it computes cost from the token
usage of a real Azure Model Router and grants `measured = true` only to live calls.
To see measured savings on your own workload, run this path in your tenant yourself.

## Claim-authority labels

- **Tier 1 — vendor spec.** e.g. the `retry-after-ms` acceptance signal, documented
  cache-key thresholds, published rates.
- **Tier 2 — this project's inference/operating policy.** e.g. the seed
  pass-rate / `$/resolved` priors, escalation thresholds, the "ensemble only above
  value X" rule.

## Placeholder models and pricing (projection track)

- **Projection track (experiments 01–08):** the model names (`mini-fast`,
  `swift-coder`, `balanced-pro`, `deep-reasoner`, `premium-max`) are all generic
  placeholders, not specific products.
- The rates in `samples/pricing/illustrative.yaml` are **dummy values** that match no
  one's published pricing. If you want measured numbers, copy it to
  `your-tenant.yaml` (gitignored) and enter your real rates.
- **Measured track (experiments 09 · 10 · 11 · 12):** uses real Azure deployment
  names and your tenant's real rates (gitignored) — not placeholders. Public
  artifacts keep only aggregates and hashes; endpoint and tenant identifiers are
  masked.

## Billing basis

Today the router picks one execution from pre-computed offline signals, and that
signal lookup is not a model call. So the ledger cost is on a
`selected-execution-only` basis. A future live fan-out layer would have to account
for every panel/judge call separately. → [audit ledger](manual/ledger.md)

## What this is / is not

**This is** an offline-first, deployable router that turns model selection into an
auditable, cost-governed decision and proves the result live.

**What it is not:**

- Not an official Foundry guide.
- Not a measured SLA/throughput model.
- Not a promise of any specific savings figure.

Savings depend entirely on your workload mix and rates — which is exactly why the
proof step runs **in your tenant**.

## Security and reproducibility discipline

- The repo holds no real keys, tokens, connection strings, or live endpoints (a
  verification gate scans for them).
- `.env.sample` carries only valueless placeholder names.
- Every experiment reproduces offline and deterministically.
