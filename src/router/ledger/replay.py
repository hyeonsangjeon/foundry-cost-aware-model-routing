"""Re-run recorded selection decisions and compare canonical final payloads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from policy import Candidate

from ..budget import BudgetGate
from ..pricing import PricingTable, TokenRates
from ..profile import profile_task
from ..select import SelectionResult, compare_select, is_clean, ordered_select
from .record import (
    LedgerRecord,
    canonical_json,
    record_completeness,
    selection_final,
    stable_hash,
)
from .store import JsonlLedger


@dataclass(frozen=True)
class LedgerReplayReport:
    """Verification result for a sequence of ledger records."""

    records: int
    matched: int
    completeness: float
    mismatches: tuple[dict[str, Any], ...]

    @property
    def ok(self) -> bool:
        return self.records > 0 and self.matched == self.records and self.completeness >= 0.99

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": self.records,
            "matched": self.matched,
            "completeness": self.completeness,
            "mismatches": list(self.mismatches),
            "ok": self.ok,
        }


def replay_final(record: LedgerRecord) -> dict[str, Any]:
    """Re-run one recorded ordered/compare selection from raw candidates."""

    selection, _ = _replay_selection(record)
    return selection_final(selection)


def _replay_selection(
    record: LedgerRecord,
) -> tuple[SelectionResult, tuple[Candidate, ...]]:
    record.validate()
    candidates = tuple(
        Candidate(
            model=str(item["model"]),
            prior_pass=float(item["prior_pass"]),
            prior_usd_resolved=float(item["prior_usd_resolved"]),
        )
        for item in record.raw_candidates
    )
    signals = {
        str(item["model"]): dict(item["signals"]) for item in record.raw_candidates
    }
    method = str(record.aggregation["method"])
    if method == "ordered":
        selection = ordered_select(candidates, signals)
    elif method == "compare":
        selection = compare_select(candidates, signals)
    else:
        raise ValueError(f"unsupported ledger aggregation method {method!r}")
    return selection, candidates


def verify_records(records: list[LedgerRecord]) -> LedgerReplayReport:
    """Verify every record's final payload and required-field completeness."""

    mismatches: list[dict[str, Any]] = []
    completeness_total = 0.0
    for record in records:
        completeness_total += record_completeness(record)
        selection, candidates = _replay_selection(record)
        actual = selection_final(selection)
        issues = _audit_issues(record, selection, candidates, actual)
        if issues:
            mismatches.append(
                {
                    "request_hash": record.request_hash,
                    "expected": record.final,
                    "actual": actual,
                    "issues": issues,
                }
            )
    count = len(records)
    return LedgerReplayReport(
        records=count,
        matched=count - len(mismatches),
        completeness=(completeness_total / count) if count else 0.0,
        mismatches=tuple(mismatches),
    )


def verify_ledger(path: Path | str) -> LedgerReplayReport:
    return verify_records(JsonlLedger(path).read_all())


def require_valid_records(records: list[LedgerRecord]) -> None:
    """Raise when records fail replay/completeness; suitable for locked appends."""

    if not records:
        return
    report = verify_records(records)
    if not report.ok:
        raise ValueError(
            f"ledger verification failed: {report.matched}/{report.records} decisions matched"
        )


