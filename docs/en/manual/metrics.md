# Metrics & Azure Foundry

`src/router/metrics.py` is the single place that turns one experiment run into a
**normalized metrics record**. The CLI, the HTTP service, and the dashboard all share
this **common class**, so per-experiment statistics and the historical dashboard never
recompute the numbers by hand.

!!! note "It keeps the repository's promises intact"
    - **Offline and deterministic** — extraction is a pure function. The same
      `ExperimentResult` yields the same `ExperimentMetrics` (including a content-addressed
      `run_id`). Nothing touches the network.
    - **`measured = false`** — these are projections over synthetic data, not measured
      Azure spend.
    - **Foundry-ready, not Foundry-coupled** — records render in the shape of Azure Monitor
      / OpenTelemetry metrics, but the actual send happens only through an **injected sink**.

## Core components

| Name | Role |
| --- | --- |
| `fanout_stats(traces)` | Recovers the **ensemble fan-out tax** from compare (ensemble) traces (`fanout_usd` · `winner_usd` · `ensemble_tax_usd` · `tax_ratio`) |
| `ExperimentMetrics` | Normalized snapshot of a single run (immutable dataclass) — cost, pass rate (the `coverage` field), fan-out tax, plus `run_id` |
| `ExperimentMetrics.to_metric_records()` | Renders a list of Azure Monitor / OTel metric data points |
| `extract_experiment_metrics(result)` | `ExperimentResult` → `ExperimentMetrics` (pure and deterministic) |
| `JsonlMetricsStore` | Append-only JSONL history store (`record` · `history` · `latest_per_experiment`) |
| `FoundryMetricsEmitter` | Connection-string-aware Foundry emitter (offline capture + injected sink) |
| `record_experiment_metrics(...)` | Common entry point that extracts a run and fans it out to the store and emitter |

## Ensemble fan-out tax

Cost-aware routing fans out to every candidate in compare mode **only on high-value
tasks**, and bills only the winning model. A trace's `cost_usd` records the winner alone,
so the fan-out cost stays hidden. `fanout_stats` recovers that hidden cost.

```python
from router.metrics import fanout_stats

stats = fanout_stats(report.traces)
# {'ensemble_tasks': 6, 'fanout_usd': 0.496812, 'winner_usd': 0.132801,
#  'ensemble_tax_usd': 0.364011, 'tax_ratio': 3.741, ...}
```

`ensemble_tax_usd = fanout_usd − winner_usd` is **what the losing models cost to run**.
For the full experiment, see
[Experiment 05 · Ensemble fan-out tax](../lab-notebook/05-ensemble-fanout.md). The canonical
source for the offline headline figure (3.74×) is [Offline experiment results](projection-results.md).

## Exporting in Azure Foundry shape

```bash
cost-router metrics emit ensemble
# offline: "local capture (offline)" — no network send
```

With a connection string present, the emitter reports `configured = True` (even so, the
default path sends nothing and only captures locally — the actual send belongs to the
injected sink):

```bash
export AZURE_AI_FOUNDRY_CONNECTION_STRING="InstrumentationKey=...;IngestionEndpoint=https://..."
cost-router metrics emit ensemble --connection-string "$AZURE_AI_FOUNDRY_CONNECTION_STRING"
# "Azure Foundry (configured)" — still an offline capture. The send happens only when a sink is injected.
```

Each record has the shape of an Azure Monitor customMetric / OTel data point:

```json
{
  "name": "router.ensemble.tax_usd",
  "value": 0.364011,
  "unit": "USD",
  "timestamp": "2026-01-01T00:00:00Z",
  "dimensions": {
    "experiment": "ensemble", "source": "fixture",
    "run_id": "38fb40ba53080601", "measured": "false",
    "policy": "seed", "pricing": "illustrative"
  }
}
```

## Storing and reading history (the historical dashboard)

Record metrics into the history store as you run experiments, and the dashboard's
**Historical dashboard** panel and the `metrics history` command read that history.

```bash
cost-router experiment run ensemble --metrics-store runs.jsonl
cost-router hero --metrics-store runs.jsonl
cost-router metrics history --store runs.jsonl
cost-router metrics history --store runs.jsonl --experiment ensemble --json
```

The live service can use the same store:

```python
from router.metrics import JsonlMetricsStore
from router.server import RouterService, serve

service = RouterService(metrics_store=JsonlMetricsStore("runs.jsonl"))
# Every call to GET /experiment?name=ensemble appends one line to the history.
```

!!! tip "Separating the deterministic from the live"
    `GET /experiments` and the static `experiments.json` are **pure projections**, so
    `recorded_at` is `null` and they always return the same values. `GET /experiment?name=`
    is **real-time behavior**: it stamps the current time and adds one line to the history.
    That way the static demo stays reproducible while the live server's history grows with
    activity.

## Injecting the Foundry sink (the one place a send actually happens)

```python
from router.metrics import FoundryMetricsEmitter, extract_experiment_metrics

def push_to_foundry(records):
    ...  # the real send, e.g. an Azure Monitor exporter (implement in your deployment)

emitter = FoundryMetricsEmitter(
    connection_string="InstrumentationKey=...",
    sink=push_to_foundry,   # the send happens only through this injected sink
)
emitter.emit(extract_experiment_metrics(result))
```

Without an injected sink, records only accumulate in `emitter.captured` — fully offline and
test-safe.

!!! tip "Up to here it's `measured = false` — to cross into measurement"
    Every metric on this page is a projection over synthetic data. To get **measured spend**
    (`measured = true`) from the real token usage of Azure Model Router, see the
    [live measured bridge](foundry-live.md).
