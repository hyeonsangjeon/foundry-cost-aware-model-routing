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
