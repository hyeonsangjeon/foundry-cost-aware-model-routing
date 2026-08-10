# Core concepts

## The problem

Most dev-centric environments live in a multi-model world yet **spend like a single
model**. The entry point may be a coding agent, but the back end runs on APIs — and
**a premium model gets applied uniformly to every workload**: planning, code
generation, test generation, validation. Two facts make that wasteful.

1. **No single model is best at everything.** Strengths split by task type, and
   cost-per-resolved (`$/resolved`) differs between models by orders of magnitude.
2. **Most tasks don't need the top model.** A good share of them are solved on the
   first try by a cheap candidate.

## The thesis

Treat model selection as a **per-task routing decision**, not a global default.

- Send each task to the **cheapest candidate** first.
- Accept it **only when the verifiable self-signals are clean** (applied, compiled,
  self-tests pass, lint/types pass) — never accept on a hunch.
- **Escalate** to the next candidate, or to a small **execution-graded ensemble**,
  only when the cheap path fails its checks.
- Before spending, a **cost governor** judges whether the task is worth running an
  ensemble on.

Here the **pass rate** is the share of tasks that passed (were solved) all the way
through — the offline CLI and experiment contract emit this value as `coverage`, and
it is a different metric from the **grading coverage** (share of cells graded)
reported separately in measured results ([Glossary](glossary.md)). The point isn't
"the cheapest bill possible"; it is **the same pass rate at far lower cost, with an
audit trail on every decision**.

!!! quote "An old field concern this project answers"
    "A multi-model approach is only worth it when the use case justifies the extra
    tokens and latency."
    — this repo answers that judgment with **code (the governor)**, not skepticism.

!!! info "The built-in Model Router already does this well — this repo is the layer on top"
    **Model selection** is already handled well by Azure AI Foundry's **built-in
    Model Router**. A single deployment routes **cross-provider with no separate
    deployment** — not just OpenAI (the GPT-4/5 family) but xAI Grok · DeepSeek ·
    Meta Llama · gpt-oss (only Anthropic Claude needs a direct deployment). It solves
    the problem of picking a suitable model **by prediction** from the prompt — and it
    does it well ([experiment 07](../lab-notebook/07-model-router.md)).

    So *"we route across several vendors' models"* is not a differentiator to
    replace but **table-stakes**. This repo does not **replace** it; it
    **complements** it — *selection* and *verification/governance* are **different
    layers**. The built-in router **picks** which model to call, and this repo takes
    that **selected result** and — ① **verifies** it with execution signals
    (accepting only when clean) · ② **escalates** on failure · ③ gates whether an
    ensemble is worth running with a **cost governor** · ④ seals every decision into
    an **auditable ledger** (hash-chained, cost-replayable). All four are
    **implemented** in this repo, and the **APIM governance** that lifts quota,
    routing, and observability up to the gateway is the next direction to extend.

    In fact this repo carries the built-in Model Router as a **first-class candidate
    arm (`single_call`)** at the frontier — an asset that *uses the product rather
    than replacing it*.

    > **In one line:** model selection is already handled well by the built-in Model
    > Router. This asset is the layer for the **next problem** — **verifying** the
    > selected result, **escalating** failures, **governing** multi-model spend, and
    > making decisions **auditable**.

## Four decision layers

```text
1. CLASSIFY  task → {plan, generate, test, validate, repo_patch}
2. POLICY    task class → ranked candidate models (pass-rate, $/resolved priors)
3. SELECT    cost-aware single path (cheapest-clean-first); on failure, execution-graded ensemble + judge tiebreak
4. GOVERN    reasoning-effort dial · PTU vs PAYG · 429 retry-after · prompt-cache bucketing (gate before spend)
```

### 1 · Classify
A lightweight classifier maps each incoming task to a class. The class is what makes
routing possible — "generate a small function" and "patch a repository" have
different best models and different cost ceilings. Start rule-based (keywords,
metadata, diff size) and upgrade to a small model later.

### 2 · Policy
Each class maps to an ordered list of candidate models, and each candidate carries
two priors — **pass-rate** (how often it solves that class) and **`$/resolved`**
(total cost per resolved task). These values are **seeded** from public/field
benchmarks and then **updated from your own routing telemetry**. Operating policy,
not fixed truth.

The seed policy lives in [`src/policy/seed_policy.yaml`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/src/policy/seed_policy.yaml),
and the contract (every class present, `prior_usd_resolved` sorted non-decreasing,
and so on) is enforced by `PolicyTable.validate`.

### 3 · Select
The governor picks between two strategies:

- **Cost-aware single path** — consult candidates cheapest-first, accept the first
  whose verifiable signals are clean, and escalate only on failure. Most of the
  savings come from this path.
- **Execution-graded ensemble** — run several candidates, grade them on execution
  signals, and break ties with an LLM judge. Higher pass rate but higher cost, so it
  is used only on tasks the governor has flagged as high value.

### 4 · Govern
Before spending, the cost governor dials the size of the decision — reasoning effort,
PAYG vs provisioned throughput, handling of the `429 retry-after-ms` acceptance
signal, `prompt_cache_key` bucketing. This layer is consumed as a **dependency** from
the companion toolkit; the router does not reimplement its math.

## Why "the cheapest bill" isn't the answer

Put the single-call arms side by side in the flagship experiment (100 synthetic
tasks) and it becomes clear.

| arm | Selection | Pass rate | Cost |
| --- | --- | --- | --- |
| cost | cheapest candidate per class | **22%** | $0.19 |
| balanced | middle candidate per class | 38% | $1.32 |
| quality (naive) | most expensive candidate per class | 100% | $2.23 |
| **cost-aware routing** | cheapest passing model first | **100%** | **$1.66** |

The cheapest arm is cheap but its pass rate collapses to 22%. The premium arm hits
100% but costs the most. Routing **holds the pass rate at 100%** while spending 25.5%
less than naive ([offline experiment results](projection-results.md) is canonical).

!!! note "This table is an illustrative equivalent"
    The cost/balanced/quality arms are transparent **placeholder baselines**, not a
    claim about any managed router's internals. Every figure is `labels.measured =
    false` — an offline projection made with no real calls.

## Claim-authority labels

Every numeric and behavioral claim in this repo keeps an authority label.

- **Tier 1 — vendor spec.** e.g. the `retry-after-ms` acceptance signal, documented
  cache-key thresholds, published rates.
- **Tier 2 — this project's inference/operating policy.** e.g. the seed
  pass-rate / `$/resolved` priors, escalation thresholds, the "ensemble only above
  value X" rule.

The modeling vs measurement boundary is stated explicitly. The offline before/after
is a **projection over synthetic data**; only a live eval in your tenant yields
**measured** savings.

For the boundaries in full, see the [Honesty Charter](../honesty.md).
