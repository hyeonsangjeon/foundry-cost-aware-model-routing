"""Named offline experiments: reproducible workload + policy + pricing scenarios.

An *experiment* is a small YAML file under ``experiments/`` that pins a workload,
its offline check signals (a curated fixture or deterministic synthesis), a
pricing table, and a policy, plus a **reproducibility contract** (``expect``)
that a run must satisfy. This is what makes the repo's "install and it just
works" promise checkable: running an experiment re-derives the naive-vs-routed
before/after and fails loudly if the offline projection ever drifts below the
contracted floor.

Everything is offline and deterministic; every number carries
``labels.measured = false`` — these are projections over synthetic data, not
measured savings.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .pipeline import (
    DEFAULT_PRICING,
    DEFAULT_SIGNALS,
    DEFAULT_WORKLOAD,
    ReplayReport,
    find_samples_root,
    run_replay,
)
from .pricing import PricingTable
from .spotlight import Spotlight, select_spotlight

EXPERIMENTS_DIRNAME = "experiments"


@dataclass(frozen=True)
class Expectation:
    """Reproducibility floor an experiment run must clear to be considered green."""

    min_coverage: float = 0.0
    min_delta_pct: float = 0.0
    min_tasks: int = 1
    max_delta_pct: float | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> Expectation:
        data = data or {}
        raw_max = data.get("max_delta_pct")
        return cls(
            min_coverage=float(data.get("min_coverage", 0.0)),
            min_delta_pct=float(data.get("min_delta_pct", 0.0)),
            min_tasks=int(data.get("min_tasks", 1)),
            max_delta_pct=None if raw_max is None else float(raw_max),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_coverage": self.min_coverage,
            "min_delta_pct": self.min_delta_pct,
            "min_tasks": self.min_tasks,
            "max_delta_pct": self.max_delta_pct,
        }


@dataclass(frozen=True)
class Experiment:
    """A named, reproducible offline routing scenario loaded from YAML."""

    name: str
    title: str
    summary: str
    synth: bool
    workload: str | None
    signals: str | None
    policy: str | None
    pricing: str | None
    spotlight: str
    expect: Expectation
    source_path: Path | None = None

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        name: str | None = None,
        source_path: Path | None = None,
    ) -> Experiment:
        if not isinstance(data, Mapping):
            raise ValueError("experiment file must be a YAML mapping")
        resolved_name = str(data.get("name") or name or "").strip()
        if not resolved_name:
            raise ValueError("experiment requires a 'name'")
        dataset = data.get("dataset") or {}
        if not isinstance(dataset, Mapping):
            raise ValueError("experiment 'dataset' must be a mapping")
        return cls(
            name=resolved_name,
            title=str(data.get("title") or resolved_name),
            summary=str(data.get("summary") or ""),
            synth=bool(dataset.get("synth", False)),
            workload=_opt_str(dataset.get("workload")),
            signals=_opt_str(dataset.get("signals")),
            policy=_opt_str(data.get("policy")),
            pricing=_opt_str(data.get("pricing")),
            spotlight=str(data.get("spotlight") or "auto").strip(),
            expect=Expectation.from_dict(data.get("expect")),
            source_path=Path(source_path) if source_path is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "summary": self.summary,
            "dataset": {
                "synth": self.synth,
                "workload": self.workload,
                "signals": self.signals,
            },
            "policy": self.policy,
            "pricing": self.pricing,
            "spotlight": self.spotlight,
            "expect": self.expect.to_dict(),
        }


@dataclass(frozen=True)
class Check:
    """One reproducibility-contract assertion and whether the run cleared it."""

    name: str
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass(frozen=True)
class ExperimentResult:
    """A completed experiment run: the replay report, spotlight, and contract."""

    experiment: Experiment
    report: ReplayReport
    spotlight: Spotlight | None
    checks: tuple[Check, ...]

    @property
    def summary(self) -> dict[str, Any]:
        return self.report.summary

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment": self.experiment.to_dict(),
            "summary": self.report.summary,
            "spotlight": self.spotlight.to_dict() if self.spotlight else None,
            "checks": [check.to_dict() for check in self.checks],
            "ok": self.ok,
        }


def experiments_dir(root: Path | str | None = None) -> Path:
    """Return the ``experiments/`` directory at the resolved samples root."""

    return find_samples_root(root) / EXPERIMENTS_DIRNAME


def list_experiments(root: Path | str | None = None) -> list[Experiment]:
    """Load every ``*.yaml`` experiment, sorted by name."""

    directory = experiments_dir(root)
    if not directory.is_dir():
        return []
    experiments = [
        _load_file(path)
        for path in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
    ]
    return sorted(experiments, key=lambda experiment: experiment.name)


def load_experiment(name_or_path: str | Path, root: Path | str | None = None) -> Experiment:
    """Load an experiment by bare name (``hero``) or explicit YAML path."""

    candidate = Path(name_or_path)
    if candidate.suffix in {".yaml", ".yml"} or candidate.exists():
        return _load_file(candidate)
    directory = experiments_dir(root)
    for suffix in (".yaml", ".yml"):
        path = directory / f"{name_or_path}{suffix}"
        if path.is_file():
            return _load_file(path)
    known = ", ".join(experiment.name for experiment in list_experiments(root)) or "(none)"
    raise ValueError(f"unknown experiment {name_or_path!r}; available: {known}")


def run_experiment(
    experiment: Experiment,
    *,
    root: Path | str | None = None,
    ledger_path: Path | str | None = None,
) -> ExperimentResult:
    """Run an experiment's replay and evaluate its reproducibility contract."""

    base = find_samples_root(root)
    workload_path = _resolve(experiment.workload, base, DEFAULT_WORKLOAD)
    pricing_path = _resolve(experiment.pricing, base, DEFAULT_PRICING)
    signals_path = None if experiment.synth else _resolve(experiment.signals, base, DEFAULT_SIGNALS)
    policy_path = _resolve(experiment.policy, base, None) if experiment.policy else None

    report = run_replay(
        workload_path=workload_path,
        pricing_path=pricing_path,
        signals_path=signals_path,
        synth=experiment.synth,
        policy_path=policy_path,
        ledger_path=ledger_path,
    )
    pricing = PricingTable.from_yaml(pricing_path)
    spotlight = select_spotlight(report.traces, pricing, experiment.spotlight)
    checks = _evaluate(report, experiment.expect)
    return ExperimentResult(
        experiment=experiment,
        report=report,
        spotlight=spotlight,
        checks=checks,
    )


