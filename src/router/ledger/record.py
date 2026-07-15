"""Ledger record schema, canonical hashing, and routing-record construction."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields, replace
from typing import Any

from policy import PolicyTable, TaskClass

from ..budget import BudgetGate
from ..pricing import PricingTable
from ..profile import profile_task
from ..select import SelectionResult, is_clean

LEDGER_SCHEMA_VERSION = 1

_REQUIRED_PATHS = (
    ("schema_version",),
    ("request_hash",),
    ("policy_version",),
    ("policy_hash",),
    ("policy_snapshot",),
    ("pricing_version",),
    ("pricing_hash",),
    ("pricing_snapshot",),
    ("signal_kind",),
    ("record_hash",),
    ("task", "task_id"),
    ("task", "class"),
    ("task", "difficulty"),
    ("task", "risk"),
    ("task", "tokens"),
    ("gate_decision", "selection_mode"),
    ("gate_decision", "value"),
    ("gate_decision", "reason"),
    ("backends",),
    ("raw_candidates",),
    ("aggregation", "method"),
    ("aggregation", "tie_break"),
    ("final", "mode"),
    ("final", "chosen_model"),
    ("final", "reason"),
    ("final", "accepted"),
    ("final", "cost_usd"),
    ("cost", "total_usd"),
    ("cost", "billing_basis"),
    ("cost", "currency"),
    ("cost", "multiplier_vs_cost_arm"),
    ("latency_ms", "total"),
    ("labels", "measured"),
    ("labels", "offline"),
)


@dataclass(frozen=True)
class LedgerRecord:
    """One self-contained, replayable offline routing decision."""

    schema_version: int
    request_hash: str
    policy_version: int
    policy_hash: str
    policy_snapshot: dict[str, Any]
    pricing_version: int
    pricing_hash: str
    pricing_snapshot: dict[str, Any]
    signal_kind: str
    task: dict[str, Any]
    gate_decision: dict[str, Any]
    backends: list[dict[str, Any]]
    raw_candidates: list[dict[str, Any]]
    aggregation: dict[str, Any]
    final: dict[str, Any]
    cost: dict[str, Any]
    latency_ms: dict[str, Any]
    labels: dict[str, Any]
    previous_hash: str | None
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> LedgerRecord:
        if self.schema_version != LEDGER_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported ledger schema version {self.schema_version}; "
                f"expected {LEDGER_SCHEMA_VERSION}"
            )
        if len(self.request_hash) != 64 or any(
            char not in "0123456789abcdef" for char in self.request_hash
        ):
            raise ValueError("ledger request_hash must be a lowercase SHA-256 digest")
        if not _is_digest(self.policy_hash):
            raise ValueError("ledger policy_hash must be a lowercase SHA-256 digest")
        if not _is_digest(self.pricing_hash):
            raise ValueError("ledger pricing_hash must be a lowercase SHA-256 digest")
        _validate_policy_snapshot(self.policy_snapshot, self.policy_version)
        _validate_pricing_snapshot(self.pricing_snapshot, self.pricing_version)
        if self.policy_hash != stable_hash(self.policy_snapshot):
            raise ValueError("ledger policy_hash does not match policy_snapshot")
        if self.pricing_hash != stable_hash(self.pricing_snapshot):
            raise ValueError("ledger pricing_hash does not match pricing_snapshot")
        if self.signal_kind not in {"fixture", "synth"}:
            raise ValueError("ledger signal_kind must be 'fixture' or 'synth'")
        if self.previous_hash is not None and not _is_digest(self.previous_hash):
            raise ValueError("ledger previous_hash must be null or a lowercase SHA-256 digest")
        if not _is_digest(self.record_hash):
            raise ValueError("ledger record_hash must be a lowercase SHA-256 digest")
        if self.record_hash != _record_hash(self):
            raise ValueError("ledger record_hash does not match its canonical payload")
        if not self.raw_candidates:
            raise ValueError("ledger record must contain at least one raw candidate")
        if not self.backends:
            raise ValueError("ledger record must contain at least one backend")
        if len(self.backends) != 1:
            raise ValueError("ledger schema v1 requires exactly one offline backend")
        _validate_backend(self.backends[0], self)
        _validate_task(self.task)
        _validate_gate_decision(self.gate_decision)
        for rank, candidate in enumerate(self.raw_candidates):
            _validate_raw_candidate(candidate, rank)
        _validate_aggregation(self.aggregation, len(self.raw_candidates))
        _validate_final(self.final)
        _validate_cost(self.cost)
        _validate_latency(self.latency_ms)
        if self.labels != {"measured": False, "offline": True}:
            raise ValueError("ledger labels must mark the record offline and unmeasured")
        if record_completeness(self) < 1.0:
            raise ValueError("ledger record is missing required audit fields")
        return self

    def with_previous_hash(self, previous_hash: str | None) -> LedgerRecord:
        """Return this record chained to ``previous_hash`` with a fresh digest."""

        unsealed = replace(self, previous_hash=previous_hash, record_hash="")
        return replace(unsealed, record_hash=_record_hash(unsealed)).validate()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LedgerRecord:
        if not isinstance(data, Mapping):
            raise ValueError("ledger record must be a JSON object")
        allowed = {field.name for field in fields(cls)}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ValueError(f"unknown ledger schema-v1 fields: {', '.join(unknown)}")
        try:
            record = cls(
                schema_version=int(data["schema_version"]),
                request_hash=str(data["request_hash"]),
                policy_version=int(data["policy_version"]),
                policy_hash=str(data["policy_hash"]),
                policy_snapshot=dict(data["policy_snapshot"]),
                pricing_version=int(data["pricing_version"]),
                pricing_hash=str(data["pricing_hash"]),
                pricing_snapshot=dict(data["pricing_snapshot"]),
                signal_kind=str(data["signal_kind"]),
                task=dict(data["task"]),
                gate_decision=dict(data["gate_decision"]),
                backends=[dict(item) for item in data["backends"]],
                raw_candidates=[dict(item) for item in data["raw_candidates"]],
                aggregation=dict(data["aggregation"]),
                final=dict(data["final"]),
                cost=dict(data["cost"]),
                latency_ms=dict(data["latency_ms"]),
                labels=dict(data["labels"]),
                previous_hash=(
                    str(data["previous_hash"]) if data.get("previous_hash") is not None else None
                ),
                record_hash=str(data["record_hash"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"malformed ledger record: {exc}") from exc
        return record.validate()


def build_ledger_record(
    *,
    task: Mapping[str, Any],
    signals_by_model: Mapping[str, Mapping[str, Any]],
    trace: Mapping[str, Any],
    policy: PolicyTable,
    pricing: PricingTable,
    signal_kind: str,
    budget_gate: BudgetGate | None = None,
) -> LedgerRecord:
    """Build a complete ledger record from one routed task and its raw signals."""

    profile = profile_task(task)
    budget_gate = budget_gate or BudgetGate()
    candidates = policy.candidates_for(profile.task_class)
    inspected = {str(item.get("model")) for item in trace.get("attempts", [])}
    raw_candidates = []
    for rank, candidate in enumerate(candidates):
        raw = signals_by_model.get(candidate.model)
        if raw is None:
            raise ValueError(f"missing ledger signals for model {candidate.model!r}")
        signals = dict(raw)
        signals["cost_usd"] = pricing.cost_usd(candidate.model, task.get("tokens", {}))
        raw_candidates.append(
            {
                "model": candidate.model,
                "rank": rank,
                "prior_pass": candidate.prior_pass,
                "prior_usd_resolved": candidate.prior_usd_resolved,
                "signals": signals,
                "accepted": is_clean(signals),
                "signal_inspected": candidate.model in inspected,
            }
        )

    policy_snapshot = _policy_payload(policy, profile.task_class)
    pricing_snapshot = _pricing_payload(pricing, tuple(candidate.model for candidate in candidates))
    policy_hash = stable_hash(policy_snapshot)
    pricing_hash = stable_hash(pricing_snapshot)
    chosen_model = trace.get("chosen")
    final = {
        "mode": str(trace.get("mode")),
        "chosen_model": str(chosen_model) if chosen_model is not None else None,
        "reason": str(trace.get("reason")),
        "accepted": _trace_accepted(trace),
        "cost_usd": trace.get("cost_usd"),
    }
    budget = trace.get("budget") or {}
    cost_arm = candidates[0]
    quality_arm = candidates[-1]
    cost_arm_usd = pricing.cost_usd(cost_arm.model, task.get("tokens", {}))
    total_usd = float(trace.get("cost_usd") or 0.0)
    record = LedgerRecord(
        schema_version=LEDGER_SCHEMA_VERSION,
        request_hash=stable_hash({"task": _task_snapshot(task)}),
        policy_version=policy.version,
        policy_hash=policy_hash,
        policy_snapshot=policy_snapshot,
        pricing_version=pricing.version,
        pricing_hash=pricing_hash,
        pricing_snapshot=pricing_snapshot,
        signal_kind=signal_kind,
        task=_task_snapshot(task),
        gate_decision={
            "selection_mode": str(budget.get("selection_mode") or trace.get("mode")),
            "value": float(budget.get("value") or 0.0),
            "reason": str(budget.get("reason") or "not-recorded"),
            "gate_version": "budget-gate-v1",
            "config": {
                "compare_min_value": budget_gate.compare_min_value,
                "min_compare_candidates": budget_gate.min_compare_candidates,
            },
        },
        backends=[
            {
                "backend_id": "offline-router",
                "deployment_version": f"{signal_kind}-v1",
                "subset_hash": policy_hash,
                "selected_model": final["chosen_model"],
            }
        ],
        raw_candidates=raw_candidates,
        aggregation={
            "method": final["mode"],
            "candidate_order": [candidate.model for candidate in candidates],
            "tie_break": "policy-order",
        },
        final=final,
        cost={
            "total_usd": round(total_usd, 6),
            "routed_usd": round(total_usd, 6),
            "currency": pricing.currency,
            "billing_basis": "selected-execution-only",
            "signals_precomputed": True,
            "cost_arm_usd": cost_arm_usd,
            "quality_arm_usd": pricing.cost_usd(
                quality_arm.model,
                task.get("tokens", {}),
            ),
            "multiplier_vs_cost_arm": (
                round(total_usd / cost_arm_usd, 6) if cost_arm_usd else 0.0
            ),
        },
        latency_ms={"candidate_max": 0, "aggregation": 0, "total": 0},
        labels={"measured": False, "offline": True},
        previous_hash=None,
        record_hash="",
    )
    return record.with_previous_hash(None)


def selection_final(selection: SelectionResult) -> dict[str, Any]:
    """Convert a replayed selection into the canonical ledger final payload."""

    chosen_cost = None
    if selection.chosen_model is not None:
        chosen = next(
            attempt for attempt in selection.attempts if attempt.model == selection.chosen_model
        )
        value = chosen.signals.get("cost_usd")
        chosen_cost = float(value) if isinstance(value, int | float) else None
    return {
        "mode": selection.mode,
        "chosen_model": selection.chosen_model,
        "reason": selection.reason,
        "accepted": selection.accepted,
        "cost_usd": chosen_cost,
    }


def canonical_json(value: Any) -> str:
    """Return a stable JSON representation for hashing and byte comparisons."""

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _record_hash(record: LedgerRecord) -> str:
    payload = record.to_dict()
    payload.pop("record_hash", None)
    return stable_hash(payload)


def _is_digest(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _validate_backend(backend: Mapping[str, Any], record: LedgerRecord) -> None:
    required = {
        "backend_id",
        "deployment_version",
        "subset_hash",
        "selected_model",
    }
    if set(backend) != required:
        raise ValueError("ledger backend must contain the exact schema-v1 fields")
    if backend["backend_id"] != "offline-router":
        raise ValueError("ledger schema v1 backend_id must be 'offline-router'")
    if backend["deployment_version"] != f"{record.signal_kind}-v1":
        raise ValueError("ledger backend deployment_version does not match signal_kind")
    if backend["subset_hash"] != record.policy_hash:
        raise ValueError("ledger backend subset_hash must match policy_hash")


def _validate_policy_snapshot(snapshot: Mapping[str, Any], version: int) -> None:
    if not isinstance(snapshot, Mapping):
        raise ValueError("ledger policy_snapshot must be a mapping")
    if set(snapshot) != {"version", "class", "candidates"}:
        raise ValueError("ledger policy_snapshot must contain exact schema-v1 fields")
    if snapshot["version"] != version:
        raise ValueError("ledger policy_snapshot version does not match policy_version")
    if snapshot["class"] not in {task_class.value for task_class in TaskClass}:
        raise ValueError("ledger policy_snapshot class is invalid")
    candidates = snapshot["candidates"]
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("ledger policy_snapshot candidates must be a non-empty list")
    required = {"model", "prior_pass", "prior_usd_resolved"}
    if any(not isinstance(item, Mapping) or set(item) != required for item in candidates):
        raise ValueError("ledger policy_snapshot candidate shape is invalid")


def _validate_pricing_snapshot(snapshot: Mapping[str, Any], version: int) -> None:
    if not isinstance(snapshot, Mapping):
        raise ValueError("ledger pricing_snapshot must be a mapping")
    if set(snapshot) != {"version", "currency", "default", "models"}:
        raise ValueError("ledger pricing_snapshot must contain exact schema-v1 fields")
    if snapshot["version"] != version:
        raise ValueError("ledger pricing_snapshot version does not match pricing_version")
    if not isinstance(snapshot["currency"], str) or not snapshot["currency"]:
        raise ValueError("ledger pricing_snapshot currency must be a non-empty string")
    rates_fields = {"input", "cached", "output", "reasoning"}
    default = snapshot["default"]
    models = snapshot["models"]
    if not isinstance(default, Mapping) or set(default) != rates_fields:
        raise ValueError("ledger pricing_snapshot default rates are invalid")
    if not isinstance(models, Mapping) or not models:
        raise ValueError("ledger pricing_snapshot models must be a non-empty mapping")
    if any(
        not isinstance(rates, Mapping) or set(rates) != rates_fields
        for rates in models.values()
    ):
        raise ValueError("ledger pricing_snapshot model rates are invalid")


def _validate_task(task: Mapping[str, Any]) -> None:
    required = {"task_id", "class", "difficulty", "risk", "tokens"}
    allowed = {*required, "domain", "diff_size_lines", "value"}
    if not required <= set(task) or not set(task) <= allowed:
        raise ValueError("ledger task has invalid schema-v1 fields")
    if not isinstance(task["task_id"], str) or not task["task_id"]:
        raise ValueError("ledger task_id must be a non-empty string")
    if task["class"] not in {task_class.value for task_class in TaskClass}:
        raise ValueError("ledger task class is invalid")
    if task["difficulty"] not in {"easy", "medium", "hard", "unspecified"}:
        raise ValueError("ledger task difficulty is invalid")
    if task["risk"] not in {"low", "moderate", "high"}:
        raise ValueError("ledger task risk is invalid")
    tokens = task["tokens"]
    if not isinstance(tokens, Mapping):
        raise ValueError("ledger task tokens must be a mapping")
    allowed_tokens = {"input", "cached", "output", "reasoning"}
    if not set(tokens) <= allowed_tokens:
        raise ValueError("ledger task tokens contain unknown fields")
    if any(
        not isinstance(value, int | float) or isinstance(value, bool)
        for value in tokens.values()
    ):
        raise ValueError("ledger task token values must be numeric")


def _validate_gate_decision(gate: Mapping[str, Any]) -> None:
    required = {"selection_mode", "value", "reason", "gate_version", "config"}
    if set(gate) != required:
        raise ValueError("ledger gate_decision must contain exact schema-v1 fields")
    if gate["selection_mode"] not in {"ordered", "compare"}:
        raise ValueError("ledger gate selection_mode is invalid")
    if not isinstance(gate["value"], int | float) or isinstance(gate["value"], bool):
        raise ValueError("ledger gate value must be numeric")
    if not isinstance(gate["reason"], str) or not gate["reason"]:
        raise ValueError("ledger gate reason must be a non-empty string")
    if gate["gate_version"] != "budget-gate-v1":
        raise ValueError("ledger gate_version is unsupported")
    config = gate["config"]
    if not isinstance(config, Mapping) or set(config) != {
        "compare_min_value",
        "min_compare_candidates",
    }:
        raise ValueError("ledger gate config is invalid")
    if not isinstance(config["compare_min_value"], int | float) or isinstance(
        config["compare_min_value"], bool
    ):
        raise ValueError("ledger gate compare_min_value must be numeric")
    if not isinstance(config["min_compare_candidates"], int) or isinstance(
        config["min_compare_candidates"], bool
    ):
        raise ValueError("ledger gate min_compare_candidates must be an integer")


def _validate_raw_candidate(candidate: Mapping[str, Any], rank: int) -> None:
    required = {
        "model",
        "rank",
        "prior_pass",
        "prior_usd_resolved",
        "signals",
        "accepted",
        "signal_inspected",
    }
    if set(candidate) != required:
        raise ValueError(f"ledger raw candidate {rank} must contain exact schema-v1 fields")
    if not isinstance(candidate["model"], str) or not candidate["model"]:
        raise ValueError(f"ledger raw candidate {rank} has invalid model")
    if not isinstance(candidate["rank"], int) or isinstance(candidate["rank"], bool):
        raise ValueError(f"ledger raw candidate {rank} has invalid rank")
    if not isinstance(candidate["prior_pass"], int | float):
        raise ValueError(f"ledger raw candidate {rank} has invalid prior_pass")
    if not isinstance(candidate["prior_usd_resolved"], int | float):
        raise ValueError(f"ledger raw candidate {rank} has invalid prior_usd_resolved")
    if not isinstance(candidate["signals"], Mapping):
        raise ValueError(f"ledger raw candidate {rank} has invalid signals")
    if not isinstance(candidate["accepted"], bool):
        raise ValueError(f"ledger raw candidate {rank} has invalid accepted flag")
    if not isinstance(candidate["signal_inspected"], bool):
        raise ValueError(f"ledger raw candidate {rank} has invalid signal_inspected flag")


def _validate_aggregation(aggregation: Mapping[str, Any], candidate_count: int) -> None:
    required = {"method", "candidate_order", "tie_break"}
    if set(aggregation) != required:
        raise ValueError("ledger aggregation must contain exact schema-v1 fields")
    if aggregation["method"] not in {"ordered", "compare"}:
        raise ValueError("ledger aggregation method must be 'ordered' or 'compare'")
    order = aggregation["candidate_order"]
    if not isinstance(order, list) or len(order) != candidate_count:
        raise ValueError("ledger aggregation candidate_order has invalid cardinality")
    if aggregation["tie_break"] != "policy-order":
        raise ValueError("ledger aggregation tie_break must be 'policy-order'")


def _validate_final(final: Mapping[str, Any]) -> None:
    required = {"mode", "chosen_model", "reason", "accepted", "cost_usd"}
    if set(final) != required:
        raise ValueError("ledger final must contain exact schema-v1 fields")
    if final["mode"] not in {"ordered", "compare"}:
        raise ValueError("ledger final mode must be 'ordered' or 'compare'")
    if final["chosen_model"] is not None and not isinstance(final["chosen_model"], str):
        raise ValueError("ledger final chosen_model must be a string or null")
    if not isinstance(final["accepted"], bool):
        raise ValueError("ledger final accepted must be boolean")
    if final["cost_usd"] is not None and not isinstance(final["cost_usd"], int | float):
        raise ValueError("ledger final cost_usd must be numeric or null")


def _validate_cost(cost: Mapping[str, Any]) -> None:
    required = {
        "total_usd",
        "routed_usd",
        "currency",
        "billing_basis",
        "signals_precomputed",
        "cost_arm_usd",
        "quality_arm_usd",
        "multiplier_vs_cost_arm",
    }
    if set(cost) != required:
        raise ValueError("ledger cost must contain exact schema-v1 fields")
    if not isinstance(cost["currency"], str) or not cost["currency"]:
        raise ValueError("ledger cost currency must be a non-empty string")
    numeric = {
        "total_usd",
        "routed_usd",
        "cost_arm_usd",
        "quality_arm_usd",
        "multiplier_vs_cost_arm",
    }
    if any(
        not isinstance(cost[key], int | float) or isinstance(cost[key], bool)
        for key in numeric
    ):
        raise ValueError("ledger cost values must be numeric")
    if cost["billing_basis"] != "selected-execution-only":
        raise ValueError("ledger cost billing_basis is unsupported")
    if cost["signals_precomputed"] is not True:
        raise ValueError("ledger schema v1 requires precomputed signals")


def _validate_latency(latency: Mapping[str, Any]) -> None:
    if set(latency) != {"candidate_max", "aggregation", "total"}:
        raise ValueError("ledger latency_ms must contain exact schema-v1 fields")
    if any(
        not isinstance(value, int | float) or isinstance(value, bool)
        for value in latency.values()
    ):
        raise ValueError("ledger latency_ms values must be numeric")


def record_completeness(record: LedgerRecord | Mapping[str, Any]) -> float:
    """Fraction of required audit fields that are present (False/zero count)."""

    data = record.to_dict() if isinstance(record, LedgerRecord) else record
    present = sum(1 for path in _REQUIRED_PATHS if _path_present(data, path))
    return present / len(_REQUIRED_PATHS)


def _task_snapshot(task: Mapping[str, Any]) -> dict[str, Any]:
    profile = profile_task(task)
    snapshot = {
        "task_id": str(task.get("task_id")),
        **profile.to_dict(),
        "tokens": dict(task.get("tokens", {})),
    }
    for key in ("domain", "diff_size_lines", "value"):
        if key in task:
            snapshot[key] = task[key]
    return snapshot


def _policy_payload(policy: PolicyTable, task_class: TaskClass) -> dict[str, Any]:
    return {
        "version": policy.version,
        "class": task_class.value,
        "candidates": [
            {
                "model": candidate.model,
                "prior_pass": candidate.prior_pass,
                "prior_usd_resolved": candidate.prior_usd_resolved,
            }
            for candidate in policy.candidates_for(task_class)
        ],
    }


def _pricing_payload(pricing: PricingTable, models: tuple[str, ...]) -> dict[str, Any]:
    return {
        "version": pricing.version,
        "currency": pricing.currency,
        "default": asdict(pricing.default),
        "models": {
            model: asdict(pricing.rates_for(model)) for model in models
        },
    }


def _trace_accepted(trace: Mapping[str, Any]) -> bool:
    chosen = trace.get("chosen")
    return any(
        attempt.get("model") == chosen and bool(attempt.get("accepted"))
        for attempt in trace.get("attempts", [])
    )


def _path_present(data: Mapping[str, Any], path: tuple[str, ...]) -> bool:
    value: Any = data
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return False
        value = value[key]
    return value is not None
