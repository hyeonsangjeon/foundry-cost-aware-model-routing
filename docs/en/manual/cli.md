# CLI reference

Every subcommand is a thin wrapper around the same orchestration in
[`router.pipeline`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/src/router/pipeline.py).
That way the CLI, the sample scripts, and the evals all travel exactly the same
path.

```bash
cost-router --help
cost-router --version
```

## Common data flags

Shared across `replay` · `route-once` · `evals` · `policy simulate/regression`.

| Flag | Meaning | Default |
| --- | --- | --- |
| `--workload PATH` | Workload JSONL | Bundled sample |
| `--signals PATH` | Offline signals JSON | Bundled sample |
| `--pricing PATH` | Pricing YAML | Bundled illustrative pricing |
| `--synth` | Synthesize every task's signals deterministically | Off |
| `--policy PATH` | Policy YAML | Seed policy |

Policy precedence: `--policy` > environment variable `COST_ROUTER_POLICY` > bundled seed.

## hero — the hero run

Runs the flagship experiment (`experiments/hero.yaml`) end to end and prints the
before/after, the spotlight, and the reproducibility self-check. If it fails the
contract it exits with a **non-zero code**.

```bash
cost-router hero               # text summary
cost-router hero --json        # machine-readable JSON
cost-router hero --ledger reports/hero.jsonl   # record decisions to the audit ledger
cost-router hero --serve       # run, then boot the dashboard (http://127.0.0.1:8000)
cost-router hero --serve --host 0.0.0.0 --port 9000
```

`--serve` points you at `http://127.0.0.1:8000/?run=1`. Open that address and the
before/after animation and spotlight play **the moment it loads** — no clicking
required (about 20 seconds).

## compare — one problem, four ways

Compares a **single** task four ways side by side and prints **cost · latency ·
accuracy** as a table: the cheapest model · the premium model · the ensemble that
fans out to everyone · the cost-aware router that climbs up from the cheapest.
It is the CLI version of the dashboard's arena panel.

```bash
cost-router compare                    # the most instructive default task (t-0003)
cost-router compare --task t-0001      # a specific task
cost-router compare --json             # that task's arena as JSON
```

The router **bills only the winner** while the ensemble **bills every candidate**
(the fan-out tax). Accuracy is the router's `is_clean` verdict; latency is an
**illustrative projection** derived from token counts (not a measurement,
`measured = false`). For the full reading see
[one problem, four ways](head-to-head.md).

## experiment — named experiments

```bash
cost-router experiment list                # list the available experiments
cost-router experiment run curated         # run by name
cost-router experiment run hero --json
cost-router experiment run ./path/to/my.yaml   # or run by file path
cost-router experiment run curated --ledger reports/curated.jsonl
```

For the experiment YAML schema see [experiment configuration (YAML)](experiments.md).

## replay — replay a workload

```bash
cost-router replay                 # the curated sample fixture
cost-router replay --synth         # the whole workload with deterministic signals
cost-router replay --json          # the trace as JSON
cost-router replay --synth --ledger reports/routing.jsonl
```

A naive-vs-routing before/after block is appended at the end.

## route-once — a single trace

```bash
cost-router route-once --task-id t-0003 --synth
cost-router route-once --task-id t-0001 --ledger reports/one.jsonl
```

Prints the JSON trace for one task — its candidates, attempts, selection, and cost.

## evals — cost-vs-baseline summary

```bash
cost-router evals --synth
```

Produces a coverage/cost summary of the routing cost against the "always the most
expensive" baseline.

## serve — offline HTTP service

```bash
cost-router serve                       # http://127.0.0.1:8000
cost-router serve --host 0.0.0.0 --port 9000 --policy src/policy/seed_policy.yaml
```

An offline service that runs on the standard library alone. If the requested port
is already in use it falls back automatically to the next free port and prints the
actual URL (no traceback). See [the dashboard](dashboard.md) for details.

## policy — inspect/validate/compare policies

```bash
cost-router policy show
cost-router policy validate --policy src/policy/seed_policy.yaml
cost-router policy diff --candidate samples/policy/candidate.example.yaml
cost-router policy simulate --policy samples/policy/candidate.example.yaml --synth
cost-router policy regression --candidate samples/policy/candidate.example.yaml --synth
```

`regression` compares the cost/coverage shift of the baseline policy against a
candidate policy deterministically.

## ledger — replay/verify the audit ledger

```bash
cost-router ledger replay --ledger reports/routing.jsonl
```

Replays the stored decisions and verifies the canonical final payload byte for
byte. See [the audit ledger](ledger.md) for details.

## foundry — the live measured bridge (opt-in)

```bash
cost-router foundry status              # check the wiring (secrets masked)
cost-router foundry status --json
cost-router foundry live                # replay the recorded snapshot (offline, measured=false)
cost-router foundry live --store runs.jsonl   # record into the historical dashboard
cost-router foundry live --live --workload my-prompts.jsonl \
  --pricing samples/pricing/your-tenant.yaml  # real calls → measured=true
```

`status` summarizes the Azure Foundry environment variables **without exposing
secrets**. `live` scores a Model Router run against **real token usage** — without
`--live` it replays the recorded snapshot, so you can see the path even with no
credentials. See [the live measured bridge](foundry-live.md) for details.

## models — fleet registration & arm selection

```bash
cost-router models list          # catalog + current slate + live-readiness
cost-router models show          # resolved role -> deployment (supports --json)
cost-router models select        # interactive /model picker (enter a number or a name)
cost-router models select --premium gpt-5.4 --ensemble gpt-5.4-nano,gpt-5.4-mini,gpt-5.4
```

Registers and selects which deployed model backs each arm
(router/cheapest/premium/ensemble). The selection is saved to the gitignored
`.foundry-fleet.local.yaml`. Every command can read a different fleet file with
`--fleet PATH` (or `FOUNDRY_FLEET_PATH`). Then run the measured arena on that fleet:

```bash
cost-router foundry arena --fleet .foundry-fleet.local.yaml         # preview (prints the slate)
cost-router foundry arena --fleet .foundry-fleet.local.yaml --live  # real calls → measured=true
```

See [fleet registration & model selection](fleet.md) for details.