def format_experiment_text(result: ExperimentResult) -> str:
    """Render an experiment run as a punchy before/after + spotlight + contract."""

    experiment = result.experiment
    summary = result.report.summary
    lines = [f"experiment: {experiment.name} — {experiment.title}"]
    if experiment.summary:
        lines.append(experiment.summary)
    lines.extend(_before_after_lines(summary))

    spotlight = result.spotlight
    if spotlight is not None:
        lines.append("")
        lines.append(
            f"spotlight  {spotlight.task_id} · {spotlight.task_class} · {spotlight.reason}"
        )
        lines.append(f"  routed  {spotlight.chosen_model:<14} ${spotlight.routed_usd:.6f}")
        lines.append(
            f"  naive   {spotlight.naive_model:<14} ${spotlight.naive_usd:.6f}"
            f"   ({spotlight.ratio:.1f}x more)"
        )

    lines.append("")
    lines.append(f"reproducibility  {'PASS' if result.ok else 'FAIL'}")
    for check in result.checks:
        lines.append(f"  {'PASS' if check.ok else 'FAIL'}  {check.name}: {check.detail}")

    ledger = summary.get("ledger")
    if ledger:
        lines.append("")
        lines.append(
            f"ledger  path={ledger['path']} appended={ledger['appended']} "
            f"matched={ledger['matched']}/{ledger['records']} "
            f"status={'PASS' if ledger['ok'] else 'FAIL'}"
        )
    return "\n".join(lines)


def format_experiment_list(experiments: list[Experiment]) -> str:
    """Render the available experiments as a compact aligned table."""

    if not experiments:
        return "no experiments found under experiments/"
    width = max(len(experiment.name) for experiment in experiments)
    lines = ["experiments:"]
    for experiment in experiments:
        source = "synth" if experiment.synth else "fixture"
        lines.append(f"  {experiment.name:<{width}}  [{source}]  {experiment.title}")
    return "\n".join(lines)


def _before_after_lines(summary: Mapping[str, Any]) -> list[str]:
    if "baseline_total_usd" not in summary:
        return []
    baseline = float(summary["baseline_total_usd"])
    routed = float(summary["total_cost_usd"])
    delta = float(summary.get("delta_usd", baseline - routed))
    delta_pct = float(summary.get("delta_pct", 0.0))
    coverage = float(summary.get("coverage", 0.0))
    return [
        "",
        "before / after  (offline projection over synthetic data; labels.measured=false)",
        f"  BEFORE  naive: premium model on every task   ${baseline:.6f}",
        f"  AFTER   cost-aware routing                   ${routed:.6f}",
        f"  SAVED   ${delta:.6f}  ({delta_pct:.1%} lower)  at {coverage:.1%} coverage",
    ]


def _evaluate(report: ReplayReport, expect: Expectation) -> tuple[Check, ...]:
    summary = report.summary
    coverage = float(summary.get("coverage", 0.0))
    delta_pct = float(summary.get("delta_pct", 0.0))
    tasks = int(summary.get("tasks", 0))
    checks = [
        Check(
            name="coverage",
            ok=coverage >= expect.min_coverage,
            detail=f"{coverage:.1%} ≥ {expect.min_coverage:.1%}",
        ),
        Check(
            name="savings",
            ok=delta_pct >= expect.min_delta_pct,
            detail=f"{delta_pct:.1%} ≥ {expect.min_delta_pct:.1%}",
        ),
        Check(
            name="tasks",
            ok=tasks >= expect.min_tasks,
            detail=f"{tasks} ≥ {expect.min_tasks}",
        ),
    ]
    if expect.max_delta_pct is not None:
        checks.append(
            Check(
                name="savings_ceiling",
                ok=delta_pct <= expect.max_delta_pct,
                detail=f"{delta_pct:.1%} ≤ {expect.max_delta_pct:.1%}",
            )
        )
    return tuple(checks)


def _load_file(path: Path) -> Experiment:
    resolved = Path(path)
    if not resolved.is_file():
        raise ValueError(f"experiment file not found: {resolved}")
    data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    return Experiment.from_dict(data, name=resolved.stem, source_path=resolved)


def _resolve(value: str | None, base: Path, default: Path | None) -> Path | None:
    if value:
        candidate = Path(value)
        return candidate if candidate.is_absolute() else base / candidate
    if default is None:
        return None
    return base / default


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
