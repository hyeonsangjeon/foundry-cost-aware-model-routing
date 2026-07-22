# Foundry Cost-Aware Model Routing

[![ci](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/actions/workflows/ci.yml/badge.svg)](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/actions/workflows/ci.yml)
[![docs](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/actions/workflows/docs.yml/badge.svg)](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/)
[![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Cost-aware model routing over Azure AI Foundry** — send the cheapest model
that still passes, escalate only when it doesn't, and prove the savings hold at
full coverage. Ten one-command experiments make the case *and* mark its limits;
a live bridge routes against your real Foundry deployments and seals the
measured spend into a tamper-evident ledger.

Two honesty rules run through everything: offline runs are **projections over
synthetic data** (`labels.measured=false`), and only a **fresh live call** is
ever labeled `measured=true`. The repo is intentionally small — source, tests,
placeholder configuration, and synthetic samples only; private notes and
diagrams stay outside Git.

📘 **한국어 매뉴얼 · 실험노트 (github.io):**
<https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/>

▶️ **Live interactive dashboard (no install, auto-plays):**
<https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1>
— animated before/after, the cost × coverage frontier, and the policy-A/B
coverage cliff, rendered from the same offline projection.

## Requirements

- **Python 3.11+** — the router uses `StrEnum`, so 3.10 fails to import. Check
  first with `python3 --version`.
- `git`, plus network access for a one-time install (the only core dependency
  is `pyyaml`).

## Quickstart

Clone, create a virtualenv, and install the `cost-router` console script:

```bash
git clone https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing.git
cd foundry-cost-aware-model-routing
python3 -m venv .venv && source .venv/bin/activate    # recommended
pip install -e .                                      # core dep: pyyaml
```

### 1 · Offline preview (30 seconds, no network or credentials)

`cost-router hero` runs the flagship experiment as a **deterministic offline
projection over synthetic data** (`labels.measured=false`) — a *preview*, not a
measurement. It prints a before/after, a spotlight task, and a reproducibility
self-check (it exits non-zero if the projection ever drifts below the contracted
floor):

```bash
cost-router hero
cost-router hero --serve --port 8000   # dashboard; auto-falls back if the port is busy
```

### 2 · Make it real — register your fleet, then measure

The preview above is synthetic. To route against **your** deployed Azure AI
Foundry models, register them in a fleet config, pick which one plays each arm
(router/cheapest/premium/ensemble), and run the live arena — real calls → real
token usage → `measured=true`:

```bash
cost-router models list        # your deployed-model catalog + current slate
cost-router models select --premium gpt-5.4 --ensemble gpt-5.4-nano,gpt-5.4-mini,gpt-5.4
cost-router foundry arena --fleet .foundry-fleet.local.yaml --live
```

See [**Fleet — register & select your models**](#fleet--register--select-your-models)
below for the config format, the terminal `/model` picker, dashboard selection,
and a single-deployment smoke test. Only a fresh live call is ever labeled
`measured=true`; everything offline stays an honest projection.

### The experiment arc — honest by construction

This repo proves where cost-aware routing **wins** and, just as deliberately,
where it **doesn't**. Ten one-command experiments — 01–08 are deterministic
offline projections over synthetic data (`labels.measured=false`); 09–10 are
real **measured** runs against a live Foundry Model Router:

| # | Experiment | Question it answers | Result |
| --- | --- | --- | --- |
| 01 | [Hero](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/lab-notebook/01-hero/) | Routing on a realistic 100-task workload? | 100% coverage, **−25.5%** cost |
| 02 | [Curated](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/lab-notebook/02-curated/) | Five tasks you can follow by eye? | 100% coverage, **−56.7%** cost |
| 03 | [Coverage cliff](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/lab-notebook/03-coverage-cliff/) | Delete the expensive fallback to save more? | looks cheaper, but coverage **100% → 67%** (honest failure) |
| 04 | [No free lunch](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/lab-notebook/04-no-free-lunch/) | A workload where only the top model passes? | 100% coverage, **0%** saved (the boundary) |
| 05 | [Ensemble fan-out tax](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/lab-notebook/05-ensemble-fanout/) | What does "just ensemble every model" really cost? | 100% coverage, **−47%** — but fan-out spends **3.74×** the winner (the hidden tax) |
| 06 | [Adaptive fan-out dial](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/lab-notebook/06-fanout-dial/) | Can you keep the savings but drop the tax? | one budget dial: coverage/savings stay flat, tax **3.74× → $0** (the honest fix for exp 05) |
| 07 | [Routing layer](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/lab-notebook/07-model-router/) | What if you pick once, like Azure AI Foundry Model Router? | single-call routing holds **52%** coverage; observe-then-escalate mix reaches **100%** at ~the same cost (gain **+48%p**) |
| 08 | [Arena](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/lab-notebook/08-arena/) *(per-task lens)* | One problem, four ways — cost · latency · accuracy at a glance? | router is the **cheapest correct** answer but the **slowest** (sequential escalation); latency is a **new illustrative projection** |
| 09 | [Live routing proof](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/lab-notebook/09-live-routing-proof/) *(measured)* | Wired to a real Foundry Model Router, what does it actually pick? | one `model-router` deployment really split to **`gpt-5.4` (×3) and `grok-4-1-fast-reasoning` (×2)** — the repo's **first `measured = true`** run, keyless Entra |
| 10 | [Measured ledger](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/lab-notebook/10-measured-ledger/) *(measured)* | Once it's measured, can anyone re-verify the spend wasn't tampered with? | the live run is sealed into a **hash-chained, cost-replayable** ledger — `measured-replay` re-derives every cost from token usage × a pinned rate card; **one edited byte fails it**, the offline ledger stays untouched |

Experiments 01–02 are the win; 03–07 are the guardrails; 08 is a per-task **lens**
(an interactive arena that collapses the frontier to a single task and adds a
latency axis). Each `expect` contract fails CI if the projection ever drifts —
including a two-sided ceiling that rejects **phantom savings** and an
escalation-gain floor that keeps observe-then-escalate honest. Read them as one
story in the
[**story arc**](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/lab-notebook/story-arc/),
or dive into the full
[Korean lab notebook](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/lab-notebook/).

## Usage

Install with dev tools (ruff, pytest) when you want to run the suite:

```bash
make dev            # or: pip install -e ".[dev]"
```

Replay routing over the sample workload and summarize cost vs. baseline:

```bash
cost-router replay              # curated sample fixture
cost-router replay --synth      # deterministic signals for the whole workload
cost-router route-once --task-id t-0003
cost-router evals --synth       # routed vs. always-most-expensive baseline
```

### Experiments

A named experiment is a small YAML (`experiments/*.yaml`) that pins a workload,
its offline signals, pricing, and policy, plus an `expect` reproducibility
contract. See [`experiments/`](experiments/) and the
[Korean manual](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/manual/experiments/).

```bash
cost-router experiment list          # list available experiments
cost-router experiment run curated   # run one by name
cost-router experiment run hero --json
```

The honest boundary — a workload of genuinely hard tasks where only the top
model passes, so routing keeps full coverage but saves **0%** (a two-sided
`expect` contract fails CI if it ever reports phantom savings; lab notebook:
실험 04 · 공짜 점심은 없다):

```bash
cost-router experiment run limits    # coverage 100.0% · saved 0.0%
```

The honest counter-example — deleting the expensive fallback models looks
cheaper but drops coverage from 100% to 67% (lab notebook: 실험 03 · 커버리지 절벽):

```bash
cost-router policy regression --candidate experiments/policies/cost-cut.yaml --synth
```

The ensemble fan-out tax — routing fans out to every candidate on high-value
tasks (compare mode) but only charges the winner. A common Azure-Foundry-shaped
metrics module (`src/router/metrics.py`) recovers the hidden fan-out cost and
records it for the web app + historical dashboard (lab notebook: 실험 05 · 앙상블
팬아웃 세금):

```bash
cost-router experiment run ensemble          # 100% coverage, −47% — but fan-out is 3.74× the winner
cost-router metrics emit ensemble            # Azure Monitor / OTel metric records (offline, measured=false)
cost-router experiment run ensemble --metrics-store runs.jsonl
cost-router metrics history --store runs.jsonl
```

The adaptive fan-out dial — the honest fix for that tax. The budget gate's
`compare_min_value` is a dial: raise it and the router fans out on fewer tasks.
Coverage (100%) and savings (47%) stay flat while the tax collapses **3.74× → $0**.
Experiment 06 pins this with a `max_tax_ratio` ceiling (lab notebook: 실험 06 ·
적응형 팬아웃 다이얼):

```bash
cost-router experiment run adaptive          # 100% coverage, −47% — fan-out tax dialed to 0.00×
```

The routing layer — Azure AI Foundry **Model Router** is a *single-call* router
(it picks one model per prompt, not an ensemble). Experiment 07 adds it as the
frontier's fifth arm: single-call routing holds only **52%** coverage, while
observe-then-escalate reaches **100%** at ~the same cost — a **+48%p**
escalation gain pinned by a `min_escalation_gain` contract. A dependency-free,
env-gated adapter (`FOUNDRY_*`) lets a live deployment's decisions replace the
offline proxy (lab notebook: 실험 07 · 라우팅 레이어):

```bash
cost-router experiment run model-router      # 100% coverage, −25.5% — single-call vs escalate gain +48%p
```

The live measured bridge — turning that env-gated adapter into **measured
spend**. `cost-router foundry live` scores a Model Router run on the endpoint's
**real token usage** (not synthetic tokens): recorded snapshot `$0.156730 / 100%`
vs the offline projection `$0.087030 / 60%`. `measured=true` is reserved for a
genuine live call; without credentials it replays a recorded snapshot so the path
stays offline/deterministic. Secrets are never printed — `foundry status` masks
them (manual: 라이브 실측 브릿지):

```bash
cost-router foundry status                   # redacted config + live-call readiness
cost-router foundry live                      # recorded snapshot (offline, measured=false)
cost-router foundry live --store runs.jsonl   # record into the historical dashboard
cost-router foundry live --live --workload my-prompts.jsonl \
  --pricing samples/pricing/your-tenant.yaml  # real Azure calls → measured=true
```

### The 30-second before / after

`make replay` (and `cost-router replay`) end with a naive-vs-routed block: the
naive column bills the most expensive candidate for every task, the routed
column is cost-aware routing (cheapest candidate that passes its own checks,
escalate only on failure). Over the full 100-row synthetic workload:

```text
before / after  (offline projection over synthetic data; labels.measured=false)
  BEFORE  naive: premium model on every task   $2.226910
  AFTER   cost-aware routing                   $1.659167
  SAVED   $0.567743  (25.5% lower)  at 100.0% coverage
  strategy  single-route=74 ensemble=26  |  clean-first=19 compared=18 escalated=55 tie-broken=8
```

These numbers are an **offline projection over synthetic data**, not a measured
result — every trace carries `labels.measured=false`. Real savings depend on
your own workload mix and rates. All model names are generic placeholders.

The same flows are available without installing, via `make` or `python -m router`:

```bash
make replay        make replay-all      # full workload (deterministic synth signals)
make evals         make evals-all
make check         make test            # validation gate / pytest
```

With `--synth`, offline check signals are derived deterministically from each
task's class, difficulty, and policy priors, so the full workload replays
identically every time. All model names are generic placeholders.

## Audit ledger & single-call baselines

Record every decision from a replay (or one task) to an append-only JSONL ledger,
then re-run the stored selection inputs and verify the canonical final payload:

```bash
cost-router replay --synth --ledger reports/routing.local.jsonl
cost-router ledger replay --ledger reports/routing.local.jsonl
```

The ledger stores policy/pricing hashes, normalized task risk/difficulty,
candidate order and signals, the gate decision, chosen model/cost, and honest
offline labels. Verification passes only when all stored decisions reproduce
byte-for-byte and required-field completeness is at least 99%.

The current router selects one execution from **precomputed offline signals**;
those signal inspections are not model calls. Ledger cost therefore uses the
explicit `selected-execution-only` billing basis. A future live fan-out layer
must account for every panel/judge call separately.

Replay/eval summaries also expose three transparent **illustrative equivalents**
for single-call comparisons: `cost` picks each class's cheapest candidate,
`balanced` its middle candidate, and `quality` its most expensive candidate.
They are deterministic placeholder baselines, not claims about a managed
router's internal implementation.

## Fleet — register & select your models

The live head-to-head (`cost-router foundry arena`) and the dashboard build
their four strategy arms from a **fleet config**: which *deployed* Azure AI
Foundry model plays each role — the **router (main)**, the **cheapest** floor,
the **premium** ceiling, and the **ensemble** fan-out. This is the "register
your models" step, and it lives in a small YAML you own:

```yaml
# samples/fleet/foundry-5series.fleet.yaml
models:
  - { name: gpt-5.4-nano, deployment: gpt-5.4-nano, tier: small }
  - { name: gpt-5.4,      deployment: gpt-5.4,      tier: frontier }
  - { name: model-router, deployment: model-router, tier: router }
roles:
  router: model-router
  cheapest: gpt-5.4-nano
  premium: gpt-5.4
  ensemble: [gpt-5.4-nano, gpt-5.4-mini, gpt-5.4]
```

`name` is the logical/pricing key; `deployment` is the Azure deployment name the
live client calls (decoupled on purpose). Point any run at your file with
`--fleet PATH` or `FOUNDRY_FLEET_PATH`; with neither, the bundled sample (then a
safe in-code default) is used.

**Select from the terminal** — inspect the catalog, then pick each arm (an
interactive `/model` picker, or non-interactive flags). The choice is saved to a
gitignored `.foundry-fleet.local.yaml`:

```bash
cost-router models list          # catalog + current slate + live readiness
cost-router models select        # interactive: enter a number or name per arm
cost-router models select --premium gpt-5.4 --ensemble gpt-5.4-nano,gpt-5.4-mini,gpt-5.4
cost-router foundry arena --fleet .foundry-fleet.local.yaml --live   # measure YOUR slate
```

**Select from the dashboard** — the "Fleet & live routing" panel lists the same
catalog with dropdowns for router/cheapest/premium and ensemble checkboxes.
"Run selection" replays the committed measured snapshot (honestly relabeled
`measured = false`, `provenance = recorded` — the web path never makes paid
calls) and prints the exact terminal command to measure your selection live.

> **Only one deployment?** Copy `samples/fleet/single-deployment.example.yaml`,
> point every arm at your one model, and you can still prove the whole live path
> end-to-end (keyless Entra → real call → token usage → priced → hash-chained
> ledger). Every arm ties — that is the point of a single-deployment smoke.

## Service

The same routing pipeline is available as a small offline HTTP service built on
the Python standard library (no web framework, no provider calls):

```bash
cost-router serve --host 127.0.0.1 --port 8000   # or: make serve
```

If the port is already in use, the server falls back to the next free port and
prints the actual URL instead of crashing.

Endpoints (all JSON, all deterministic and network-free):

| Method | Path           | Purpose                                                  |
| ------ | -------------- | -------------------------------------------------------- |
| GET    | `/healthz`     | Liveness probe.                                          |
| GET    | `/policy`      | Policy version and ordered candidates per task class.    |
| GET    | `/fleet`       | Model catalog, current slate, and live readiness.        |
| POST   | `/fleet/run`   | Validate a selected slate; replay the recorded arena.    |
| POST   | `/route`       | Route one task payload, return its routing trace.        |
| POST   | `/batch-route` | Route many task payloads, return traces plus a summary.  |

Route a single task (synthesizing offline check signals when none are supplied):

```bash
curl -s http://127.0.0.1:8000/route \
  -H 'content-type: application/json' \
  -d '{"task": {"task_id": "t-0001", "class": "generate",
                "tokens": {"input": 1232, "cached": 448, "output": 418, "reasoning": 168}},
       "synth": true}'
```

`pricing` accepts `"illustrative"` (default, bundled sample rates) or `"none"`
to omit cost estimates. Provide `signals` per model to override the synthesized
offline checks. `/batch-route` takes a `tasks` array and returns the same
aggregate summary as `cost-router evals`.

### Container

A public-safe image runs the offline service with no secrets or local notes in
its build context:

```bash
make docker-build          # docker build -t cost-router:local .
make docker-run            # serves on http://127.0.0.1:8000
```

## Policy ops & regression guard

Inspect, validate, diff, and simulate routing policies — and check cost/coverage
regressions before changing one:

```bash
cost-router policy show
cost-router policy validate --policy src/policy/seed_policy.yaml
cost-router policy diff --candidate samples/policy/candidate.example.yaml
cost-router policy simulate --policy samples/policy/candidate.example.yaml --synth
cost-router policy regression --candidate samples/policy/candidate.example.yaml --synth
```

`replay`, `route-once`, `evals`, and `serve` all accept an optional `--policy PATH`.
Resolution precedence is **CLI `--policy` > `COST_ROUTER_POLICY` env var > bundled
seed**; the service binds whichever policy was chosen at startup (requests can't
pick a file).

The regression report scores the base and candidate policies on **one shared set
of evaluation signals** so the deltas isolate the routing change. With `--synth`
the signals are synthesized once from the *union* of both policies' candidates:
shared models keep the base policy's prior, and the most expensive model in the
union is the guaranteed clean fallback. Raising a candidate's `prior_pass` alone
therefore leaves the signals untouched (zero delta), while dropping an expensive
fallback exposes the coverage risk it creates instead of hiding it. Over the
synthetic 100-row workload the bundled candidate (which removes the `premium-max`
fallback from `repo_patch`) routes for `$1.337137` vs the seed's `$1.659167`, but
coverage drops to `93%` (base `100%`) — the report surfaces that trade-off rather
than masking it. The result is deterministic for a given workload, and all models
stay generic placeholders.
