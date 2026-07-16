"""Provider-neutral, Azure AI Foundry-shaped metrics for routing experiments.

This module is the single place where an experiment run is turned into a
normalized **metrics record** — the "common class" every consumer (the CLI, the
HTTP service, the dashboard) shares so per-experiment statistics and the
historical dashboard never re-derive numbers by hand.

Design constraints (the repo's promise):

* **Offline and deterministic.** Extraction is pure: the same
  :class:`~router.experiment.ExperimentResult` yields the same
  :class:`ExperimentMetrics` (including a content-addressed ``run_id``). Nothing
  here touches the network.
* **``measured = false`` everywhere.** These are projections over synthetic
  data, not measured Azure spend.
* **Foundry-ready, not Foundry-coupled.** :meth:`ExperimentMetrics.to_metric_records`
  emits the exact Azure Monitor / OpenTelemetry metric shape you would push to
  Azure AI Foundry observability. :class:`FoundryMetricsEmitter` captures that
  payload locally and only *forwards* it through an injected sink — so a real
  connection string is the single seam where egress would happen, and the
  default path stays pure-stdlib and test-safe.

The honest headline this unlocks is the **ensemble fan-out tax**: cost-aware
routing only fans out (compare mode) to every candidate on the high-value tasks,
but a naive "ensemble everything" strategy pays to run *all* models on *every*
task. :func:`fanout_stats` recovers that hidden cost from the traces.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .experiment import ExperimentResult

SCHEMA_VERSION = 1

# Azure AI Foundry / Azure Monitor connection-string environment variables. When
# either is set the emitter reports ``configured = True``; egress itself is left
# to an injected sink so this module never requires the network.
FOUNDRY_ENV_VARS = (
    "AZURE_AI_FOUNDRY_CONNECTION_STRING",
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
)


def _round(value: float, places: int = 6) -> float:
    return round(float(value), places)


def _attempt_cost(attempt: Mapping[str, Any]) -> float:
    signals = attempt.get("signals") or {}
    value = signals.get("cost_usd")
    return float(value) if isinstance(value, int | float) else 0.0


def fanout_stats(traces: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Recover the ensemble fan-out cost from routed traces.

    In *compare* (ensemble) mode the router evaluates every candidate — a real
    fan-out that runs each model — but only charges the winner. This function
    sums what the fan-out actually costs (every attempted candidate) versus what
    routing keeps (the winner), exposing the **ensemble tax**: the price of
    running the losers. *ordered* (single-route) tasks never fan out and are
    reported only as a count.

    All figures are offline projections over synthetic data (``measured=false``).
    """

    ensemble_tasks = 0
    single_tasks = 0
    fanout_candidates = 0
    fanout_usd = 0.0
    winner_usd = 0.0
    for trace in traces:
        if str(trace.get("mode")) != "compare":
            single_tasks += 1
            continue
        attempts = trace.get("attempts") or []
        ensemble_tasks += 1
        fanout_candidates += len(attempts)
        fanout_usd += sum(_attempt_cost(attempt) for attempt in attempts)
        chosen = trace.get("chosen")
        for attempt in attempts:
            if attempt.get("model") == chosen:
                winner_usd += _attempt_cost(attempt)
                break
    tax = fanout_usd - winner_usd
    return {
        "ensemble_tasks": ensemble_tasks,
        "single_tasks": single_tasks,
        "fanout_candidates": fanout_candidates,
        "fanout_usd": _round(fanout_usd),
        "winner_usd": _round(winner_usd),
        "ensemble_tax_usd": _round(tax),
        "tax_ratio": _round(fanout_usd / winner_usd, 4) if winner_usd else 0.0,
    }