def _audit_issues(
    record: LedgerRecord,
    selection: SelectionResult,
    candidates: tuple[Candidate, ...],
    actual_final: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    _compare("final", record.final, actual_final, issues)

    expected_order = [candidate.model for candidate in candidates]
    _compare("aggregation.method", record.aggregation.get("method"), selection.mode, issues)
    _compare(
        "aggregation.candidate_order",
        record.aggregation.get("candidate_order"),
        expected_order,
        issues,
    )
    _compare("aggregation.tie_break", record.aggregation.get("tie_break"), "policy-order", issues)

    inspected = {attempt.model for attempt in selection.attempts}
    for rank, raw in enumerate(record.raw_candidates):
        prefix = f"raw_candidates[{rank}]"
        _compare(f"{prefix}.rank", raw.get("rank"), rank, issues)
        _compare(f"{prefix}.model", raw.get("model"), candidates[rank].model, issues)
        _compare(
            f"{prefix}.accepted",
            raw.get("accepted"),
            is_clean(raw.get("signals") or {}),
            issues,
        )
        _compare(
            f"{prefix}.signal_inspected",
            raw.get("signal_inspected"),
            candidates[rank].model in inspected,
            issues,
        )

    gate_config = record.gate_decision["config"]
    budget = BudgetGate(
        compare_min_value=float(gate_config["compare_min_value"]),
        min_compare_candidates=int(gate_config["min_compare_candidates"]),
    ).decide(record.task, candidates)
    expected_gate = {
        "selection_mode": budget.selection_mode,
        "value": budget.value,
        "reason": budget.reason,
        "gate_version": "budget-gate-v1",
        "config": dict(gate_config),
    }
    _compare("gate_decision", record.gate_decision, expected_gate, issues)

    profile = profile_task(record.task)
    _compare("task.class", record.task.get("class"), profile.task_class.value, issues)
    _compare("task.difficulty", record.task.get("difficulty"), profile.difficulty, issues)
    _compare("task.risk", record.task.get("risk"), profile.risk, issues)
    _compare(
        "request_hash",
        record.request_hash,
        stable_hash({"task": record.task}),
        issues,
    )

    expected_policy = {
        "version": record.policy_version,
        "class": profile.task_class.value,
        "candidates": [
            {
                "model": candidate.model,
                "prior_pass": candidate.prior_pass,
                "prior_usd_resolved": candidate.prior_usd_resolved,
            }
            for candidate in candidates
        ],
    }
    _compare("policy_snapshot", record.policy_snapshot, expected_policy, issues)
    _compare("policy_hash", record.policy_hash, stable_hash(record.policy_snapshot), issues)

    pricing = _pricing_from_snapshot(record)
    _compare("pricing_version", record.pricing_version, pricing.version, issues)
    _compare("pricing_hash", record.pricing_hash, stable_hash(record.pricing_snapshot), issues)
    _compare("cost.currency", record.cost.get("currency"), pricing.currency, issues)
    for rank, candidate in enumerate(candidates):
        expected_cost = pricing.cost_usd(candidate.model, record.task.get("tokens", {}))
        _compare(
            f"raw_candidates[{rank}].signals.cost_usd",
            record.raw_candidates[rank]["signals"].get("cost_usd"),
            expected_cost,
            issues,
        )

    chosen = actual_final["chosen_model"]
    for index, backend in enumerate(record.backends):
        _compare(
            f"backends[{index}].selected_model",
            backend.get("selected_model"),
            chosen,
            issues,
        )

    routed_usd = float(actual_final["cost_usd"] or 0.0)
    cost_arm_usd = float(record.raw_candidates[0]["signals"].get("cost_usd") or 0.0)
    quality_arm_usd = float(record.raw_candidates[-1]["signals"].get("cost_usd") or 0.0)
    expected_multiplier = round(routed_usd / cost_arm_usd, 6) if cost_arm_usd else 0.0
    _compare("cost.total_usd", record.cost.get("total_usd"), round(routed_usd, 6), issues)
    _compare("cost.routed_usd", record.cost.get("routed_usd"), round(routed_usd, 6), issues)
    _compare("cost.cost_arm_usd", record.cost.get("cost_arm_usd"), cost_arm_usd, issues)
    _compare("cost.quality_arm_usd", record.cost.get("quality_arm_usd"), quality_arm_usd, issues)
    _compare(
        "cost.multiplier_vs_cost_arm",
        record.cost.get("multiplier_vs_cost_arm"),
        expected_multiplier,
        issues,
    )
    _compare(
        "cost.billing_basis",
        record.cost.get("billing_basis"),
        "selected-execution-only",
        issues,
    )
    _compare("cost.signals_precomputed", record.cost.get("signals_precomputed"), True, issues)
    _compare("labels", record.labels, {"measured": False, "offline": True}, issues)
    return issues


def _compare(name: str, actual: Any, expected: Any, issues: list[str]) -> None:
    if canonical_json(actual) != canonical_json(expected):
        issues.append(name)


def _pricing_from_snapshot(record: LedgerRecord) -> PricingTable:
    snapshot = record.pricing_snapshot
    try:
        return PricingTable(
            version=int(snapshot["version"]),
            currency=str(snapshot["currency"]),
            default=TokenRates.from_dict(snapshot["default"]),
            models={
                str(model): TokenRates.from_dict(rates)
                for model, rates in snapshot["models"].items()
            },
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"malformed ledger pricing_snapshot: {exc}") from exc
