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
cost-router experiment run hero --json
```

`cost-router hero --serve` runs the experiment and then boots the offline
dashboard so you can watch the routing decisions live.

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

## Fields

| field | meaning |
| --- | --- |
| `name` / `title` / `summary` | identity and human description |
| `dataset.workload` | workload JSONL (default: bundled sample) |
| `dataset.signals` | offline signals JSON, or `null` to synthesize |
| `dataset.synth` | `true` → derive signals deterministically |
| `policy` / `pricing` | policy + pricing YAML (default: bundled) |
| `spotlight` | `auto`, a `task_id`, or `none` — the task to highlight |
| `expect.min_coverage` | routing must keep at least this coverage |
| `expect.min_delta_pct` | …while cutting at least this share of the naive bill |
| `expect.min_tasks` | minimum tasks the run must cover |

> 한국어 매뉴얼과 실험노트는 GitHub Pages 문서 사이트를 참고하세요 (`docs/`).