@dataclass(frozen=True)
class ExperimentMetrics:
    """A normalized, Foundry-shaped snapshot of one experiment run.

    Every numeric field is an offline projection over synthetic data. ``run_id``
    is content-addressed (a hash of the experiment name and its headline totals)
    so re-running the same experiment yields the same id — deterministic and
    dedup-friendly for the historical store.
    """

    run_id: str
    experiment: str
    title: str
    source: str
    tasks: int
    accepted: int
    coverage: float
    routed_usd: float
    baseline_usd: float
    delta_usd: float
    delta_pct: float
    avg_usd_per_task: float
    ensemble_tasks: int
    single_tasks: int
    fanout_candidates: int
    fanout_usd: float
    ensemble_tax_usd: float
    tax_ratio: float
    spotlight_task: str | None
    spotlight_ratio: float | None
    reproducible: bool
    recorded_at: str | None = None
    measured: bool = False
    schema_version: int = SCHEMA_VERSION
    dimensions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_metric_records(self) -> list[dict[str, Any]]:
        """Render the run as Azure Monitor / OpenTelemetry metric data points.

        This is the payload a Foundry exporter would push: one record per
        numeric metric, each carrying a value, a unit, the run's dimensions
        (Azure ``customDimensions`` / OTel attributes), and the recording time.
        """

        base_dims = {
            "experiment": self.experiment,
            "source": self.source,
            "run_id": self.run_id,
            "measured": str(self.measured).lower(),
            **{str(k): str(v) for k, v in self.dimensions.items()},
        }
        gauges: list[tuple[str, float, str]] = [
            ("router.cost.routed_usd", self.routed_usd, "USD"),
            ("router.cost.baseline_usd", self.baseline_usd, "USD"),
            ("router.cost.delta_usd", self.delta_usd, "USD"),
            ("router.cost.delta_pct", self.delta_pct, "ratio"),
            ("router.cost.avg_usd_per_task", self.avg_usd_per_task, "USD"),
            ("router.quality.coverage", self.coverage, "ratio"),
            ("router.workload.tasks", float(self.tasks), "count"),
            ("router.workload.accepted", float(self.accepted), "count"),
            ("router.ensemble.tasks", float(self.ensemble_tasks), "count"),
            ("router.ensemble.single_tasks", float(self.single_tasks), "count"),
            ("router.ensemble.fanout_candidates", float(self.fanout_candidates), "count"),
            ("router.ensemble.fanout_usd", self.fanout_usd, "USD"),
            ("router.ensemble.tax_usd", self.ensemble_tax_usd, "USD"),
            ("router.ensemble.tax_ratio", self.tax_ratio, "ratio"),
            ("router.contract.reproducible", 1.0 if self.reproducible else 0.0, "bool"),
        ]
        return [
            {
                "name": name,
                "value": value,
                "unit": unit,
                "timestamp": self.recorded_at,
                "dimensions": dict(base_dims),
            }
            for name, value, unit in gauges
        ]


def _content_run_id(name: str, summary: Mapping[str, Any]) -> str:
    parts = "|".join(
        str(part)
        for part in (
            name,
            summary.get("tasks"),
            summary.get("coverage"),
            _round(float(summary.get("total_cost_usd", 0.0))),
            _round(float(summary.get("baseline_total_usd", 0.0))),
        )
    )
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()[:16]


def extract_experiment_metrics(
    result: ExperimentResult,
    *,
    run_id: str | None = None,
    recorded_at: str | None = None,
    dimensions: Mapping[str, str] | None = None,
) -> ExperimentMetrics:
    """Derive a normalized :class:`ExperimentMetrics` from an experiment run.

    Pure and deterministic: no clock, no network. The caller supplies
    ``recorded_at`` when a wall-clock timestamp is wanted (the historical store)
    and leaves it ``None`` for reproducible fixtures.
    """

    experiment = result.experiment
    summary = result.report.summary
    tasks = int(summary.get("tasks", 0))
    routed = _round(float(summary.get("total_cost_usd", 0.0)))
    baseline = _round(float(summary.get("baseline_total_usd", routed)))
    delta = _round(float(summary.get("delta_usd", baseline - routed)))
    fan = fanout_stats(result.report.traces)
    spotlight = result.spotlight
    source = "synth" if experiment.synth else "fixture"
    dims = {
        "policy": experiment.policy or "seed",
        "pricing": experiment.pricing or "illustrative",
        **{str(k): str(v) for k, v in (dimensions or {}).items()},
    }
    return ExperimentMetrics(
        run_id=run_id or _content_run_id(experiment.name, summary),
        experiment=experiment.name,
        title=experiment.title,
        source=source,
        tasks=tasks,
        accepted=int(summary.get("accepted", 0)),
        coverage=_round(float(summary.get("coverage", 0.0)), 4),
        routed_usd=routed,
        baseline_usd=baseline,
        delta_usd=delta,
        delta_pct=_round(float(summary.get("delta_pct", 0.0)), 4),
        avg_usd_per_task=_round(routed / tasks) if tasks else 0.0,
        ensemble_tasks=int(fan["ensemble_tasks"]),
        single_tasks=int(fan["single_tasks"]),
        fanout_candidates=int(fan["fanout_candidates"]),
        fanout_usd=fan["fanout_usd"],
        ensemble_tax_usd=fan["ensemble_tax_usd"],
        tax_ratio=fan["tax_ratio"],
        spotlight_task=spotlight.task_id if spotlight else None,
        spotlight_ratio=_round(spotlight.ratio, 2) if spotlight else None,
        reproducible=bool(result.ok),
        recorded_at=recorded_at,
        dimensions=dims,
    )


