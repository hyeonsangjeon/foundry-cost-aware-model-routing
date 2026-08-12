# Core concepts

## The problem

Many development tools can call several models but still **spend like a single
model**: they send planning, code generation, test generation, and validation to the
same premium model. The front end may be a coding agent, but the back end still pays
for API calls. That wastes money for two reasons.

1. **No single model is best at everything.** Different models do well on different
   task types, and cost-per-resolved (`$/resolved`) can differ by orders of magnitude.
2. **Most tasks don't need the top model.** A cheaper candidate can solve many of
   them on the first try.

## The thesis

Choose a model for each task instead of using one global default.

- Start with the **cheapest candidate**.
- Check the result. Accept it **only when the verifiable self-signals are clean**
  (applied, compiled, self-tests pass, lint/types pass), never on a hunch.
- If it fails those checks, **escalate** to the next candidate or a small
  **execution-graded ensemble**.
- Before calling several models, let the **cost governor** decide whether that extra
  spend is justified for the task.

Here **pass rate** means the share of tasks that were solved. The offline CLI and
experiment contract call this field `coverage`. Measured results also report
**grading coverage**, the share of cells that produced an answer that could be
graded; it is a different metric ([Glossary](glossary.md)). The goal is not
"the cheapest bill possible"; it is **the same pass rate at far lower cost, with an
audit trail on every decision**.

!!! quote "An old field concern this project answers"
    "A multi-model approach is only worth it when the use case justifies the extra
    tokens and latency."
    — the **cost governor** turns that concern into a rule checked before spending.

!!! info "The built-in Model Router already does this well — this repo is the layer on top"
    Azure AI Foundry's **built-in Model Router** already handles **model selection**.
    It reads the prompt and predicts which model to call. One deployment can route
    **cross-provider with no separate deployment**: OpenAI (the GPT-4/5 family), xAI
    Grok, DeepSeek, Meta Llama, and gpt-oss. Only Anthropic Claude needs a direct
    deployment ([experiment 07](../lab-notebook/07-model-router.md)).

    The built-in already covers "we route across several vendors' models". This repo
    starts with the result the built-in router selected. It does not **replace** the
    router; it **complements** it. The next steps are separate:
    ① **verify** the result with execution signals and accept it only when clean ·
    ② **escalate** after a failure · ③ use a **cost governor** to decide whether
    calling an ensemble is worth the extra spend · ④ write every decision to an
    **auditable ledger** that is hash-chained and cost-replayable. All four are
    **implemented** here. **APIM governance** for quota, routing, and observability at
    the gateway is the next direction to extend.

    The built-in Model Router also remains a **first-class candidate arm
    (`single_call`)**. This project uses the product rather than replacing it.

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
A lightweight classifier puts each incoming task into a class. Tasks such as
"generate a small function" and "patch a repository" can need different models and
different spending limits. The first version can use rules such as keywords,
metadata, and diff size; a small model can replace those rules later.

### 2 · Policy
Each class has an ordered list of candidate models. Each candidate has two starting
estimates: **pass-rate**, how often it solves that class, and **`$/resolved`**, its
total cost per resolved task. Public and field benchmarks provide the initial
values. Your own routing telemetry then updates them. They are operating policy, not
fixed truth.

The seed policy lives in [`src/policy/seed_policy.yaml`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/src/policy/seed_policy.yaml),
and the contract (every class present, `prior_usd_resolved` sorted non-decreasing,
and so on) is enforced by `PolicyTable.validate`.

### 3 · Select
The governor chooses one of two ways to run the task:

- **Cost-aware single path** — try candidates from cheapest upward. Accept the first
  result whose verifiable signals are clean; move up only after a failure. Most of
  the savings come from this path.
- **Execution-graded ensemble** — run several candidates, check them with execution
  signals, and use an LLM judge to break ties. It can raise the pass rate but also
  costs more, so the governor uses it only for tasks marked as high value.

### 4 · Govern
Before spending, the cost governor sets how much work the task may use: reasoning
effort, PAYG vs provisioned throughput, handling of the `429 retry-after-ms`
acceptance signal, and `prompt_cache_key` bucketing. The router consumes this layer
as a **dependency** from the companion toolkit instead of reimplementing its math.

## Why "the cheapest bill" isn't the answer

The flagship experiment runs 100 synthetic tasks through the single-call arms and
cost-aware routing.

| arm | Selection | Pass rate | Cost |
| --- | --- | --- | --- |
| cost | cheapest candidate per class | **22%** | $0.19 |
| balanced | middle candidate per class | 38% | $1.32 |
| quality (naive) | most expensive candidate per class | 100% | $2.23 |
| **cost-aware routing** | cheapest passing model first | **100%** | **$1.66** |

The cheapest arm solves only 22% of the tasks. The premium arm solves 100% but costs
the most. Routing starts with a cheaper model and moves up after a failed check. It
also **holds the pass rate at 100%** while spending 25.5% less than naive
([offline experiment results](projection-results.md) is canonical).

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

The offline before/after is a **projection over synthetic data**, not a measured
saving. Only a live eval in your tenant can produce **measured** savings for your
workload.

For the boundaries in full, see the [Honesty Charter](../honesty.md).
