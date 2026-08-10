# Experiment 08 · One problem, four routing strategies

!!! abstract "One-line summary"
    Where experiments 01–07 weighed the **whole workload** in aggregate, this one narrows that frontier to **a single task** — the "fills in the moment you click" prototype run screen that answers the first question a new user asks: *"for this one problem, how much does each method spend, how slow is it, and does it even get it right?"* It runs four approaches on the same task (cheapest model · premium · ensemble · cost-aware router) and fills three axes — **cost · latency · accuracy**. On the default task `t-0003` the router is the **cheapest correct answer** (1/2.5 of premium) but the **slowest** (sequential escalation) — even the hero pays a price on this experiment's **new axis, latency**. Cost and accuracy come from the **same offline machine** as the other experiments (`measured = false`); **latency is a newly introduced illustrative projection** (not measured).

## What this experiment is

- **Situation (when):** every other dashboard panel is an **aggregate** — a frontier or strategy bar that summarizes a 100-task workload into one point. Powerful, but a first-time visitor wants an immediate screen that *"runs the same one problem several ways and compares cost, performance, and accuracy by eye."* There was no HuggingFace-Spaces-style "5-minute wow."
- **Task (what):** we built an **arena** that scores four approaches on a single task and put it in both the web app and the CLI. Cost and accuracy **reuse the existing offline machine** as-is (`classify_task` · `candidates_for` · `pricing.cost_usd` · `is_clean` · `ordered_select`), matching the aggregate panels by construction, and we newly added a **third axis, latency**, as an illustrative projection.
- **Experiment (what it tests):** on the default `t-0003`, that (1) the router **wins on cost** (the cheapest correct answer), (2) **accuracy is shared by the three approaches that pass** (only the cheapest model fails), and yet (3) the router is **slowest on latency** (1.25× premium) — the hero's hidden price.

This is the **lens that narrows the whole story to one task**, following 01 · 02 (the gain), 03 · 04 (the honest limits), and 05 · 06 · 07 (the expensive shortcuts and their price). And it honestly puts one axis the earlier experiments didn't cover — **latency** — on stage.

## Aggregate frontier ↔ single-task arena

| | Experiments 01–07 (aggregate) | Experiment 08 (arena) |
| --- | --- | --- |
| Unit | 100 tasks (or 5 curated) as **one point** | **one task** across four columns |
| Axes | cost × coverage | cost × **latency** × accuracy (pass/fail) |
| Contract | the `expect` floor/ceiling in `experiments/*.yaml` | `tests/test_arena.py` pins the numbers |
| Question | "which strategy wins across the whole workload" | "what does each method produce on this one problem" |

!!! note "This is a lens, not a contract experiment"
    01–07 are **workload experiments**, each with its own `expect` contract. The arena is a different animal — a **prototype-run lens** that runs one task several ways to show it, so we didn't force an `expect` floor onto it. Instead, every number is pinned by `tests/test_arena.py` (the cost convention · latency projection · winner logic · endpoint/CLI shape), so CI fails if it drifts.

## Four approaches — same task, different strategies

| Approach | What it does | Cost billed |
| --- | --- | --- |
| **Cheapest model** | calls only the single cheapest candidate in the class | that one call |
| **Premium model** | calls only the priciest candidate (the naive ceiling) | that one call |
| **Ensemble (fan-out)** | fans out to **all** candidates and adopts the best | **the sum of all candidates** ([fan-out tax](05-ensemble-fanout.md)) |
| **Cost-aware router** | cheapest first, escalate up on failure | **the winner only** |

The billing convention is the same as elsewhere in the repo: the router matches the winner-billing in `trace.py`, and the ensemble matches the sum-all in `baseline.ensemble_all_summary` — they cannot diverge by construction.

## Input test data — a problem you can read

