# One problem, four ways (5-minute wow)

Where the dashboard's other panels compare the **whole workload** in aggregate, this arena
answers the question a new user asks first: **"For this one problem, how much does each
approach spend, how slow is it, and does it even get the answer right?"** Pick a task and
watch four columns fill in — a "press it and you see it" screen in the spirit of HuggingFace
Spaces.

!!! success "See it instantly, no install"
    The arena panel is part of the live dashboard.

    [:material-open-in-new: Live demo](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/){ .md-button target=_blank }

## The four ways

The same single task is scored across four approaches. It reuses the **exact same offline
machinery** as the aggregate panels, so the numbers agree by construction.

| Approach | What it does | Cost billed |
| --- | --- | --- |
| **Cheapest model** | Calls only the class's single cheapest candidate | that one call |
| **Premium model** | Calls only the most expensive candidate (the naive ceiling) | that one call |
| **Ensemble (fan-out)** | Fans out to **all** candidates and takes the best | **the sum of all candidates** (the fan-out tax) |
| **Cost-aware router** | Starts cheap, escalates upward on failure | **the winner only** |

!!! info "The four ways = a contrast of the axes layered on top of the built-in router"
    The Azure AI Foundry **built-in Model Router** already does the **per-prompt "selection"**
    well (one deployment, cross-provider). This four-way comparison shows the **layer above**
    it — **ensemble (fan-out)** represents the [ensemble-tax
    distinction](../lab-notebook/05-ensemble-fanout.md) (winner only vs. sum of all), and the
    **cost-aware router** represents *observe-then-escalate* (validation-based acceptance + a
    cost governor). In short, it narrows to a single task the contrast between the built-in
    router's single selection and the **validation, escalation, and governance** this repository
    adds — and the aggregate view of that is [Experiment 07 · The routing layer](../lab-notebook/07-model-router.md) ⭐.

## The three axes

- **Cost** — applies example prices to the task's token count. The router bills the **winner
  only**; the ensemble bills **all**.
- **Accuracy** — the router's `is_clean` verdict ("pass" when every offline check passes). It's
  a synthetic-signal projection, not a graded live answer.
- **Latency** — an **illustrative projection**, not a measurement. The bundled telemetry has no
  timing, so a per-tier throughput model turns token counts into milliseconds just to give the
  third axis a shape. The ensemble is a parallel fan-out, so it's the **slowest single one**
  (max); the router escalates sequentially, so it's the **sum of the calls it attempted** (sum).

## An honest trade-off

On the default task `t-0003` (repo_patch), the result is:

| Approach | Cost | Latency* | Accuracy |
| --- | --- | --- | --- |
| Cheapest model | `$0.0067` | fast | ✗ fail |
| Premium model | `$0.08` | medium | ✓ pass |
| Ensemble (fan-out) | `$0.18` | medium | ✓ pass |
| **Cost-aware router** | **`$0.03`** | **slowest** | ✓ pass |

The router is **the cheapest and gets it right** (about 2.5× cheaper than premium — and
premium and ensemble are equally right), but because of sequential escalation it has the
**slowest latency**. Premium wins on latency. **There is no free lunch** — here you pay latency
for the cost you save. Accuracy is binary, so the three approaches that pass
(premium, ensemble, router) are **equally** correct and only the cheapest model fails. Pick an
easy task (`t-0001`) and the cheapest model wins all three axes, and the router picks exactly
that — routing earns its value on the hard tasks.

`*` Latency is an illustrative projection (`measured = false`). It is not real wall-clock; real
timing comes from the [live measured bridge](foundry-live.md).

## Input data — a problem you can read

Every task carries a **human-readable problem statement** — a title, the prompt it will
actually send, and the pass criterion (`expect`). The CLI shows it as a `problem` block above
the table; the web app shows it as a task card. That makes it immediately clear "what problem
this is" and that the four ways solve **the same concrete problem**.

!!! warning "Authored (synthetic) prompts — not a public benchmark"
    These problem statements are **synthetic examples the repository authored itself**
    (`problem_basis = authored-synthetic`, `samples/prompts/curated-arena.sample.json`). It
    **did not bolt on a public benchmark** like HumanEval or MBPP — attaching synthetic
    pass/fail signals to a named benchmark would dishonestly imply a measured evaluation. Real
    public data plus real grading is possible only in the [live measured
    bridge](foundry-live.md). The prompts are **display-only** — they don't affect
    classification or cost, and the numbers above are identical with or without them.

## Viewing it from the CLI

```bash
cost-router compare                    # default task (t-0003)
cost-router compare --task t-0001      # a specific task
cost-router compare --json             # that task's arena as JSON
```

Example output:

```text
one problem, four ways   (measured = false)
task  t-0003   class=repo_patch   difficulty=medium
problem   Patch parse_duration to accept combined units
          The repo's parse_duration(text: str) -> int helper returns None for
          combined values like "1h30m" or "2m30s". Patch it to sum consecutive
          <number><unit> segments (h/m/s) into total seconds, reject empty or
          malformed input, and keep the existing single-unit tests green.
          expect: "1h30m" -> 5400, "45s" -> 45, "" and "10x" are rejected, and the
                  existing single-unit tests still pass.

approach            model(s)                            cost    latency*  result
------------------- ---------------------------- ----------- -----------  ------
Cheapest model      swift-coder                  $  0.006680     15485ms  ✗ fail
Premium model       premium-max                  $  0.081981     26860ms  ✓ pass @
Ensemble (fan-out)  4 models (swift-coder +3)    $  0.179844     26860ms  ✓ pass
Cost-aware router   swift-coder → balanced-pro   $  0.032793     33556ms  ✓ pass $

winners   cost: Cost-aware router   latency: Premium model   accuracy: 3 of 4 pass
note      latency is an illustrative projection (measured = false), not wall-clock.
          $ = cheapest   @ = fastest   (accuracy is pass/fail per approach)
```

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/compare` | Task menu + arenas for all curated tasks |
| GET | `/compare?task=<id>` | Sets the default task to the given task |

The payload is small (5 curated tasks), so it returns the whole `{tasks, default, arenas}` map
at once. That keeps the static export and the live server identical, and the web app switches
tasks with no round trip.

!!! note "Every number is an offline projection"
    Cost and accuracy come from the same offline machinery as the other panels (`measured =
    false`) **by construction**; latency is a newly introduced **illustrative projection**. Model
    names are generic placeholders.

## Viewing it measured (`measured = true`)

The numbers above are all offline projections (`measured = false`). To **measure the same
curated tasks (t-0001–t-0006) against the real Azure Model Router**, run the live bridge with a
prepared, prompt-bearing workload — it's one command once you fill in credentials:

```bash
cost-router foundry live --live \
  --workload samples/telemetry/curated-arena-live.sample.jsonl \
  --pricing  samples/pricing/your-tenant.yaml --store runs.jsonl
```

Cost is computed from the actually billed token usage, becoming `measured = true`, and `--store`
leaves one line on the historical dashboard. For the full setup and honesty boundaries, see the
[live measured bridge](foundry-live.md). (Measuring accuracy too requires injecting a `grader`;
without one, coverage is labeled an offline-signal projection.)

## Experiment record

The method, numbers, and honesty labels of this prototype run feature are collected in
[Experiment 08 · Arena](../lab-notebook/08-arena.md) — why it narrows to a single task, why the
latency axis is an illustrative projection, and why the router is the slowest (sequential
escalation).
