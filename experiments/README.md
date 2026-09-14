# Experiments

Every experiment here tests the same intervention: **route each task to the
cheapest candidate model first, check the result against offline signals, and
escalate to a stronger model only when that check fails** — with a budget gate
deciding, before any extra call is made, whether the task is worth calling more
than one model on. The comparison is always against the **premium-on-every-task
baseline**, which bills the most expensive candidate on every task and which the
CLI labels `naive`. An **arm** is one such strategy
scored over the same workload.

A named experiment is a small YAML file that pins a **workload**, its offline
**signals** (curated fixture or deterministic synthesis), a **pricing** table,
and a **policy**, plus an `expect` block of **reproducibility criteria**. Running
one re-derives the before/after against that premium baseline and fails loudly if
the offline projection ever drifts below the contracted floor.

Everything on this page is offline, deterministic, and labelled
`measured = false` — these are projections over synthetic data, not measured
savings. No model is called, so nothing here can tell you what a real deployment
would bill. For runs that did call real models, see the measured track
(experiments 09 · 10 · 12 · 13, plus 11, which is measured but voided by its own
grading-coverage gate) in the
[lab notebook](../docs/en/lab-notebook/index.md).

## Run

```bash
cost-router hero                 # the default experiment (experiments/hero.yaml)
cost-router experiment list      # list every experiment
cost-router experiment run curated
cost-router experiment run ensemble  # best-of-N fan-out: 100% coverage, -47%, but extra calls cost 3.74x the winner
cost-router experiment run adaptive  # the honest fix: same coverage/savings, extra-call ratio down to 0.00x
cost-router experiment run limits    # the honest boundary: routing saves ~0% here
cost-router experiment run single-call  # one pick per prompt, no escalation: 52% pass rate vs 100% when escalating
cost-router experiment run hero --json
```

`cost-router experiment list` prints **six** runnable experiments, which is fewer
than the thirteen write-ups in the lab notebook: the remaining ones are driven by
`policy regression`, `foundry arena`, and the measured commands rather than by an
`experiments/*.yaml` file.

`cost-router hero --serve` runs the experiment and then boots the offline
dashboard so you can watch the routing decisions live.

## The honest boundary (no free lunch)

`limits.yaml` is the deliberate counter-weight to the default run: a curated set
of genuinely hard tasks where **only the most expensive candidate passes** every
offline check. Routing tries the cheap models, watches them fail, and escalates
to the top model on every task — so it keeps a **100% pass rate** while saving
**0%**. Its `expect` block is a *two-sided* contract (`min_coverage: 1.0` **and**
`max_delta_pct: 0.0`), so CI fails if this workload ever reports phantom savings.

```bash
cost-router experiment run limits
# coverage 100.0% · saved 0.0% → routing spends correctly on hard work.
```

See the lab notebook:
[Experiment 04 · When every task is hard, there is no saving](../docs/en/lab-notebook/04-no-free-lunch.md).

**What this result supports.** On a workload of genuinely hard tasks, adopt
routing for the pass-rate guarantee and the audit trail, not for savings. The
`expect` block treats any saving reported here as a failure, so a future change
that appears to find one is a bug until proven otherwise.

## Extra candidate-call cost (the hidden price of "just run every model")

`ensemble.yaml` uses a curated set of high-value tasks where the cheap
candidate fails one check and the mid/top candidates pass fully (a tie broken to
the cheapest passing model). The budget gate sends these to **compare mode**, so
routing fans out to *every* candidate but only charges the winner. The common
metrics module (`src/router/metrics.py`) recovers what that fan-out really cost:

```bash
cost-router experiment run ensemble
# coverage 100.0% · saved 47.0% — but the 6 tasks fan out to $0.50 of models
# and keep $0.13 of winners: a $0.36 (3.74x) extra candidate-call cost.
cost-router metrics emit ensemble                        # Azure Foundry-shaped metric records
cost-router experiment run ensemble --metrics-store runs.jsonl  # record to history
cost-router metrics history --store runs.jsonl           # historical dashboard feed
```