At first the arena showed only a task's **metadata** (class · difficulty · token counts). There was no answer to "so **what problem** is this?" So we attached **human-readable problem statements** to the 5 curated tasks — `samples/prompts/curated-arena.sample.json` holds a `title` · `prompt` · `acceptance` (pass criteria) per task, shown in both the CLI (a `problem` block) and the web app (a problem card). For example, `t-0003` is *"patch parse_duration to also handle combined units like '1h30m' — reject empty/malformed input, keep the existing single-unit tests green."*

!!! warning "These are authored (synthetic) prompts — not a public benchmark (`measured = false`)"
    These problem statements are **synthetic examples the repo authored itself** (`problem_basis = authored-synthetic`). We did **not** paste in problems from named public benchmarks like HumanEval or MBPP — doing so would dishonestly imply the repo's synthetic pass/fail signals are that benchmark's **measured evaluation results**. Real public data + real grading is possible only in the [live measured bridge](../manual/foundry-live.md) (`measured = true`, credentials · network · real cost). **Important:** the prompts are **display-only** and do not affect classification or cost — all five tasks carry an explicit `class` field, so `classify_task` never reads the prompt text, and attaching problem statements leaves the pinned numbers above **unchanged** (`tests/test_arena.py` pins this invariant).

## Result — default task `t-0003` (repo_patch, medium)

Candidate ladder: `swift-coder → balanced-pro → deep-reasoner → premium-max`.

| Approach | Model | Cost | Latency* | Accuracy |
| --- | --- | --- | --- | --- |
| Cheapest model | swift-coder | `$0.0067` | **15,485 ms** (fastest) | ✗ fail |
| Premium model | premium-max | `$0.08` | 26,860 ms | ✓ pass |
| Ensemble (fan-out) | all 4 | `$0.18` | 26,860 ms | ✓ pass |
| **Cost-aware router** | swift-coder → **balanced-pro** | **`$0.03`** | **33,556 ms** (slowest) | ✓ pass |

Winners by axis: **cost = router** · **latency = premium** · **accuracy = the three that pass (premium · ensemble · router)**.

Three honest observations:

1. **Router = the cheapest correct answer.** It delivers the same "pass" as premium **2.5× cheaper** ($0.03 vs $0.08), and than the ensemble **5.5× cheaper** ($0.03 vs $0.18). The cheapest model is cheaper still but **wrong**.
2. **The ensemble buys the answer but pays a tax.** It fans out four candidates and adopts **the best passing answer**, but bills **all** four models — about **2.2×** the single winner-bill (premium $0.08) — the [fan-out tax](05-ensemble-fanout.md) seen through one task.
3. **The router is the slowest.** This is the experiment's key new observation → below.

## The new axis, latency — why the router is slowest

On `t-0003` the router wins on cost and accuracy but **loses on latency** (1.25× premium). The reason is that the router does **sequential escalation**: it first calls `swift-coder` → confirms the failure → then climbs to `balanced-pro`. The two calls' latencies **add up**. By contrast:

- **The cheapest model** is fastest, done in one call (but wrong).
- **The ensemble** fans candidates out **in parallel**, so its latency is the **slowest single one** (max).
- **The router** is the **sum** of the calls it tried, so it can be slowest on escalated tasks.

In other words, **there is no free lunch.** The price of the cost and accuracy the router reclaims is **latency** here. On a real-time path where latency is critical, a single premium call may be the sensible choice; on a batch path where cost dominates, the router wins — the arena **meters that trade-off on one screen**.

!!! warning "Latency is an illustrative projection (`measured = false`, not wall-clock)"
    The bundled telemetry has no timing. So latency is an **illustrative projection** that turns token counts into ms with a per-tier throughput model — `latency = (150 + 90·tier) + 1000·(output+reasoning tokens)/(200 − 28·tier)`, ensemble = parallel (max), router = sequential (sum). It exists only to give the third axis a **shape**, not real wall-clock. Real latency has to be measured with real calls in the [live measured bridge](../manual/foundry-live.md). We flag it consistently across UI · CLI · docs as a **different source** from cost/accuracy (offline projection).

## Contrast — easy task `t-0001` (generate, easy)