@runtime_checkable
class MetricSink(Protocol):
    """Anything that can accept an :class:`ExperimentMetrics` snapshot."""

    def emit(self, metrics: ExperimentMetrics) -> Any:  # pragma: no cover - protocol
        ...


class JsonlMetricsStore:
    """Append-only newline-delimited JSON store for experiment metrics history.

    A deliberately small local store (no hash chain, unlike the audit ledger):
    each recorded run is one JSON line, and :meth:`history` reads them back for
    the historical dashboard. Offline and deterministic given its inputs.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def emit(self, metrics: ExperimentMetrics) -> ExperimentMetrics:
        """:class:`MetricSink` entry point — records and returns the snapshot."""

        return self.record(metrics)

    def record(self, metrics: ExperimentMetrics) -> ExperimentMetrics:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(metrics.to_dict(), ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as handle:
            _lock(handle)
            try:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            finally:
                _unlock(handle)
        return metrics

    def history(
        self,
        *,
        experiment: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return recorded runs oldest-first, optionally filtered and tail-limited."""

        rows = self._read_all()
        if experiment is not None:
            rows = [row for row in rows if row.get("experiment") == experiment]
        if limit is not None and limit >= 0:
            rows = rows[-limit:]
        return rows

    def latest_per_experiment(self) -> dict[str, dict[str, Any]]:
        """Map each experiment to its most recently recorded run."""

        latest: dict[str, dict[str, Any]] = {}
        for row in self._read_all():
            name = str(row.get("experiment"))
            latest[name] = row
        return latest

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as handle:
            _lock(handle, exclusive=False)
            try:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        raise ValueError(
                            f"invalid metrics JSON at {self.path}:{line_number}: {exc.msg}"
                        ) from exc
            finally:
                _unlock(handle)
        return rows


class FoundryMetricsEmitter:
    """Azure AI Foundry-shaped metrics emitter (offline by default).

    Renders each run into Azure Monitor / OpenTelemetry metric records and
    captures them locally. When a connection string is present (``configured``)
    a real deployment would forward these to Foundry observability; here that
    forwarding is an **injected** ``sink`` callable, so the default path never
    egresses and stays test-safe. Nothing is measured — ``measured=false``.
    """

    def __init__(
        self,
        *,
        connection_string: str | None = None,
        env: Mapping[str, str] | None = None,
        sink: Any = None,
    ) -> None:
        environ = env if env is not None else os.environ
        self.connection_string = connection_string or _first_env(environ, FOUNDRY_ENV_VARS)
        self.sink = sink
        self.captured: list[dict[str, Any]] = []

    @property
    def configured(self) -> bool:
        """True when an Azure Foundry / Application Insights connection is set."""

        return bool(self.connection_string)

    def emit(self, metrics: ExperimentMetrics) -> list[dict[str, Any]]:
        records = metrics.to_metric_records()
        self.captured.extend(records)
        if self.sink is not None:
            self.sink(records)
        return records


def record_experiment_metrics(
    result: ExperimentResult,
    *,
    store: JsonlMetricsStore | None = None,
    emitter: FoundryMetricsEmitter | None = None,
    sinks: Iterable[MetricSink] | None = None,
    run_id: str | None = None,
    recorded_at: str | None = None,
    dimensions: Mapping[str, str] | None = None,
) -> ExperimentMetrics:
    """Extract metrics for an experiment run and fan them out to every sink.

    The shared entry point used by the CLI and the HTTP service: it stamps the
    recording time (real UTC now unless ``recorded_at`` is supplied), persists to
    the historical ``store``, forwards to the Foundry ``emitter``, and returns
    the snapshot. Any additional :class:`MetricSink` may be passed via ``sinks``.
    """

    if recorded_at is None:
        recorded_at = utc_now_iso()
    metrics = extract_experiment_metrics(
        result, run_id=run_id, recorded_at=recorded_at, dimensions=dimensions
    )
    if store is not None:
        store.record(metrics)
    if emitter is not None:
        emitter.emit(metrics)
    for sink in sinks or ():
        sink.emit(metrics)
    return metrics


def utc_now_iso() -> str:
    """Return the current UTC time as a compact ISO-8601 ``…Z`` string."""

    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _first_env(env: Mapping[str, str], names: Sequence[str]) -> str | None:
    for name in names:
        value = env.get(name)
        if value:
            return value
    return None


def _lock(handle: Any, *, exclusive: bool = True) -> None:
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
    except (ImportError, OSError):  # pragma: no cover - non-POSIX / unsupported fs
        pass


def _unlock(handle: Any) -> None:
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except (ImportError, OSError):  # pragma: no cover - non-POSIX / unsupported fs
        pass
