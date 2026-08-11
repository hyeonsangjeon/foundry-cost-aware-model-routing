# Experiment configuration (YAML)

A **named experiment** is a small YAML file that pins the workload, the offline
signals (fixture or synthetic), the pricing, and the policy, and adds an `expect`
**reproducibility contract** on top. Run one and it re-derives the naive-vs-routing
before/after and **fails loudly** if the offline projection drops below the
contracted floor.

The repository's "install it and it just runs" promise is checked by the expect
block: the command exits non-zero when the projection falls outside the declared
limits.

The files live in the `experiments/` directory.

!!! tip "Want to see it visually first — the Experiment Atlas"
    To see at a glance **which model** each experiment uses to do **what**, and in
    **which way** (sequential escalation · fan-out · single call), as animated SVGs,
    see the **[Experiment Atlas](experiment-atlas.md)**. It even includes a
    walkthrough of the real Azure Model Router setup (keyless Entra).

## Minimal example

```yaml title="experiments/hero.yaml"
name: hero
title: "Same coverage, lower cost — the 30-second hero run"
summary: >-
  Route 100 synthetic-workload items 'cheapest passing model first, escalate
  only on failure' and compare against the naive approach of sending every task
  to a premium model.

dataset:
  workload: samples/telemetry/mixed-coding-workload.sample.jsonl
  signals: null        # null + synth:true → deterministic offline signals
  synth: true

policy: null           # null → bundled seed policy
pricing: null          # null → bundled illustrative pricing (measured=false)

spotlight: auto        # auto | <task_id> | none

expect:
  min_coverage: 1.0    # routing must keep coverage
  min_delta_pct: 0.20  # …while cutting the naive bill by at least 20%
  min_tasks: 100
```

!!! tip "The fan-out dial — `budget:` (optional)"
    An experiment can tune the router's fan-out threshold. Raise
    `compare_min_value` and any task worth less than that goes down a **single path
    (ordered)**, reducing the cost of extra candidate calls —
    [experiment 06](../lab-notebook/06-fanout-dial.md) uses this dial.

    ```yaml
    budget:
      compare_min_value: 1.1      # above every task's value (max 1.0) → no fan-out at all
      min_compare_candidates: 2   # need at least 2 candidates to go to compare
    ```

!!! tip "The measurement bridge — Azure AI Foundry Model Router (optional)"
    The `single_call` arm is an offline proxy for a single-call routing layer. To use
    the **decisions** of a real Foundry
    Model Router, give the dependency-free gate adapter
    `router.foundry_router.FoundryModelRouter` the environment variables below plus
    an injected `client` callable (with no configuration the adapter is inactive and
    the offline proxy stands in). Even with live decisions plugged in, cost and
    coverage remain offline projections (`measured = false`) — only the model
    **selection** is live. See [experiment 07](../lab-notebook/07-model-router.md).

    | Environment variable | Meaning |
    | --- | --- |
    | `AZURE_AI_FOUNDRY_ENDPOINT` | Foundry endpoint (or `AZURE_OPENAI_ENDPOINT`) |
    | `AZURE_AI_FOUNDRY_MODEL_ROUTER` | Model Router deployment name (or `AZURE_MODEL_ROUTER_DEPLOYMENT`) |
    | `AZURE_AI_FOUNDRY_API_KEY` | API key (or `AZURE_OPENAI_API_KEY`) |

## Field reference

| Field | Meaning |
| --- | --- |
| `name` | Experiment name (defaults to the file stem) |
| `title` / `summary` | Human-readable title/description |
| `dataset.workload` | Workload JSONL path (empty → bundled sample) |
| `dataset.signals` | Offline signals JSON path, or `null` to synthesize |
| `dataset.synth` | If `true`, synthesize the signals deterministically |
| `policy` | Policy YAML path (empty → bundled seed) |
| `pricing` | Pricing YAML path (empty → bundled illustrative pricing) |
| `budget.compare_min_value` | (optional) Fan-out threshold — compare (fan out) only when a task's value is at or above this. Higher → fewer extra candidate calls (see `adaptive.yaml`) |
| `budget.min_compare_candidates` | (optional) Minimum candidates required to go to compare |
| `spotlight` | `auto`, a specific `task_id`, or `none` |
| `expect.min_coverage` | Must hold at or above this coverage |
| `expect.min_delta_pct` | Must lower the naive bill by at least this fraction |
| `expect.max_delta_pct` | (optional) **Ceiling** — savings must not exceed this fraction (blocks implausibly large savings; see `limits.yaml`) |
| `expect.max_tax_ratio` | (optional) **Extra-call ratio ceiling** — the fan-out cost/winner ratio must not exceed this (see `adaptive.yaml`) |
| `expect.min_escalation_gain` | (optional) **Escalation-gain floor** — mix coverage − `single_call` arm coverage must be at or above this (see `single-call.yaml`) |
| `expect.min_tasks` | Must cover at least this many tasks |

Paths are written relative to the repository root, or as absolute paths.

## spotlight — highlight a representative task

`spotlight` picks the one task where cost-aware routing beats the naive premium arm
most visibly.

- `auto` — among the accepted tasks, the one with the largest
  **naive/routing cost ratio**
- `<task_id>` — pin a specific task explicitly
- `none` — disable the spotlight

## What the reproducibility contract does

After the replay, `run_experiment` checks:

- `coverage ≥ min_coverage`
- `delta_pct ≥ min_delta_pct`
- `delta_pct ≤ max_delta_pct` (only when set — a ceiling that blocks an implausibly large saving)
- `tax_ratio ≤ max_tax_ratio` (only when set — the extra-call ratio ceiling)
- `escalation_gain ≥ min_escalation_gain` (only when set — mix must beat the single-call `single_call` on coverage by at least this much)
- `tasks ≥ min_tasks`

If any one fails, `cost-router hero`/`experiment run` exits with a **non-zero code**.
This prevents an "it still runs but the savings vanished" regression from passing.

!!! tip "Make your own experiment"
    ```bash
    cp experiments/hero.yaml experiments/my-workload.yaml
    # swap the workload/policy/pricing for your own
    cost-router experiment run my-workload
    ```
    If you want measured numbers, copy `samples/pricing/illustrative.yaml` into
    `your-tenant.yaml` (gitignored), put in your real rates, and point `pricing:` at
    it.
