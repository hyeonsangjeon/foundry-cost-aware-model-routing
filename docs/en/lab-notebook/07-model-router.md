# Experiment 07 · One pick vs observe-then-escalate

!!! quote "⭐ The repo's primary comparison — why this asset exists next to the built-in router"
    Azure AI Foundry's **built-in Model Router** already does the **'selection'** well — picking a model per prompt (one deployment, cross-provider). This experiment captures, on one screen, the **reason the layer on top of it exists** — picking once up front and being done vs observe-then-escalate, *at comparable cost*. *Selection is the built-in router's job; verification, governance, and audit are this repo's.* And the **measured** answer to *"what if you plug the real router straight into this arm?"* is [experiment 09](09-live-routing-proof.md) — the repo's first live Model Router run and its first `measured=true` result, where one deployment called over keyless Entra routed 5 curated prompts to `gpt-5.4`×3 and `grok-4-1-fast-reasoning`×2.

!!! info "Field names — the CLI prints this pass rate as `coverage`"
    The **pass rate** on this page is the share of tasks that pass (are resolved). The offline CLI and the experiment contract emit it under the field name `coverage`, so the two words name one quantity here. It differs from **grading coverage** (the share of planned cells that were graded), which the measured experiments 11, 12 and 13 report separately → [glossary](../manual/glossary.md).

!!! abstract "One-line summary"
    An **arm** is one comparison strategy evaluated against the same workload under the
    same measurement plan, and this experiment compares two. **`single-call`** picks one
    model per prompt and stops. With **no escalation**, it reaches a **52%** pass rate on
    100 synthetic tasks. `cost-aware mix` checks the result and moves to another model
    after failure, reaching **100%** at comparable cost (**$1.66 vs $1.59**). The
    `min_escalation_gain` contract pins the **+48 percentage point (pp)** gap. All numbers are offline
    projections over synthetic data and `measured = false`, not a score for any
    commercial product.

<figure markdown="span">
  ![Animation comparing the pass rate of a single-call lane and an observe-then-escalate lane side by side](/foundry-cost-aware-model-routing/assets/gif/model-router.gif)
  <figcaption>One pick vs observe-then-escalate — a lane that fixes one tier up front against a lane that observes cheap failures and raises only when needed, contrasted on pass rate.</figcaption>
</figure>

The real Foundry **Model Router**'s selection skill is a **measured** quantity, so we
left open a gated integration point behind credentials — the live measurement adapter —
that plugs that decision straight into this arm.

!!! tip "Operational view — Model Router is 'one deploy and it's handled'"
    In real operation, Model Router is done with **one deployment**. The supported models (OpenAI GPT-4/5 families, xAI Grok, DeepSeek, Meta Llama, gpt-oss) need **no separate deploy** — the router picks one per prompt; the only exception is Anthropic Claude, which needs a direct deployment. So the built-in router is already **cross-provider**.     That means *"routing across several vendors' models"* is already handled. This
    repo adds result checks, escalation after failure, accounting for all candidate
    calls, spending limits, and the audit ledger
    ([core concepts](../manual/concept.md)). It does not **replace** the router; it
    uses it as a **first-class candidate arm**. The experiment below measures the
    pass-rate gap between picking once (single-call routing) and observing and raising
    (observe-then-escalate routing).

## What this experiment is

- **Situation (when):** it started from a request to "ensemble with the Azure AI
  Foundry Model Router," but Model Router is **a single-call router, not an
  ensemble**. It picks one model per prompt, so it belongs in the same comparison as
  this repo's `route_task`, as a **first-class arm**.
- **Task (what):** add `single_call` as the fifth strategy. It picks one model from
  the class ladder by task value and cannot recover after that choice. Score its cost
  and pass rate on the same offline signals, then pin "single-call loses the passes
  escalation earns" with `min_escalation_gain`.
- **Experiment (what it tests):** on 100 synthetic tasks, (1) `single_call` reaches a
  **52% pass rate**, (2) observe-then-escalate routing (`cost-aware mix`) reaches
  **100%** at **comparable cost**, and (3) the **+48 percentage point** escalation gain
  clears the 30 percentage point floor.

The result is direct: picking once and stopping is not the same as checking the
result and trying another model after failure.
Experiments 01 · 02 cover savings, 03 covers a lost pass rate, 04 covers no saving,
05 covers all-candidate call cost, and 06 covers the fan-out threshold.

## Three routing shapes (Model Router ≠ ensemble)

| | What it does | Pass rate | This repo's counterpart |
| --- | --- | --- | --- |
| **Model Router** (single-call) | picks **one model** up front per prompt | no recovery once the first pick fails | `route_task`'s **ordered / single route** |
| **Ensemble / fan-out** (compare) | runs several models and picks a winner | high, with [extra call cost](05-ensemble-fanout.md) | `route_task`'s **compare route** |
| **observe-then-escalate routing** (this repo) | cheapest first, **escalate on failure** | 100% at low cost | `route_task` in full |

