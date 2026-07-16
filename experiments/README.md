# Experiments

A named experiment is a small YAML file that pins a **workload**, its offline
**signals** (curated fixture or deterministic synthesis), a **pricing** table,
and a **policy**, plus an `expect` **reproducibility contract**. Running one
re-derives the naive-vs-routed before/after and fails loudly if the offline
projection ever drifts below the contracted floor.

Everything is offline, deterministic, and labelled `measured = false` — these
are projections over synthetic data, not measured savings.

## Run

```bash
cost-router hero                 # the flagship experiment (experiments/hero.yaml)
cost-router experiment list      # list every experiment
cost-router experiment run curated
cost-router experiment run ensemble  # best-of-N fan-out: 100% coverage, -47%, but a 3.74x fan-out tax
cost-router experiment run adaptive  # the honest fix: same coverage/savings, fan-out tax dialed to 0.00x
cost-router experiment run limits    # the honest boundary: routing saves ~0% here
cost-router experiment run model-router  # single-call routing layer: 52% coverage vs mix's 100% (gain +48%p)
cost-router experiment run hero --json
```

`cost-router hero --serve` runs the experiment and then boots the offline
dashboard so you can watch the routing decisions live.

## The honest boundary (no free lunch)

`limits.yaml` is the deliberate counter-weight to the hero run: a curated set of
genuinely hard tasks where **only the most expensive candidate passes** every
offline check. Routing tries the cheap models, watches them fail, and escalates
to the top model on every task — so it keeps **full coverage** while saving
**0%**. Its `expect` block is a *two-sided* contract (`min_coverage: 1.0` **and**
`max_delta_pct: 0.0`), so CI fails if this workload ever reports phantom savings.

```bash
cost-router experiment run limits
# coverage 100.0% · saved 0.0% → routing spends correctly on hard work.
```

See the lab notebook: **실험 04 · 공짜 점심은 없다**.

## Ensemble fan-out tax (the hidden cost of "just run every model")

`ensemble.yaml` uses a curated set of high-value tasks where the cheap
candidate fails one check and the mid/top candidates pass fully (a tie broken to
the cheapest passing model). The budget gate sends these to **compare mode**, so
routing fans out to *every* candidate but only charges the winner. The common
metrics module (`src/router/metrics.py`) recovers what that fan-out really cost:

```bash
cost-router experiment run ensemble
# coverage 100.0% · saved 47.0% — but the 6 tasks fan out to $0.496812 of models
# and keep $0.132801 of winners: a $0.364011 (3.74x) ensemble tax.
cost-router metrics emit ensemble                        # Azure Foundry-shaped metric records
cost-router experiment run ensemble --metrics-store runs.jsonl  # record to history
cost-router metrics history --store runs.jsonl           # historical dashboard feed
```

The metrics are provider-neutral and `measured = false`: `FoundryMetricsEmitter`
renders Azure Monitor / OpenTelemetry records and only forwards through an
injected sink, so the default path never touches the network. See the lab
notebook: **실험 05 · 앙상블 팬아웃 세금**.

## Adaptive fan-out dial (the honest fix for the tax)

