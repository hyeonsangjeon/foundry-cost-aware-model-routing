# Foundry Cost-Aware Model Routing

Initial Python scaffold for model-routing experiments.

This repository is intentionally kept small: source code, tests, placeholder
configuration, and synthetic sample data only. Internal planning material,
private notes, launch notes, and diagrams stay outside Git.

## Usage

Everything runs offline against the checked-in synthetic samples — no network,
no credentials, deterministic results.

Install the package (provides the `cost-router` console script):

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

## Service

The same routing pipeline is available as a small offline HTTP service built on
the Python standard library (no web framework, no provider calls):

```bash
cost-router serve --host 127.0.0.1 --port 8000   # or: make serve
```

Endpoints (all JSON, all deterministic and network-free):

| Method | Path           | Purpose                                                  |
| ------ | -------------- | -------------------------------------------------------- |
| GET    | `/healthz`     | Liveness probe.                                          |
| GET    | `/policy`      | Policy version and ordered candidates per task class.    |
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