Azure AI Foundry Model Router is the productized form of single-call routing — it looks at a prompt and picks a model once. So this experiment's `single_call` arm transparently mimics that **shape**: a `floor(value × N)` rule that picks an index into the class ladder by task value (difficulty) (easy → the cheapest `mini-fast`, hard → `premium-max`).

!!! warning "This arm is a placeholder (`measured = false`, `equivalent = illustrative`)"
    The `single_call` arm is a transparent proxy that shows the **shape** of a single-call router, not Azure's internal selection logic. On 100 synthetic tasks the picks spread evenly across the five models (`mini-fast` 31 · `swift-coder` 23 · `balanced-pro` 20 · `deep-reasoner` 19 · `premium-max` 7) — a fair difficulty router that uses the whole ladder, not a straw man. A real router's **selection skill** is a measured quantity, plugged in via [the measurement adapter](#measurement-adapter) below.

## Result — one pick versus escalation

The five strategies on the 100-task synthetic workload:

| Strategy | Cost | Pass rate | Position |
| --- | --- | --- | --- |
| all-mini | $0.19 | 22% | cheap, low pass rate |
| **single_call** (single-call) | **$1.59** | **52%** | picks once, no recovery |
| observe-then-escalate routing | $1.66 | **100%** | checks and escalates after failure |
| all-premium | $2.23 | 100% | same pass rate, maximum cost |
| all-ensemble | $4.23 | 100% | calls every candidate ([extra fan-out cost](05-ensemble-fanout.md)) |

The key is the contrast between `single_call` and `mix`:

- **Cost is nearly identical** — single-call $1.59 vs observe-then-escalate $1.66 (**+4.5%**).
- **The pass rate differs two-fold** — 52% vs 100%. **Escalation gain = +48 percentage points.**

That is, for almost the same money, observing and raising doubles the share of tasks
solved.
Single-call cannot recover when its first model fails.

> Canonical: the single-call pass-rate gap (+48 pp) is collected in [offline experiment results](../manual/projection-results.md).

## Why one model choice leaves failed tasks unresolved

On deterministic offline signals, when the router picks one model **up front**, a task that model fails has **no recovery path** — that task counts as unsolved. However good the difficulty estimate, a task whose first pick misses (48% here) is a straight loss.

`cost-aware mix` **tries the cheapest candidate first** and **escalates** after a
failed check. At nearly the same cost, those additional attempts raise the pass rate to
100%.

## Experiment 07 — pinning the escalation gain with a contract

```bash
cost-router experiment run single-call    # (the old name model-router still works as an alias)
```

```text
before / after  (offline projection over synthetic data; labels.measured=false)
  BEFORE  naive: premium model on every task   $2.23
  AFTER   cost-aware routing                   $1.66
  SAVED   $0.57  (25.5% lower)  at 100.0% coverage

spotlight  t-0078 · validate · clean-first
  routed  mini-fast      $0.0003
  naive   deep-reasoner  $0.0071   (24.1x more)

reproducibility  PASS
  PASS  coverage: 100.0% ≥ 100.0%
  PASS  savings: 25.5% ≥ 20.0%
  PASS  tasks: 100 ≥ 100
  PASS  escalation_gain: observe-then-escalate 100.0% − single-call 52.0% = +48.0 percentage points ≥ 30.0 percentage points
```

The new contract check `escalation_gain` pins *"observe-then-escalate routing (`mix`) must buy at least 30 percentage points more pass rate than single-call routing (`single_call`)."* If someone removes escalation from routing (so `mix` collapses like single-call) or inflates the arm, the gain falls below 30 percentage points and **CI fails**.

!!! note "New capability — the contract's third axis"
    Experiment 04 introduced `max_delta_pct` to cap reported savings; experiment 06
    uses `max_tax_ratio` to cap extra candidate-call cost. Experiment 07 adds
    `min_escalation_gain` (**a floor on escalation gain**) so CI checks that
    "observing really buys passes." For the fields, see
    [experiment config (YAML)](../manual/experiments.md).

## <a name="measurement-adapter"></a>The live measurement adapter — gated, behind real Azure credentials

The `single_call` arm's pick is a placeholder proxy. To plug in the real Azure AI Foundry Model Router's **decision**, use the dependency-free gated adapter `router.foundry_router.FoundryModelRouter`:

- **Gated by environment variables** — `AZURE_AI_FOUNDRY_ENDPOINT`, `AZURE_AI_FOUNDRY_MODEL_ROUTER` (the deployment name), `AZURE_AI_FOUNDRY_API_KEY`. Without them the adapter is **inactive** and the offline proxy stands in.
- **It opens no network itself** — the HTTP call is an **injected `client` callable** (the same pattern as `metrics`' `FoundryMetricsEmitter`). This module imports no SDK, so it is test/CI-safe and fully deterministic.
- **Honesty boundary (important):** plugging in a live **decision** does not make the numbers measured — cost and pass rate are still an offline projection over synthetic signals (`measured = false`), and only the model **selection** may be live. `labels.decisions` records the provenance (`live` / `recorded` / `illustrative`) so this distinction never disappears. Truly measured spend needs real token usage and real evaluation, which is out of scope for this offline repo.

A recorded snapshot of decisions can be scored in the same comparison
(`samples/responses/model-router-choices.sample.json`):

```python
from router.foundry_router import load_recorded_choices, summary_from_choices
choices = load_recorded_choices("samples/responses/model-router-choices.sample.json")
arm = summary_from_choices(workload, signals, policy, pricing, choices)
# a recorded run leaning toward strong models: 100% coverage, $0.13 — about 2.3× the escalation mix ($0.06)
```

This recorded run leans toward strong models and reaches a 100% pass rate.
Observe-then-escalate routing reaches the same pass rate **2.3× cheaper**. The model
selections here were captured from a live deployment; the cost and pass rate scored
against them are still an offline projection.

### Integrating it with real Azure — `azure_router_choice_client` + `foundry router`

The **real implementation** of the `client` callable to inject is
`azure_router_choice_client`. It is a selection function that returns only the model the
deployment actually chose, wrapping the keyless SDK client (`AzureModelRouterClient`) as
a `(deployment, task) -> model` callable (normalized: `gpt-5.4-2026-03-05` →
`gpt-5.4`):

```python
from router.foundry_live import AzureModelRouterClient, FoundryConfig
from router.foundry_router import FoundryModelRouter, azure_router_choice_client

client = AzureModelRouterClient(config=FoundryConfig.from_env())
router = FoundryModelRouter.from_env(client=azure_router_choice_client(client))
model = router.choose({"task_id": "t-0003", "prompt": "..."})  # live single-call decision
```

One CLI line runs the exp-07 comparison (offline proxy pick vs the router's real
choice). By default it replays the recorded snapshot offline (deterministic, no
sending); `--live` asks the real deployment and shows **genuine per-task selection**;
`--capture` writes those choices to a file:

```bash
cost-router foundry router                        # offline: proxy vs recorded choices
cost-router foundry router --live                 # the model the real deployment picked (measured decision)
cost-router foundry router --live --capture picks.json   # capture the real choices as a snapshot
```

```text
Azure Model Router — single-call choice  (recorded snapshot (…/model-router-choices.sample.json))
  tasks                 : 5
  offline proxy pick    : $0.09   coverage 60.0%  (difficulty-tiered, illustrative)
  router choices        : $0.13   coverage 100.0%  (decisions: recorded)
  Δ cost vs proxy       : +$0.04
  chosen models         : balanced-pro×2, deep-reasoner×2, premium-max×1
  labels                : measured=no  decisions=recorded
```

`capture_recorded_choices` (the inverse of `load_recorded_choices`) honestly stamps each item `decisions=recorded` / `measured=false`, and the top-level `captured_from=live` records that "the source is real." When `--live` returns real 5-series names (`gpt-5.4` · `grok-4-1-fast-reasoning`), the offline candidate ladder (placeholder names) has no matching row, so scoring **falls back** to the proxy — the selection is live but cost and pass rate are still an offline projection (the honesty boundary holds).

## See it in the web app — compare the five strategies

The dashboard plots `single_call` with `all-mini`, `all-premium`, `all-ensemble`, and
`cost-aware mix`. The `single_call` point has a lower pass rate because it stops after
one choice; observe-then-escalate routing reaches 100% by escalating after failure. The
chart's own axis label reads `coverage`, which is that field name for the pass rate.

[See it in the live demo →](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1)

## Reading this number honestly

This experiment shows that single-call routing solves fewer tasks than
observe-then-escalate routing. But two honest caveats:

1. **The `single_call` arm is a placeholder.** The real Foundry Model Router's
   selection may be better than this proxy. That improvement is a **measured**
   quantity plugged in through [the measurement adapter](#measurement-adapter).
   [Experiment 09](09-live-routing-proof.md) connects the measurement adapter to a real deployment.
   This experiment does not claim that skill on the router's behalf.
2. **Cost and pass rate are offline projections.** Plugging in a live decision keeps them `measured = false`. A truly measured verdict needs real tokens and evaluation.

Before choosing a single-call router, compare what it leaves unsolved — here 48% of tasks, a 48 percentage-point gap against observe-then-escalate routing — with the
additional cost of escalation.

## When to use this experiment

- When deciding whether to adopt a managed **single-call router** (Azure AI Foundry
  Model Router or similar) and checking how many tasks "picking once" leaves unresolved.
- To set a **floor on escalation gain** (`min_escalation_gain`) in the reproducibility criteria so CI blocks anyone quietly removing observe-then-escalate from routing.
- To plug a real router's decisions in via **the measurement adapter** instead of using
  the placeholder proxy.

## Reproduce this experiment

```bash
pip install -e .
cost-router experiment run single-call            # human-readable summary (incl. the escalation-gain contract)
cost-router experiment run single-call --json     # contract checks + strategy arms
cost-router replay --synth                         # see the frontier's five strategies for yourself
```