`adaptive.yaml` answers experiment 05: the ensemble tax is a **dial**, not a
fixed cost. The budget gate's `compare_min_value` is the knob — raise it and the
router fans out on fewer tasks. Coverage (100%) and savings (47%) stay flat while
the tax collapses. `adaptive.yaml` sets it to `1.1` (above every task's value),
so nothing fans out and the tax is exactly `$0.000000`. Its `expect` block adds a
`max_tax_ratio` ceiling, so CI fails if fan-out ever creeps back in.

```yaml
budget:
  compare_min_value: 1.1      # dial the fan-out threshold above every task value
  min_compare_candidates: 2
expect:
  max_tax_ratio: 0.01         # fan-out cost / winner cost must stay ~0
```

```bash
cost-router experiment run adaptive
# coverage 100.0% · saved 47.0% · fan-out tax 0.00x → same win, no tax.
```

The dashboard's **fan-out dial** panel sweeps the threshold live (`/fanout-sweep`)
so you can watch coverage/savings hold flat while the tax steps down to zero. See
the lab notebook: **실험 06 · 적응형 팬아웃 다이얼**.

## Policy regression (the coverage cliff)

`experiments/policies/` holds candidate policies for **regression experiments**
— the honest counter-story to the before/after wins. `cost-cut.yaml` naively
deletes the expensive fallback models to look cheaper; comparing it against the
seed policy exposes the coverage it silently loses:

```bash
cost-router policy regression --candidate experiments/policies/cost-cut.yaml --synth
# coverage: 67.0% (base 100.0%)  → cheaper only because a third of tasks no
# longer have a model that passes. Cost is comparable only at fixed coverage.
```

See the lab notebook: **실험 03 · 커버리지 절벽**.

## Routing layer (single-call vs observe-then-escalate)

Azure AI Foundry **Model Router** is a *single-call* routing layer — it picks one
model per prompt, up front (not an ensemble). `model-router.yaml` adds that shape
as the frontier's fifth arm and pins the honest gap: committing per prompt with
no escalation loses coverage that observe-then-escalate keeps.

```bash
cost-router experiment run model-router
# coverage 100.0% · saved 25.5% · escalation_gain: mix 100% − single-call 52% = +48%p ≥ 30%
```

The `model_router` arm is a transparent proxy (`measured=false`,
`equivalent=illustrative`) for a router's *shape*, not Azure's internal logic. To
score a **real** deployment's decisions on the same offline frontier, use the
dependency-free, env-gated adapter `router.foundry_router.FoundryModelRouter`:

```bash
export AZURE_AI_FOUNDRY_ENDPOINT=...          # or AZURE_OPENAI_ENDPOINT
export AZURE_AI_FOUNDRY_MODEL_ROUTER=...      # the Model Router deployment name
export AZURE_AI_FOUNDRY_API_KEY=...           # or AZURE_OPENAI_API_KEY
```

With no config the adapter is inert and the offline proxy stands in; even with
live **decisions** the cost/coverage stay offline projections (`measured=false`)
— only the model *choice* may be live. A recorded snapshot lives at
`samples/responses/model-router-choices.sample.json`. See the lab notebook:
**실험 07 · 라우팅 레이어**.

## Fields

| field | meaning |
| --- | --- |
| `name` / `title` / `summary` | identity and human description |
| `dataset.workload` | workload JSONL (default: bundled sample) |
| `dataset.signals` | offline signals JSON, or `null` to synthesize |
| `dataset.synth` | `true` → derive signals deterministically |
| `policy` / `pricing` | policy + pricing YAML (default: bundled) |
| `budget.compare_min_value` | optional fan-out threshold — compare (fan out) only when task value ≥ this; raise it to shrink the tax (see `adaptive.yaml`) |
| `budget.min_compare_candidates` | optional minimum candidates required before compare mode |
| `spotlight` | `auto`, a `task_id`, or `none` — the task to highlight |
| `expect.min_coverage` | routing must keep at least this coverage |
| `expect.min_delta_pct` | …while cutting at least this share of the naive bill |
| `expect.max_delta_pct` | optional **upper** bound — savings must not exceed this (guards against phantom savings; see `limits.yaml`) |
| `expect.max_tax_ratio` | optional **fan-out tax ceiling** — fan-out cost / winner cost must not exceed this (see `adaptive.yaml`) |
| `expect.min_escalation_gain` | optional **escalation-gain floor** — mix coverage − single-call `model_router` coverage must be ≥ this (see `model-router.yaml`) |
| `expect.min_tasks` | minimum tasks the run must cover |

> 한국어 매뉴얼과 실험노트는 GitHub Pages 문서 사이트를 참고하세요 (`docs/`).
