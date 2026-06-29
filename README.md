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

The same flows are available without installing, via `make` or `python -m router`:

```bash
make replay        make replay-all      # full workload (deterministic synth signals)
make evals         make evals-all
make check         make test            # validation gate / pytest
```

With `--synth`, offline check signals are derived deterministically from each
task's class, difficulty, and policy priors, so the full workload replays
identically every time. All model names are generic placeholders.

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
pick a file). The regression report is deterministic for a given workload — over
the synthetic 100-row workload the bundled candidate routes for `$1.478647` vs the
seed's `$1.659167` (≈11% cheaper) at unchanged 100% coverage. All models stay
generic placeholders.