| Approach | Model | Cost | Latency* | Accuracy |
| --- | --- | --- | --- | --- |
| **Cheapest model** | mini-fast | **`$0.0005`** | **3,080 ms** | ✓ pass |
| Premium model | balanced-pro | `$0.0065` | 4,399 ms | ✓ pass |
| Ensemble (fan-out) | all 3 | `$0.0083` | 4,399 ms | ✓ pass |
| Cost-aware router | mini-fast | `$0.0005` | 3,080 ms | ✓ pass |

On an easy task the **cheapest model wins all three axes** (cheapest · fastest · passes). The router picks exactly that (mini-fast) — its first try passes, so there's no escalation, and premium/ensemble's extra spend ($0.0065 · $0.0083, **up to 17×**) buys nothing. **Routing earns its value on hard tasks** — the arena shows this contrast with one task chip.

## See it in the web app — the arena panel

Below the dashboard spotlight we added a **"one problem, four ways"** panel:

- **Task chips** — click one of the 5 curated tasks (t-0001/0003/0004/0005/0006) to switch. One payload holds every task's arena, so it changes **without a round trip**.
- **Four cards** — model · cost · latency · accuracy per approach. It **highlights the winner by axis** (cost = cheapest pass, latency = fastest pass, accuracy = all that pass) and gives the router card a hero border.
- **A verdict line** — a one-line summary auto-generated per task, like "the router delivers the correct answer 2.5× cheaper than premium, but is slowest because escalation is sequential."

[Open it in the live demo →](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/)

## Reading these numbers honestly

1. **Cost and accuracy are the same offline machine as the aggregate experiments.** So they match the frontier/strategy panels' numbers **by construction** — the arena invents no new claim. `measured = false`.
2. **Latency is a new illustrative projection.** It shows only the **relative shape** between approaches (router = sequential sum, ensemble = parallel max); the absolute ms are not measured. Measure it for real before making a real-time decision.
3. **Accuracy is binary.** Approaches that pass are **equally** correct, so we don't crown only the router but credit all three that pass. Only the cheapest model fails.

So the honest rule: *the arena meters "for this problem, each method's cost, (illustrative) latency, and whether it's correct" at a glance. Trust cost and accuracy as-is, but confirm latency with the measured bridge.*

## When to use this experiment

- When first introducing routing to a team — to convey the cost/latency/accuracy trade-off with **one problem** in 5 minutes, before they read the aggregate frontier.
- To weigh the router's **latency price** (sequential escalation) by eye and decide whether a single premium call fits a real-time path and the router a batch path.
- To demo, switching between an easy task (t-0001) and a hard one (t-0003), that **"routing is only worth it on hard work."**

## Reproduce this experiment

```bash
pip install -e .
cost-router compare                    # the most instructive default task (t-0003)
cost-router compare --task t-0001      # the easy-task contrast
cost-router compare --json             # that task's arena as JSON
```

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

The problem statement (the `problem` block) is an **authored synthetic example** and display-only — the numbers above are the same without the prompt.

## Switching to measured (`measured = true`)

The numbers above are offline projections. Now that the curated tasks carry **sendable prompts**, the same 5 tasks can be measured against the real Azure Model Router — one command once you fill in credentials:

```bash
cost-router foundry live --live \
  --workload samples/telemetry/curated-arena-live.sample.jsonl \
  --pricing  samples/pricing/your-tenant.yaml --store runs.jsonl
```

Cost is computed from real billed usage and becomes `measured = true`, and the result is recorded on the historical dashboard. **Boundary:** the prompts are authored-synthetic, but the **usage and cost** you get by sending them are measured. To measure accuracy (pass/fail) as well, you must inject a `grader`; without one, coverage is labeled as an offline-signal projection. For details, see the [live measured bridge](../manual/foundry-live.md).

For the full manual, see [one problem, four ways](../manual/head-to-head.md), and for the development context, the 2026-07-20 entry in the [development log](/foundry-cost-aware-model-routing/ko/lab-notebook/devlog/).
