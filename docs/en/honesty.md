# Honesty Charter

Every numeric and behavioral claim has an **authority label**. The label tells you
whether the result was measured, computed offline, or taken from a vendor
specification. This page also states what the project does not claim.

## The modeling vs measurement boundary

| Category | In this repo | Label |
| --- | --- | --- |
| Offline before/after | Projection over synthetic data | `measured = false` |
| Experiment spotlight / savings rate | Projection over synthetic data | `measured = false` |
| Measured experiments 09 · 10 · 11 · 12 · 13 (committed) | Real Foundry calls · `evidence_tier = directional` (11 is VOID, below its pre-registration bar; one arm of 13 is cost-incomplete) | `measured = true` |
| A live eval in your tenant | Real measurement (scope: the workload you measured) | `measured = true` |

The offline `hero` and projection bundle use synthetic data (`measured = false`).
They do not report measured savings.

Experiments 09 · 10 · 11 · 12 · 13 use real Azure Foundry calls and are
`measured = true`. Experiments 09 · 10 · 12 · 13 still carry
`evidence_tier = directional`: 24 tasks · single tenant · one measurement. They show
what happened in those runs, not what every workload will do.

Experiment 11 is also `measured = true`, but one arm did not clear the
grading-coverage gate fixed by pre-registration. The result is **VOID**. The
measurement remains in the measured track, but it cannot support the comparison
that was planned.

[Experiment 13](lab-notebook/13-router-modes-rate-card-gap.md) cleared every gate,
but 12 calls in one arm were served by a model the rate card had no row for. Those
cells were withheld fail-closed rather than priced at a guessed rate, so that arm is
**cost-incomplete**: its total is reported and labelled, and it carries no savings
claim. Nothing in an earlier run was recomputed when the card was later corrected.

The [live measurement bridge](manual/foundry-live.md) implements this path. It reads
the token usage from a real Azure Model Router call, computes the cost, and grants
`measured = true` only to live calls. To find the measured savings for your workload,
run it in your own tenant.

## Claim-authority labels

- **Tier 1 — vendor spec.** Facts the vendor publishes, such as the `retry-after-ms`
  acceptance signal, documented cache-key thresholds, and published rates.
- **Tier 2 — this project's inference/operating policy.** Choices this project makes,
  such as the seed pass-rate / `$/resolved` priors, escalation thresholds, and the
  "ensemble only above
  value X" rule.

## Placeholder models and pricing (projection track)

- **Projection track (experiments 01–08):** the model names (`mini-fast`,
  `swift-coder`, `balanced-pro`, `deep-reasoner`, `premium-max`) are all generic
  placeholders, not specific products.
- The rates in `samples/pricing/illustrative.yaml` are **dummy values** and do not
  match any published pricing. For measured numbers, copy the file to
  `your-tenant.yaml` (gitignored) and enter your real rates.
- **Measured track (experiments 09 · 10 · 11 · 12):** uses real Azure deployment
  names and your tenant's real rates (gitignored), not placeholders. Public
  artifacts include only aggregates and hashes. Endpoint and tenant identifiers are
  masked.

## Billing basis

The current router chooses one execution from pre-computed offline signals. Looking
up that signal is not a model call, so the ledger uses a
`selected-execution-only` billing basis. A future live fan-out layer must record the
cost of every panel and judge call separately. → [audit ledger](manual/ledger.md)

## What this is / is not

**This is** an offline-first, deployable router. It checks model-selection results,
limits spending, records each decision, and can prove the result with a live run.

**What it is not:**

- Not an official Foundry guide.
- Not a measured SLA/throughput model.
- Not a promise of any specific savings figure.

Savings depend entirely on your workload mix and rates. That is why the proof step
runs **in your tenant**.

## Security and reproducibility discipline

- The repo holds no real keys, tokens, connection strings, or live endpoints (a
  verification gate scans for them).
- `.env.sample` carries only valueless placeholder names.
- The projection track (experiments 01–08) reproduces offline and deterministically.
  The measured track (experiments 09 · 10 · 11 · 12) makes real Azure Foundry calls,
  so it runs in your tenant.
