# 30-second install

These experiments are **offline and deterministic**. No network, no credentials,
no external API calls. Everything reproduces identically from the synthetic samples
shipped in the repo.

## Requirements

- **Python 3.11 or newer** (3.12 recommended)
- `pip` (or an equivalent such as [`uv`](https://docs.astral.sh/uv/))

## Install

```bash
git clone https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing
cd foundry-cost-aware-model-routing
pip install -e .
```

`pip install -e .` installs the `cost-router` console script. If you also want the
dev tools (ruff, pytest):

```bash
pip install -e ".[dev]"     # or:  make dev
```

!!! tip "If you use uv"
    ```bash
    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python -e ".[dev]"
    ```

## Run it now

```bash
cost-router hero            # flagship experiment (100 synthetic tasks) — before/after in one shot
cost-router experiment list # list the available experiments
cost-router replay          # replay the curated sample
cost-router replay --synth  # replay the full workload from deterministic signals
```

Without installing, `make` or `python -m router` runs the same thing:

```bash
make replay        make replay-all
make evals         make evals-all
make check         make test
```

## Check the install worked

```bash
cost-router --version
cost-router hero           # a reproducibility PASS on the last line means it's fine
```

`cost-router hero` carries a **reproducibility contract** — coverage, savings rate,
and task count must meet preset thresholds to pass. Fail the contract and it exits
with a **non-zero exit code**. In other words, it won't quietly wave through a
"runs, but the numbers look off" state.

## How long does it take — measured on supported interpreters

Below are the **fresh clone → install → first result** times, actually re-measured
on the supported interpreters (**CPython 3.11 · 3.12**). The earlier macOS/Python
3.14 observations are **outside the supported set** and are no longer used as a
baseline.

| Stage | Python 3.11.15 | Python 3.12.13 | Nature |
| --- | --- | --- | --- |
| `git clone --depth 1` | 1.17 s | 1.37 s | telemetry (network variance) |
| `venv` + `pip install -e .` (cold cache) | 7.18 s | 4.83 s | telemetry |
| `venv` + `pip install -e .` (warm cache) | 6.59 s | 4.60 s | telemetry |
| **after install: `cost-router hero --json`** | **0.12 s** | **0.12 s** | **the product-promise stage** |

- **The post-install stage is the product promise** — under **one second** from a
  finished install to a result. It doesn't depend on the network, so it's
  deterministic.
- clone and install vary widely with the public network and the runner, so we set no
  separate threshold and record them **as telemetry only**. Both cold and warm are in
  the table above.
- The post-install figure was 0.12 s at both the minimum and the median across three
  runs (0.18 s on the first run).

!!! note "Measurement environment (metadata)"
    - **OS**: `Linux-3.10.102-x86_64-with-glibc2.35` (Ubuntu 22.04.5 LTS), `x86_64`, 8 vCPU
    - **Interpreters**: CPython **3.11.15**, **3.12.13** (uv-distributed builds)
    - **Cache**: cold = `pip install --no-cache-dir`, warm = reuse of a shared pip cache
    - **Network**: `--depth 1` public clone from GitHub (0 Azure calls)
    - **Command**: `cost-router hero --json` (offline deterministic projection, `measured = false`)

!!! warning "What these numbers are"
    The per-second figures above are **observed targets** until repeated measurements
    accumulate across the supported interpreters. They are neither a guaranteed
    performance metric (p95) nor a service-level promise (SLA). We also do not call
    this offline path **"10 minutes"** — the 10-minute figure applies only to the
    credentialed legacy-Foundry path.

## Dev verification gates (optional)

```bash
make check     # shell syntax · python compile · secret scan · pytest · ruff
make test      # pytest
make lint      # ruff check .
```

## Next steps

- Why route this way → [Core concepts](concept.md)
- What commands exist → [CLI reference](cli.md)
- Build your own experiment → [Experiment config (YAML)](experiments.md)