Those three dollar figures are rounded for display. At full precision the run
reports `fanout_usd 0.496812`, `winner_usd 0.132801` and
`ensemble_tax_usd 0.364011`; the `3.74x` is `fanout_usd / winner_usd`. Subtracting
the two rounded amounts gives `$0.37`, which is not how the figure is computed.

The metrics are provider-neutral and `measured = false`: `FoundryMetricsEmitter`
renders Azure Monitor / OpenTelemetry records and only forwards through an
injected sink, so the default path never touches the network. See the lab
notebook:
[Experiment 05 · Calling several models at once multiplies the cost](../docs/en/lab-notebook/05-ensemble-fanout.md).

**What this result supports.** Do not adopt "call every candidate and keep the
best" as a default. Price the extra calls first: here they cost 3.74× what the
winning call did, for the same pass rate the escalating strategy already reached.

## The fan-out threshold (the honest fix for that cost)

`adaptive.yaml` answers experiment 05: the extra candidate-call cost is a
**threshold you set**, not a fixed price. The budget gate's `compare_min_value` is
the knob — raise it and the router fans out on fewer tasks. The pass rate (100%)
and the savings (47%) stay flat while the extra-call cost collapses. `adaptive.yaml`
sets it to `1.1` (above every task's value), so nothing fans out and the extra cost
is exactly `$0.00`. Its `expect` block adds a `max_tax_ratio` ceiling, so CI fails if
fan-out ever creeps back in.

```yaml
budget:
  compare_min_value: 1.1      # set the fan-out threshold above every task value
  min_compare_candidates: 2
expect:
  max_tax_ratio: 0.01         # fan-out cost / winner cost must stay ~0
```

```bash
cost-router experiment run adaptive
# coverage 100.0% · saved 47.0% · extra-call ratio 0.00x → same win, no extra cost.
```

The dashboard's **fan-out** panel sweeps the threshold live (`/fanout-sweep`)
so you can watch the pass rate and the savings hold flat while the extra-call ratio
steps down to zero. See the lab notebook:
[Experiment 06 · When is it worth calling several models](../docs/en/lab-notebook/06-fanout-dial.md).

**What this result supports.** Keep fan-out available but gate it on task value.
On this workload the threshold that removes every extra call costs nothing in
pass rate or savings, so fan-out should be opt-in per task rather than on by
default.

## Policy regression (the pass-rate cliff)

`experiments/policies/` holds candidate policies for **regression experiments**
— the honest counter-story to the before/after wins. `cost-cut.yaml` naively
deletes the expensive fallback models to look cheaper; comparing it against the
seed policy exposes the pass rate it silently loses:

```bash
cost-router policy regression --candidate experiments/policies/cost-cut.yaml --synth
# coverage: 67.0% (base 100.0%)  → cheaper only because a third of tasks no
# longer have a model that passes. Cost is comparable only at fixed coverage.
```

See the lab notebook:
[Experiment 03 · What you lose by using only the cheapest model](../docs/en/lab-notebook/03-coverage-cliff.md).

**What this result supports.** Reject any policy change that is justified by cost
alone. Compare policies at a fixed pass rate, because deleting an expensive
fallback always looks cheaper and this one silently drops a third of the tasks.

## One pick per prompt vs checking the result and escalating

Azure AI Foundry **Model Router** picks one model per prompt, up front, in a
single call (not an ensemble). `single-call.yaml` adds that shape as the
frontier's fifth arm and pins the honest gap: committing per prompt with no
escalation loses pass rate that checking the result and escalating keeps.

```bash
cost-router experiment run single-call
# coverage 100.0% · saved 25.5% · escalation_gain: +48.0 percentage points ≥ 30.0 percentage points
```

The `single_call` arm is a transparent proxy (`measured=false`,
`equivalent=illustrative`) for a router's *shape*, not Azure's internal logic. To
score a **real** deployment's decisions on the same offline frontier, use the
dependency-free, env-gated adapter `router.foundry_router.FoundryModelRouter`:

```bash
export AZURE_AI_FOUNDRY_ENDPOINT=...          # or AZURE_OPENAI_ENDPOINT
export AZURE_AI_FOUNDRY_MODEL_ROUTER=...      # the Model Router deployment name
export AZURE_AI_FOUNDRY_API_KEY=...           # or AZURE_OPENAI_API_KEY
```

With no config the adapter is inert and the offline proxy stands in; even with
live **decisions** the cost and pass-rate figures stay offline projections
(`measured=false`) — only the model *choice* may be live. A recorded snapshot
lives at
`samples/responses/model-router-choices.sample.json`. See the lab notebook:
[Experiment 07 · One pick vs observe-then-escalate](../docs/en/lab-notebook/07-model-router.md).

**What this result supports.** Treat model selection as solved by the product and
put the effort into what happens after the pick. On this workload, committing to
one model per prompt leaves **48% of tasks unsolved** — a 48 percentage-point gap
against observe-then-escalate — which checking the result and escalating recovers
at about the same cost. In the command output above, the gain is printed as `+48.0 percentage points`.

### Arm naming (`single_call`, formerly `model_router`)

The single-call routing arm is named **`single_call`**. Its earlier name
`model_router` stays as a backward-compatible alias, so nothing breaks:

| current | alias (still works) |
| --- | --- |
| experiment `single-call` (`single-call.yaml`) | `cost-router experiment run model-router` |
| strategy key `single_call` | `model_router` (emitted alongside it) |
| `single_call_pick()` / `single_call_summary()` | `model_router_pick()` / `model_router_summary()` |

The real Azure deployment name `model-router` and the sample file
`model-router-choices.sample.json` are unchanged — only the offline arm/strategy
identifier was renamed.

## Fields

| field | meaning |
| --- | --- |
| `name` / `title` / `summary` | identity and human description |
| `dataset.workload` | workload JSONL (default: bundled sample) |
| `dataset.signals` | offline signals JSON, or `null` to synthesize |
| `dataset.synth` | `true` → derive signals deterministically |
| `policy` / `pricing` | policy + pricing YAML (default: bundled) |
| `budget.compare_min_value` | optional fan-out threshold — compare (fan out) only when task value ≥ this; raise it to shrink the extra candidate-call cost (see `adaptive.yaml`) |
| `budget.min_compare_candidates` | optional minimum candidates required before compare mode |
| `spotlight` | `auto`, a `task_id`, or `none` — the representative task the run highlights |
| `expect.min_coverage` | routing must keep at least this pass rate |
| `expect.min_delta_pct` | routing must cut at least this share of the premium baseline's bill |
| `expect.max_delta_pct` | optional **upper** bound — savings must not exceed this (guards against phantom savings; see `limits.yaml`) |
| `expect.max_tax_ratio` | optional **ceiling on extra candidate-call cost** — fan-out cost / winner cost must not exceed this (see `adaptive.yaml`) |
| `expect.min_escalation_gain` | optional **escalation-gain floor** — the escalating strategy's pass rate minus the `single_call` arm's pass rate must be at least this, in percentage points (see `single-call.yaml`) |
| `expect.min_tasks` | minimum tasks the run must cover |

The field name `min_coverage` and the CLI's `coverage` line both mean the offline
**pass rate**: tasks a model passed ÷ tasks counted. The measured runs distinguish
that from **grading coverage**, which counts cells rather than tasks; see the
[glossary](../docs/en/manual/glossary.md). The CLI names the strategy
`observe-then-escalate` and reports the gain in `percentage points`.

---

**한국어** — 같은 내용의 한국어 매뉴얼과 실험노트는 문서 사이트의 한국어 판을
보세요: <https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/ko/>
(English: <https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/>).
