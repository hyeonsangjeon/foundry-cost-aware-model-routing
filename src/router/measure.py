"""``cost-router measure`` — the *measured* live-run harness (BOLT Phase 0).

Everything else in this repo projects cost/coverage over synthetic telemetry
(``labels.measured = false``). This module is the isolated harness that turns a
prompt-bearing workload into a **measured** snapshot: it drives real Azure AI
Foundry deployments through an injected client seam, records one raw trace row
per *call attempt* (429 retries included), prices the real token usage, and
seals the result into a self-contained, fingerprinted snapshot that a
credential-free ``replay`` can recompute byte-for-byte.

Design (mirrors the rest of the repo — readable-first, honest-by-construction):

* **No egress by default.** The live client is an *injected seam*
  (:class:`MeasureClient`); :class:`AzureMeasureClient` is the only live adapter
  and it is built lazily, only on the ``--live`` path. Tests and CI drive the
  harness with a scripted fake and never touch the network.
* **``measured = true`` only for real live calls.** Every successful attempt
  carries a ``provenance``; a run is labelled ``measured`` only when every
  scored call was ``provenance = "live"``. Replays recompute from the recorded
  traces and are never a fresh measurement.
* **Deterministic replay.** :func:`compute_summary` is a pure function of the
  recorded traces × the pinned rate card, so ``run`` and ``replay`` produce a
  byte-identical ``summary.json``. Reuses the ledger's canonical hashing
  (:func:`router.ledger.record.canonical_json` / ``stable_hash``) for the
  per-file SHA-256 fingerprints.
* **Failures are first-class.** 429/throttle exhaustion, HTTP errors and
  timeouts are all recorded as trace rows and summarised — never dropped.

The bundled synthetic telemetry has no prompt text, so ``measure`` runs on a
prompt-bearing workload (default ``samples/telemetry/curated-arena-live.sample``)
whose per-task ``tokens`` estimates also drive the pre-flight dry-run cost table.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from time import perf_counter, sleep
from typing import Any, Protocol, runtime_checkable

import yaml

from . import __version__
from .pricing import PricingTable, format_usd
from .pricing_engine import (
    PricingEngine,
    as_engine,
    engine_from_snapshot,
)

# Bumped when the snapshot layout or summary schema changes in a
# non-backward-compatible way (recorded in every manifest for auditing).
MEASURE_RUNNER_VERSION = f"{__version__}+measure1"
TRACE_SCHEMA_VERSION = 1
SUMMARY_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 2

DEFAULT_N = 3
DEFAULT_SNAPSHOT_ROOT = Path("results/measured")

# Token estimate used for a dry-run when a workload task carries no ``tokens``
# block. Deliberately generic (not tuned to any tenant) so the estimate is a
# conservative planning figure, never a measured claim.
DEFAULT_DRY_RUN_TOKENS: dict[str, float] = {
    "input": 1500.0,
    "cached": 0.0,
    "output": 700.0,
    "reasoning": 300.0,
}

# Snapshots older than this many days are flagged stale by the measured
# range-contract validator (freshness warning, per BOLT §7.2).
SNAPSHOT_FRESHNESS_DAYS = 90


# --------------------------------------------------------------------------- #
# Value types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MeasureCandidate:
    """One model/deployment an experiment calls, on a given call surface."""

    model: str
    deployment: str
    provider: str = "openai"
    router: bool = False

    @classmethod
    def coerce(cls, value: MeasureCandidate | str | Mapping[str, Any]) -> MeasureCandidate:
        if isinstance(value, MeasureCandidate):
            return value
        if isinstance(value, str):
            return cls(model=value, deployment=value)
        deployment = str(value.get("deployment") or value["model"])
        return cls(
            model=str(value["model"]),
            deployment=deployment,
            provider=str(value.get("provider", "openai")),
            router=bool(value.get("router", False)),
        )


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential backoff for 429 (throttle) responses."""

    max_retries: int = 5
    base_backoff_ms: float = 500.0
    backoff_factor: float = 2.0
    max_backoff_ms: float = 30_000.0

    def backoff_ms(self, attempt_idx: int) -> float:
        """Deterministic backoff (ms) *before* retrying after ``attempt_idx`` (1-based)."""

        raw = self.base_backoff_ms * (self.backoff_factor ** (attempt_idx - 1))
        return float(min(raw, self.max_backoff_ms))

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_retries": self.max_retries,
            "base_backoff_ms": self.base_backoff_ms,
            "backoff_factor": self.backoff_factor,
            "max_backoff_ms": self.max_backoff_ms,
        }


@dataclass(frozen=True)
class AttemptResult:
    """One transport attempt: the HTTP status and (on success) usage it billed."""

    http_status: int
    model: str | None = None
    usage: Mapping[str, float] | None = None
    latency_ms: float = 0.0
    error: str | None = None
    provenance: str = "live"
    content: str | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.http_status < 300 and self.usage is not None

    @property
    def throttled(self) -> bool:
        return self.http_status == 429

    @property
    def server_error(self) -> bool:
        """A retryable 5xx transport failure (distinct from a 4xx client error)."""

        return 500 <= self.http_status <= 599

    @property
    def retryable(self) -> bool:
        """Runner-owned retry set: 429 throttling and 5xx server errors.

        Timeouts (408/0) are deliberately *not* retried here: a read timeout may
        leave the request in flight, so the runner seals it as unreconciled
        exposure rather than risk a double charge. 4xx client errors are fatal.
        """

        return self.throttled or self.server_error


@runtime_checkable
class MeasureClient(Protocol):
    """Anything that turns one (deployment, task) into an :class:`AttemptResult`."""

    def attempt(
        self, *, deployment: str, provider: str, task: Mapping[str, Any]
    ) -> AttemptResult:  # pragma: no cover - protocol
        ...


def _http_status_of(exc: BaseException) -> int:
    """Best-effort HTTP status extraction from an SDK/transport exception."""

    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int):
        return status
    name = type(exc).__name__.lower()
    if "ratelimit" in name or "throttl" in name:
        return 429
    if "timeout" in name:
        return 408
    return 0


@dataclass
class AzureMeasureClient:
    """Live adapter: drive a real deployment and surface status + billed usage.

    The only egressing :class:`MeasureClient`. Built lazily on the ``--live``
    path; wraps :class:`router.foundry_live.AzureModelRouterClient` (keyless
    Entra, lazy SDK import) and maps a rate-limit exception to HTTP 429 so the
    runner's backoff loop records every throttled attempt.
    """

    client: Any  # AzureModelRouterClient (kept Any to avoid a hard import)

    def attempt(
        self, *, deployment: str, provider: str, task: Mapping[str, Any]
    ) -> AttemptResult:  # pragma: no cover - live path, operator-gated
        from .foundry_live import normalize_model_name

        started = perf_counter()
        try:
            outcome = self.client.complete(task, deployment=deployment, provider=provider)
        except Exception as exc:  # noqa: BLE001 - map any transport error to a status
            latency = (perf_counter() - started) * 1000.0
            return AttemptResult(
                http_status=_http_status_of(exc), latency_ms=latency,
                error=str(exc)[:200], provenance="live",
            )
        latency = (perf_counter() - started) * 1000.0
        return AttemptResult(
            http_status=200,
            model=normalize_model_name(outcome.model) or deployment,
            usage=dict(outcome.usage),
            latency_ms=latency,
            provenance=outcome.provenance,
            content=getattr(outcome, "content", None),
        )


# A grader scores one successful outcome as pass/fail. Without one, spend is
# measured but correctness is honestly *ungraded* (coverage is null). The last
# argument is the captured output (the generated code); a content grader returns
# a ``GradeVerdict`` (tri-state + output hash), a legacy usage grader returns a
# plain ``bool``. ``run_candidate`` normalizes either shape.
Grader = Callable[
    [str, Mapping[str, Any], str, Mapping[str, float], "str | None"], "Any"
]


# --------------------------------------------------------------------------- #
# Workload loading
# --------------------------------------------------------------------------- #


def load_prompt_workload(path: Path | str) -> dict[str, dict[str, Any]]:
    """Load a prompt-bearing JSONL workload as ``task_id -> task`` (order kept).

    Only tasks that carry a ``prompt`` (or ``messages``) can be measured live;
    tasks without one are skipped. Each task keeps its optional ``tokens``
    estimate block, which the dry-run cost table uses.

    The canonical BOLT-02 task schema is
    ``{task_id, class, system_prompt, user_prompt, validation}``; for backward
    compatibility ``user_prompt`` also reads from ``prompt``/``text``/``input``
    and ``system_prompt`` from ``system``. Any ``validation`` block is checked
    with :func:`router.validation.validate_rule` at load time, so a malformed or
    subjective rule fails loudly *here* — before any (paid) live run — rather
    than silently passing a measured task.
    """

    from .validation import validate_rule

    tasks: dict[str, dict[str, Any]] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        prompt = row.get("user_prompt") or row.get("prompt") or row.get("text") or row.get("input")
        if not prompt and not row.get("messages"):
            continue
        task_id = str(row.get("task_id") or row.get("id") or f"task-{len(tasks) + 1}")
        task: dict[str, Any] = {"task_id": task_id, "prompt": str(prompt) if prompt else ""}
        if row.get("messages"):
            task["messages"] = row["messages"]
        system = row.get("system_prompt") or row.get("system")
        if system:
            task["system"] = str(system)
        if isinstance(row.get("tokens"), Mapping):
            task["tokens"] = {k: float(v) for k, v in row["tokens"].items()}
        if row.get("title"):
            task["title"] = str(row["title"])
        if row.get("class"):
            task["class"] = str(row["class"])
        if row.get("acceptance"):
            task["acceptance"] = str(row["acceptance"])
        if row.get("validation") is not None:
            validate_rule(row["validation"])  # raises ValidationSpecError on a bad rule
            task["validation"] = row["validation"]
        tasks[task_id] = task
    return tasks


# --------------------------------------------------------------------------- #
# Dry-run cost estimate (no live calls)
# --------------------------------------------------------------------------- #


def estimate_dry_run(
    workload: Mapping[str, Mapping[str, Any]],
    candidates: Sequence[MeasureCandidate],
    *,
    n: int,
    pricing: PricingTable | PricingEngine,
    default_tokens: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Estimate the spend of a live run *before* making any call.

    Cost = Σ over (task × candidate × n) of ``pricing × est-tokens``. Token
    estimates come from each task's ``tokens`` block when present, else from
    ``default_tokens`` — the estimate is a planning figure, never a measurement.
    Under the v2 composite card a Model-Router arm's pick is unknown before the
    run, so its cell is honestly *unpriced* (``est_cost_usd = null``) and the
    run's reservation ceiling falls back to the budget rather than a guess.
    """

    engine = as_engine(pricing)
    tokens_default = dict(default_tokens or DEFAULT_DRY_RUN_TOKENS)
    per_candidate: list[dict[str, Any]] = []
    grand_total = 0.0
    unpriced_models: list[str] = []
    for candidate in candidates:
        cand_total = 0.0
        cand_priced = True
        for task in workload.values():
            est = task.get("tokens") if isinstance(task.get("tokens"), Mapping) else tokens_default
            priced = engine.price_estimate(candidate, est)
            if priced.priced and priced.cost_usd is not None:
                cand_total += priced.cost_usd
            else:
                cand_priced = False
        if cand_priced:
            cand_total *= n
            grand_total += cand_total
            est_cost: float | None = round(cand_total, 6)
        else:
            est_cost = None
            unpriced_models.append(candidate.model)
        per_candidate.append(
            {
                "model": candidate.model,
                "deployment": candidate.deployment,
                "calls": len(workload) * n,
                "est_cost_usd": est_cost,
            }
        )
    estimate: dict[str, Any] = {
        "tasks": len(workload),
        "candidates": len(candidates),
        "n": n,
        "calls": len(workload) * len(candidates) * n,
        "per_candidate": per_candidate,
        "est_total_usd": round(grand_total, 6),
        "labels": {"measured": False, "estimate": True, "basis": "list-price × est-tokens"},
    }
    if engine.version >= 2:
        estimate["labels"]["basis"] = "composite-rate-card-v2 × est-tokens"
        estimate["unpriced_models"] = unpriced_models
        estimate["cost_complete"] = not unpriced_models
    return estimate


def format_dry_run_table(estimate: Mapping[str, Any], *, budget_usd: float | None = None) -> str:
    """Render the dry-run estimate as a human-readable pre-flight table."""

    lines = [
        "dry-run cost estimate (NO live calls yet — planning figures only)",
        f"  tasks={estimate['tasks']}  candidates={estimate['candidates']}  "
        f"n={estimate['n']}  → {estimate['calls']} live calls",
        "",
        f"  {'candidate':22s} {'calls':>6s} {'est cost':>12s}",
        f"  {'-' * 22} {'-' * 6} {'-' * 12}",
    ]
    for row in estimate["per_candidate"]:
        est = row["est_cost_usd"]
        cost_cell = "unpriced" if est is None else format_usd(est)
        lines.append(
            f"  {row['model'][:22]:22s} {row['calls']:>6d} {cost_cell:>12s}"
        )
    lines.append(f"  {'-' * 22} {'-' * 6} {'-' * 12}")
    lines.append(f"  {'TOTAL (estimate)':22s} {estimate['calls']:>6d} "
                 f"{format_usd(estimate['est_total_usd']):>12s}")
    if budget_usd is not None:
        headroom = budget_usd - estimate["est_total_usd"]
        verdict = "within budget" if headroom >= 0 else "OVER BUDGET"
        lines.append("")
        lines.append(f"  budget cap : {format_usd(budget_usd)}  ({verdict}, "
                     f"headroom {format_usd(headroom)})")
    lines.append("")
    lines.append("  basis: list-price × per-task token estimate; real spend depends on live usage.")
    unpriced = estimate.get("unpriced_models")
    if unpriced:
        lines.append(
            "  unpriced (composite card, pick unknown pre-run): "
            + ", ".join(unpriced)
            + " — reserved against the budget cap, not a per-cell estimate."
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Pre-flight prompt catalog (B4/D12) — "here is exactly what will go out"
# --------------------------------------------------------------------------- #


def build_catalog(
    workload: Mapping[str, Mapping[str, Any]],
    candidates: Sequence[MeasureCandidate],
    *,
    n: int,
    pricing: PricingTable | PricingEngine,
) -> dict[str, Any]:
    """Assemble the full pre-run picture *before* any call (D12).

    For every task it surfaces the system/user prompt text in full, the
    machine-readable validation rule (human-summarised), and the per-task token
    estimate; alongside the candidate slate and the dry-run cost estimate. The
    point is that nothing goes out unseen — the operator reads exactly this,
    then decides whether to spend.
    """

    from .validation import describe_rule

    tokens_default = dict(DEFAULT_DRY_RUN_TOKENS)
    tasks: list[dict[str, Any]] = []
    graded = 0
    for task in workload.values():
        rule = task.get("validation")
        if rule is not None:
            graded += 1
        est = task.get("tokens") if isinstance(task.get("tokens"), Mapping) else tokens_default
        tasks.append(
            {
                "task_id": task.get("task_id", ""),
                "class": task.get("class"),
                "title": task.get("title"),
                "system_prompt": task.get("system", ""),
                "user_prompt": task.get("prompt", ""),
                "validation": describe_rule(rule) if isinstance(rule, Mapping) else None,
                "est_tokens": {k: float(v) for k, v in est.items()},
            }
        )
    estimate = estimate_dry_run(workload, candidates, n=n, pricing=pricing)
    return {
        "tasks": tasks,
        "candidates": [
            {"model": c.model, "deployment": c.deployment, "provider": c.provider}
            for c in candidates
        ],
        "graded_tasks": graded,
        "ungraded_tasks": len(tasks) - graded,
        "n": n,
        "estimate": estimate,
        "workload_fingerprint": workload_fingerprint(workload),
        "labels": {"measured": False, "estimate": True},
    }


def format_catalog(catalog: Mapping[str, Any], *, budget_usd: float | None = None) -> str:
    """Render :func:`build_catalog` as a human pre-flight sheet (no live calls)."""

    tasks = catalog["tasks"]
    lines = [
        "prompt catalog — exactly what a live run would send (NO calls made here)",
        f"  tasks={len(tasks)}  graded={catalog['graded_tasks']}  "
        f"ungraded={catalog['ungraded_tasks']}  n={catalog['n']}",
        f"  workload fingerprint: {catalog['workload_fingerprint']}",
        "",
        "  candidates:",
    ]
    for cand in catalog["candidates"]:
        prov = f"  [{cand['provider']}]" if cand.get("provider") else ""
        lines.append(f"    - {cand['model']} (deployment {cand['deployment']}){prov}")
    lines.append("")
    for idx, task in enumerate(tasks, start=1):
        header = f"  [{idx}] {task['task_id']}"
        if task.get("class"):
            header += f"  ({task['class']})"
        if task.get("title"):
            header += f"  — {task['title']}"
        lines.append(header)
        if task.get("system_prompt"):
            lines.append(f"      system: {task['system_prompt']}")
        lines.append(f"      user  : {task['user_prompt']}")
        rule = task.get("validation")
        lines.append(f"      pass if: {rule}" if rule else "      pass if: (ungraded — no rule)")
        est = task["est_tokens"]
        lines.append(
            "      est tokens: "
            + ", ".join(f"{k}={int(v)}" for k, v in est.items())
        )
        lines.append("")
    lines.append(format_dry_run_table(catalog["estimate"], budget_usd=budget_usd))
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Trace construction + per-candidate retry loop
# --------------------------------------------------------------------------- #


def _trace_row(
    *,
    run_id: str,
    exp_id: str,
    task_id: str,
    repeat_idx: int,
    candidate_model: str,
    attempt_idx: int,
    tokens: Mapping[str, float],
    latency_ms: float,
    http_status: int,
    retries: int,
    backoff_ms_total: float,
    cost_usd: float | None,
    passed: bool | None,
    score: float | None,
    fail_reason: str | None,
    measured: bool,
    ts: str,
    extra: Mapping[str, Any] | None = None,
    output_sha256: str | None = None,
    grade_error: str | None = None,
) -> dict[str, Any]:
    """Build one canonical trace row (§3.2). Field order is fixed for readability.

    ``cost_usd`` is ``None`` for an *unpriced* attempt (fail-closed: the amount
    is withheld, never fabricated as ``0.0``). ``extra`` carries engine-specific
    columns (the v2 composite breakdown) so replay recomputes the identical
    number; the v1 engine passes nothing, keeping legacy rows byte-identical.
    """

    row: dict[str, Any] = {
        "run_id": run_id,
        "exp_id": exp_id,
        "task_id": task_id,
        "repeat_idx": repeat_idx,
        "candidate_model": candidate_model,
        "attempt_idx": attempt_idx,
        "tokens": {
            "input": float(tokens.get("input", 0.0)),
            "cached": float(tokens.get("cached", 0.0)),
            "output": float(tokens.get("output", 0.0)),
            "reasoning": float(tokens.get("reasoning", 0.0)),
        },
        "latency_ms": round(float(latency_ms), 1),
        "http_status": int(http_status),
        "retries": int(retries),
        "backoff_ms_total": round(float(backoff_ms_total), 1),
        "cost_usd": None if cost_usd is None else round(float(cost_usd), 6),
        "pass": passed,
        "score": score,
        "fail_reason": fail_reason,
        "labels": {"measured": bool(measured)},
        "ts": ts,
    }
    # Grading evidence is present only when a content grader ran, so an ungraded
    # run's rows stay byte-identical (and out of the public grading surface).
    if output_sha256 is not None:
        row["output_sha256"] = output_sha256
    if grade_error is not None:
        row["grade_error"] = grade_error
    if extra:
        row.update(extra)
    return row


def _normalize_verdict(verdict: Any) -> tuple[bool | None, str | None, str | None]:
    """Reduce a grader result to ``(passed, output_sha256, grade_error)``.

    Accepts a content grader's :class:`~router.benchmark_grader.GradeVerdict`
    (duck-typed: any object exposing ``passed``/``output_sha256``/``detail``) or
    a legacy usage grader's plain ``bool``/``None``. A tri-state ``passed=None``
    with output present carries its ``detail`` as ``grade_error`` so an ungraded
    captured cell is visible (and counts against coverage), never dropped.
    """

    if verdict is None or isinstance(verdict, bool):
        return (None if verdict is None else bool(verdict)), None, None
    passed = getattr(verdict, "passed", None)
    output_sha256 = getattr(verdict, "output_sha256", None)
    detail = getattr(verdict, "detail", "") or None
    grade_error = detail if passed is None else None
    return passed, output_sha256, grade_error


def run_candidate(
    client: MeasureClient,
    task: Mapping[str, Any],
    candidate: MeasureCandidate,
    *,
    run_id: str,
    exp_id: str,
    repeat_idx: int,
    pricing: PricingTable | PricingEngine,
    retry: RetryPolicy,
    grader: Grader | None = None,
    sleeper: Callable[[float], None] = sleep,
    clock: Callable[[], str] | None = None,
) -> tuple[list[dict[str, Any]], AttemptResult | None]:
    """Drive one (task, candidate, repeat) with bounded 429 backoff.

    Returns ``(trace_rows, final_ok_result_or_None)``. Every attempt is one row;
    a 429 retry adds a row and (deterministically computed) backoff. Exhausting
    the retry budget records ``fail_reason = "throttle_exhausted"``.
    """

    engine = as_engine(pricing)
    now = clock or (lambda: datetime.now(UTC).isoformat(timespec="milliseconds"))
    task_id = str(task.get("task_id") or task.get("id") or "")
    rows: list[dict[str, Any]] = []
    backoff_total = 0.0
    max_attempts = retry.max_retries + 1
    for attempt_idx in range(1, max_attempts + 1):
        result = client.attempt(
            deployment=candidate.deployment, provider=candidate.provider, task=task
        )
        retries = attempt_idx - 1
        if result.ok:
            usage = dict(result.usage or {})
            priced = engine.price(candidate, resolved_model=result.model, usage=usage)
            passed: bool | None = None
            output_sha256: str | None = None
            grade_error: str | None = None
            if grader is not None:
                verdict = grader(task_id, task, candidate.model, usage, result.content)
                passed, output_sha256, grade_error = _normalize_verdict(verdict)
            rows.append(
                _trace_row(
                    run_id=run_id, exp_id=exp_id, task_id=task_id, repeat_idx=repeat_idx,
                    candidate_model=candidate.model, attempt_idx=attempt_idx, tokens=usage,
                    latency_ms=result.latency_ms, http_status=result.http_status,
                    retries=retries, backoff_ms_total=backoff_total, cost_usd=priced.cost_usd,
                    passed=passed, score=None, fail_reason=None,
                    measured=result.provenance == "live", ts=now(),
                    extra=priced.trace_fields(),
                    output_sha256=output_sha256, grade_error=grade_error,
                )
            )
            return rows, result
        can_retry = result.retryable and attempt_idx <= retry.max_retries
        if can_retry:
            wait = retry.backoff_ms(attempt_idx)
            backoff_total += wait
            fail_reason: str | None = (
                "throttled_429" if result.throttled else f"retry_http_{result.http_status}"
            )
        elif result.throttled:
            fail_reason = "throttle_exhausted"
        elif result.server_error:
            fail_reason = f"http_{result.http_status}_exhausted"
        elif result.http_status == 408 or result.http_status == 0:
            fail_reason = "timeout" if result.http_status == 408 else "transport_error"
        else:
            fail_reason = f"http_{result.http_status}"
        rows.append(
            _trace_row(
                run_id=run_id, exp_id=exp_id, task_id=task_id, repeat_idx=repeat_idx,
                candidate_model=candidate.model, attempt_idx=attempt_idx, tokens={},
                latency_ms=result.latency_ms, http_status=result.http_status,
                retries=retries, backoff_ms_total=backoff_total, cost_usd=0.0,
                passed=False, score=None, fail_reason=fail_reason,
                measured=result.provenance == "live", ts=now(),
            )
        )
        if not can_retry:
            return rows, None
        sleeper(wait / 1000.0)
    return rows, None  # pragma: no cover - loop always returns inside


# --------------------------------------------------------------------------- #
# Deterministic summary (shared by run + replay → byte-identical output)
# --------------------------------------------------------------------------- #


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    rank = max(1, ceil(pct / 100.0 * len(sorted_values)))
    return float(sorted_values[rank - 1])


def compute_summary(
    traces: Sequence[Mapping[str, Any]],
    pricing: PricingTable | PricingEngine,
    *,
    exp_id: str,
    run_id: str,
    n: int,
    task_ids: Sequence[str],
    candidate_models: Sequence[str],
    partial: bool,
    planned_cells: int | None = None,
) -> dict[str, Any]:
    """Aggregate raw traces into the canonical ``summary.json`` (pure function).

    This is the single source of the summary so ``run`` and ``replay`` are
    byte-identical: every number is derived only from the recorded traces and
    the pinned rate card. Each successful call's ``cost_usd`` is re-derived from
    its usage × ``pricing`` — a mismatch surfaces as a ``cost_mismatch`` failure.
    An *unpriced* attempt (v2 fail-closed) withholds its amount (``cost_usd`` is
    ``null``): it still counts as a graded call but adds no spend, is excluded
    from the savings comparison, and marks the run ``cost_complete = false``.
    """

    engine = as_engine(pricing)
    by_candidate: dict[str, dict[str, Any]] = {
        model: {"total_usd": 0.0, "calls": 0, "unpriced": 0, "latencies": [],
                "tokens": _zero_tokens()}
        for model in candidate_models
    }
    totals_tokens = _zero_tokens()
    total_cost = 0.0
    ok_calls = 0
    unpriced_calls = 0
    graded = 0
    accepted = 0
    http_429 = 0
    retries_total = 0
    throttle_exhausted = 0
    backoff_ms_total = 0.0
    cached_tokens = 0.0
    input_tokens = 0.0
    failures: list[dict[str, Any]] = []
    all_live = True
    saw_call = False
    cost_mismatches: list[dict[str, Any]] = []

    for row in traces:
        status = int(row.get("http_status", 0))
        if status == 429:
            http_429 += 1
        model = str(row.get("candidate_model", ""))
        tokens = row.get("tokens") or {}
        passed = row.get("pass")
        reason = row.get("fail_reason")
        measured_label = bool((row.get("labels") or {}).get("measured", False))
        is_ok = 200 <= status < 300 and reason is None
        if is_ok:
            saw_call = True
            ok_calls += 1
            if not measured_label:
                all_live = False
            expected = engine.recompute(row)
            recorded_raw = row.get("cost_usd", 0.0)
            recorded_is_none = recorded_raw is None
            recorded_cost = 0.0 if recorded_is_none else float(recorded_raw)
            cost_priced = expected.priced and not recorded_is_none
            if expected.priced != (not recorded_is_none):
                # Integrity breach: one side claims a number the other withholds.
                cost_mismatches.append(
                    {
                        "task_id": row.get("task_id"),
                        "candidate_model": model,
                        "attempt_idx": row.get("attempt_idx"),
                        "recorded": None if recorded_is_none else recorded_cost,
                        "expected": expected.cost_usd,
                    }
                )
            elif cost_priced and round(expected.cost_usd, 6) != round(recorded_cost, 6):
                cost_mismatches.append(
                    {
                        "task_id": row.get("task_id"),
                        "candidate_model": model,
                        "attempt_idx": row.get("attempt_idx"),
                        "recorded": recorded_cost,
                        "expected": expected.cost_usd,
                    }
                )
            bucket = by_candidate.setdefault(
                model,
                {"total_usd": 0.0, "calls": 0, "unpriced": 0, "latencies": [],
                 "tokens": _zero_tokens()},
            )
            if cost_priced:
                total_cost += recorded_cost
                bucket["total_usd"] += recorded_cost
            else:
                unpriced_calls += 1
                bucket["unpriced"] += 1
            bucket["calls"] += 1
            bucket["latencies"].append(float(row.get("latency_ms", 0.0)))
            _add_tokens(bucket["tokens"], tokens)
            _add_tokens(totals_tokens, tokens)
            cached_tokens += float(tokens.get("cached", 0.0))
            input_tokens += float(tokens.get("input", 0.0))
            if passed is not None:
                graded += 1
                if passed:
                    accepted += 1
        else:
            if reason == "throttle_exhausted":
                throttle_exhausted += 1
            failures.append(
                {
                    "task_id": row.get("task_id"),
                    "repeat_idx": row.get("repeat_idx"),
                    "candidate_model": model,
                    "attempt_idx": row.get("attempt_idx"),
                    "http_status": status,
                    "fail_reason": reason,
                }
            )

    # Retries + backoff are re-derived from the per-attempt rows: any attempt
    # beyond the first for a (task, repeat, candidate) is a retry.
    retries_total = _count_retries(traces)
    backoff_ms_total = round(sum(float(r.get("backoff_ms_total", 0.0)) for r in traces), 1)

    candidate_out: dict[str, Any] = {}
    for model in sorted(by_candidate):
        bucket = by_candidate[model]
        calls = bucket["calls"]
        priced_calls = calls - bucket["unpriced"]
        latencies = sorted(bucket["latencies"])
        entry = {
            "total_usd": round(bucket["total_usd"], 6),
            "calls": calls,
            "avg_usd_per_call": (
                round(bucket["total_usd"] / priced_calls, 6) if priced_calls else 0.0
            ),
            "latency_p50_ms": round(_percentile(latencies, 50), 1),
            "latency_p95_ms": round(_percentile(latencies, 95), 1),
            "tokens": {k: round(v, 1) for k, v in bucket["tokens"].items()},
        }
        if engine.version >= 2:
            entry["unpriced_calls"] = bucket["unpriced"]
            entry["cost_complete"] = bucket["unpriced"] == 0
        candidate_out[model] = entry

    # Only cost-complete arms enter the savings comparison: an unpriced arm is
    # never treated as a cheap $0 winner (fail-closed withholds, never claims).
    priced = {
        m: v["total_usd"]
        for m, v in candidate_out.items()
        if v["calls"] > 0 and by_candidate[m]["unpriced"] == 0
    }
    if priced:
        naive_total = max(priced.values())
        best_total = min(priced.values())
        naive_model = sorted(m for m, t in priced.items() if t == naive_total)[0]
        best_model = sorted(m for m, t in priced.items() if t == best_total)[0]
        savings_pct = (
            round((naive_total - best_total) / naive_total * 100, 1) if naive_total else 0.0
        )
    else:
        naive_total = best_total = 0.0
        naive_model = best_model = None
        savings_pct = 0.0

    all_latencies = sorted(
        float(r.get("latency_ms", 0.0))
        for r in traces
        if 200 <= int(r.get("http_status", 0)) < 300 and r.get("fail_reason") is None
    )
    coverage_block: dict[str, Any] | None
    if graded > 0:
        coverage_block = {
            "graded": graded,
            "accepted": accepted,
            "coverage": round(accepted / graded, 6),
            "basis": "graded",
        }
        accuracy = "graded"
    else:
        coverage_block = None
        accuracy = "ungraded"

    measured = saw_call and all_live
    summary: dict[str, Any] = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "exp_id": exp_id,
        "run_id": run_id,
        "n": n,
        "tasks": len(set(task_ids)),
        "candidates": sorted(candidate_models),
        "attempts": len(traces),
        "calls": ok_calls,
        "labels": {
            "measured": measured,
            "spend_source": "provider-usage",
            "cost_basis": engine.cost_basis_label(),
            "accuracy": accuracy,
            "partial": bool(partial),
        },
        "cost": {
            "total_usd": round(total_cost, 6),
            "by_candidate": candidate_out,
            "naive_model": naive_model,
            "naive_total_usd": round(naive_total, 6),
            "best_model": best_model,
            "best_total_usd": round(best_total, 6),
            "savings_pct": savings_pct,
        },
        "coverage": coverage_block,
        "latency_ms": {
            "p50": round(_percentile(all_latencies, 50), 1),
            "p95": round(_percentile(all_latencies, 95), 1),
        },
        "throttle": {
            "http_429": http_429,
            "retries": retries_total,
            "throttle_exhausted": throttle_exhausted,
            "backoff_ms_total": backoff_ms_total,
        },
        "cache": {
            "cached_tokens": round(cached_tokens, 1),
            "input_tokens": round(input_tokens, 1),
            "cached_fraction": round(cached_tokens / input_tokens, 6) if input_tokens else 0.0,
        },
        "tokens": {k: round(v, 1) for k, v in totals_tokens.items()},
        "failures": failures,
        "integrity": {"cost_mismatches": cost_mismatches},
    }
    if engine.version >= 2:
        # Fail-closed cost completeness: any withheld amount makes the run's
        # spend total a floor, not a settled figure, and blocks a savings claim.
        summary["cost"]["unpriced_calls"] = unpriced_calls
        summary["cost"]["cost_complete"] = unpriced_calls == 0
        if unpriced_calls:
            summary["cost"]["savings_claim_allowed"] = False

    grading_block, quality_block = _grading_blocks(
        traces,
        candidate_models=candidate_models,
        n=n,
        planned_cells=planned_cells,
        arm_known_cost={m: v["total_usd"] for m, v in candidate_out.items()},
    )
    if grading_block is not None:
        summary["grading"] = grading_block
        summary["quality"] = quality_block
        summary["labels"]["quality_graded"] = quality_block["quality_graded"]
    return summary


def _grading_blocks(
    traces: Sequence[Mapping[str, Any]],
    *,
    candidate_models: Sequence[str],
    n: int,
    planned_cells: int | None,
    arm_known_cost: Mapping[str, float],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Derive the ``grading`` + ``quality`` summary blocks from traces.

    Pure function of the trace rows so replay reproduces it byte-identically and
    any tampered ``pass`` value changes the summary (tamper-evident). Emits
    ``None, None`` unless at least one content-graded cell exists (a row carrying
    ``output_sha256``), keeping ungraded and legacy usage-grader runs untouched.

    Coverage is graded-cells / planned-cells (§10): a cell whose grader could not
    run (``pass is None`` with output captured) counts as a grade error and drags
    coverage down — it is never silently dropped. Task-level quality uses
    majority-pass-of-``n`` (needs > n/2 passing repeats); cost-per-pass divides an
    arm's known (priced) spend by its passed tasks.
    """

    def _ok(row: Mapping[str, Any]) -> bool:
        return 200 <= int(row.get("http_status", 0)) < 300 and row.get("fail_reason") is None

    content_rows = [r for r in traces if _ok(r) and r.get("output_sha256")]
    if not content_rows:
        return None, None

    graded_cells = sum(1 for r in content_rows if r.get("pass") is not None)
    grade_errors = sum(1 for r in content_rows if r.get("pass") is None)
    arms = len(candidate_models) or 1
    planned = planned_cells if planned_cells else len(content_rows)
    denom = n * arms
    if denom:
        planned_tasks = planned // denom
    else:
        planned_tasks = len({str(r.get("task_id")) for r in content_rows})

    by_model_task: dict[tuple[str, str], list[Any]] = {}
    for r in content_rows:
        key = (str(r.get("candidate_model")), str(r.get("task_id")))
        by_model_task.setdefault(key, []).append(r.get("pass"))

    quality_by_candidate: dict[str, Any] = {}
    for model in sorted(set(candidate_models)):
        tasks = {t for (m, t) in by_model_task if m == model}
        passed_tasks = 0
        for task_id in tasks:
            passes = by_model_task[(model, task_id)]
            if sum(1 for p in passes if p is True) * 2 > n:
                passed_tasks += 1
        known = round(float(arm_known_cost.get(model, 0.0)), 6)
        quality_by_candidate[model] = {
            "tasks_planned": planned_tasks,
            "tasks_passed": passed_tasks,
            "pass_rate": round(passed_tasks / planned_tasks, 6) if planned_tasks else 0.0,
            "known_cost_usd": known,
            "cost_per_pass_usd": round(known / passed_tasks, 6) if passed_tasks else None,
        }

    grading = {
        "basis": "exec-signals",
        "planned_cells": planned,
        "content_graded": len(content_rows),
        "graded_cells": graded_cells,
        "grade_errors": grade_errors,
        "coverage": round(graded_cells / planned, 6) if planned else 0.0,
    }
    quality = {
        "quality_graded": graded_cells > 0,
        "by_candidate": quality_by_candidate,
    }
    return grading, quality


def _zero_tokens() -> dict[str, float]:
    return {"input": 0.0, "cached": 0.0, "output": 0.0, "reasoning": 0.0}


def _add_tokens(acc: MutableMapping[str, float], tokens: Mapping[str, Any]) -> None:
    for key in ("input", "cached", "output", "reasoning"):
        acc[key] = acc.get(key, 0.0) + float(tokens.get(key, 0.0) or 0.0)


def _cell_key(row: Mapping[str, Any]) -> tuple[str, int, str]:
    """Identity of one (task, repeat, candidate) cell within a run."""

    return (
        str(row.get("task_id")),
        int(row.get("repeat_idx", 0)),
        str(row.get("candidate_model")),
    )


def _count_retries(traces: Sequence[Mapping[str, Any]]) -> int:
    seen: set[tuple[str, int, str]] = set()
    retries = 0
    for row in traces:
        key = _cell_key(row)
        if key in seen:
            retries += 1
        else:
            seen.add(key)
    return retries


# --------------------------------------------------------------------------- #
# Snapshot serialization + fingerprints
# --------------------------------------------------------------------------- #


def _dumps(value: Any) -> str:
    """Stable pretty JSON used for every snapshot JSON file (byte-reproducible)."""

    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _dump_traces(traces: Iterable[Mapping[str, Any]]) -> str:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in traces
    )


def pricing_snapshot_yaml(pricing: PricingTable) -> str:
    """Serialize the full rate card as YAML for the run's ``pricing.snapshot.yaml``."""

    from dataclasses import asdict

    payload = {
        "version": pricing.version,
        "currency": pricing.currency,
        "default": asdict(pricing.default),
        "models": {model: asdict(rates) for model, rates in sorted(pricing.models.items())},
    }
    return yaml.safe_dump(payload, sort_keys=True, allow_unicode=True)


def pricing_from_snapshot_yaml(text: str) -> PricingTable:
    """Rebuild a :class:`PricingTable` from a ``pricing.snapshot.yaml`` blob."""

    from .pricing import TokenRates

    data = yaml.safe_load(text)
    return PricingTable(
        models={m: TokenRates.from_dict(r) for m, r in data.get("models", {}).items()},
        default=TokenRates.from_dict(data["default"]),
        version=int(data.get("version", 1)),
        currency=str(data.get("currency", "USD")),
    )


def _fingerprints(files: Mapping[str, str]) -> dict[str, str]:
    """SHA-256 of each snapshot file's exact bytes (via the shared ledger hash)."""

    return {
        name: "sha256:" + stable_hash_bytes(content) for name, content in sorted(files.items())
    }


def workload_fingerprint(workload: Mapping[str, Mapping[str, Any]]) -> str:
    """SHA-256 of the measured workload's canonical content (D14).

    Hashes a stable, whitespace-insensitive serialization of the whole task
    mapping, so any change to the tasks — including their ``system_prompt`` /
    ``user_prompt`` / ``validation`` fields — yields a different fingerprint.
    The gap view can then treat two runs with different prompts as different
    experiments rather than silently comparing unlike workloads.
    """

    canonical = json.dumps(workload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + stable_hash_bytes(canonical)


def stable_hash_bytes(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# prereg gate (D8)
# --------------------------------------------------------------------------- #


def git_committed_at(path: Path | str) -> tuple[str, str] | None:
    """Return ``(commit_hash, iso_commit_time)`` of the last commit to ``path``.

    ``None`` when the file is untracked / never committed. Used by the prereg
    gate so a live run cannot start unless its pre-registration was committed
    beforehand (a tamper-evident timestamp).

    The path is normalized to an absolute one first: git runs with ``cwd`` set to
    the file's own directory, so a repo-relative path would be resolved twice and
    silently return ``None`` — reading as "never committed" when it was.
    """

    from .preregistration import git_dir_and_path

    cwd, file_path = git_dir_and_path(path)
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%H%x00%cI", "--", str(file_path)],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):  # pragma: no cover - git absent
        return None
    line = out.stdout.strip()
    if out.returncode != 0 or not line or "\x00" not in line:
        return None
    commit_hash, _, iso_time = line.partition("\x00")
    if not commit_hash or not iso_time:
        return None
    return commit_hash, iso_time


@dataclass(frozen=True)
class PreregDecision:
    """Outcome of the prereg gate for a run."""

    allowed: bool
    commit_hash: str | None
    committed_at: str | None
    note: str
    bypassed: bool = False


def evaluate_prereg(
    prereg_path: Path | str,
    *,
    run_started_at: datetime,
    allow_no_prereg: bool = False,
    committed_at_fn: Callable[[Path | str], tuple[str, str] | None] = git_committed_at,
) -> PreregDecision:
    """Enforce D8: a live run needs a prereg committed *before* it starts."""

    path = Path(prereg_path)
    if not path.is_file():
        if allow_no_prereg:
            return PreregDecision(True, None, None, "no prereg file (bypassed)", bypassed=True)
        return PreregDecision(False, None, None, f"prereg file not found: {path}")
    committed = committed_at_fn(path)
    if committed is None:
        if allow_no_prereg:
            return PreregDecision(
                True, None, None, "prereg not committed (bypassed)", bypassed=True
            )
        return PreregDecision(
            False, None, None,
            f"prereg {path} is not committed; commit it before the run (or --allow-no-prereg)",
        )
    commit_hash, committed_at = committed
    try:
        committed_dt = datetime.fromisoformat(committed_at)
    except ValueError:  # pragma: no cover - git always returns ISO
        committed_dt = run_started_at
    if committed_dt > run_started_at:
        if allow_no_prereg:
            return PreregDecision(
                True, commit_hash, committed_at,
                "prereg committed after run start (bypassed)", bypassed=True,
            )
        return PreregDecision(
            False, commit_hash, committed_at,
            "prereg must be committed BEFORE the run starts "
            f"(committed {committed_at}, run started {run_started_at.isoformat()})",
        )
    return PreregDecision(True, commit_hash, committed_at, "prereg committed before run")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


@dataclass
class MeasureRunResult:
    """The written snapshot of a measure run."""

    run_dir: Path
    run_id: str
    exp_id: str
    summary: dict[str, Any]
    manifest: dict[str, Any]
    partial: bool
    stopped_reason: str | None = None


def make_run_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return stamp


def _completed_keys(run_dir: Path) -> set[tuple[str, int, str]]:
    """Read an existing traces.jsonl to skip already-finished (task, repeat, candidate)."""

    traces_path = run_dir / "traces.jsonl"
    done: set[tuple[str, int, str]] = set()
    if not traces_path.is_file():
        return done
    for line in traces_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        # Only a successful terminal row (or a non-retryable failure) completes a cell.
        status = int(row.get("http_status", 0))
        reason = row.get("fail_reason")
        terminal = (200 <= status < 300 and reason is None) or reason in {
            "throttle_exhausted",
            "timeout",
            "transport_error",
        } or (reason or "").startswith("http_")
        if terminal:
            done.add(_cell_key(row))
    return done


@dataclass(frozen=True)
class CellId:
    """The identity of one logical cell (task x repeat x arm) in plan order."""

    task_id: str
    repeat_idx: int
    model: str


@dataclass(frozen=True)
class RunHooks:
    """Optional per-cell seams so a caller can gate/observe the sweep.

    ``before_cell`` runs *before* a cell dispatches: return a non-empty
    halt-reason string to stop the sweep (the run seals ``partial = true`` with
    that reason, exactly like the budget-cap halt), or ``None`` to admit the
    dispatch. ``after_cell`` runs after a cell's rows are recorded. Both default
    to ``None``, so the measured CLI path is unchanged; the Cockpit injects
    gate-backed closures (03B :class:`SpendLedger` reservation-before-dispatch +
    :class:`AbortGate` admission) here rather than forking a second sweep loop.
    """

    before_cell: Callable[[CellId], str | None] | None = None
    after_cell: Callable[[CellId, list[dict[str, Any]]], None] | None = None


def run_measure(
    workload: Mapping[str, Mapping[str, Any]],
    candidates: Sequence[MeasureCandidate],
    *,
    client: MeasureClient,
    pricing: PricingTable | PricingEngine,
    exp_id: str,
    run_dir: Path | str,
    run_id: str | None = None,
    n: int = DEFAULT_N,
    budget_usd: float | None = None,
    retry: RetryPolicy | None = None,
    grader: Grader | None = None,
    prereg: PreregDecision | None = None,
    git_commit: str | None = None,
    endpoint: str | None = None,
    region: str | None = None,
    pricing_path: str | None = None,
    plan_hash: str | None = None,
    resume: bool = False,
    sleeper: Callable[[float], None] = sleep,
    clock: Callable[[], str] | None = None,
    now: datetime | None = None,
    progress: Callable[[Mapping[str, Any]], None] | None = None,
    hooks: RunHooks | None = None,
) -> MeasureRunResult:
    """Run a measured sweep and seal it into a §3 snapshot directory.

    Every call goes through the injected ``client`` seam, so this never egresses
    on its own — the live adapter (:class:`AzureMeasureClient`) is the only path
    that does, and only on ``--live``. Halts cleanly at ``budget_usd`` and writes
    a ``partial = true`` snapshot; resumes from an existing traces file.

    ``progress``, when given, is called once per finished cell (and once when a
    budget cap halts the run) with a small dict — ``cells_done``/``cells_total``,
    running spend vs. budget, throttle/failure tallies, and the last cell's
    identity. The cockpit (Phase C) streams these; it is a pure observer and
    never gates or mutates the run.
    """

    retry = retry or RetryPolicy()
    started = now or datetime.now(UTC)
    run_id = run_id or make_run_id(started)
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)

    engine = as_engine(pricing)
    already = _completed_keys(run_path) if resume else set()
    prior_rows: list[dict[str, Any]] = []
    if resume and (run_path / "traces.jsonl").is_file():
        # Keep only rows from cells that finished (terminal); drop any dangling
        # partial-retry rows from an interrupted cell so a resume never
        # double-counts a re-run attempt.
        prior_rows = [
            row
            for line in (run_path / "traces.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
            for row in [json.loads(line)]
            if _cell_key(row) in already
        ]

    candidate_models = [c.model for c in candidates]
    rows: list[dict[str, Any]] = list(prior_rows)
    running_cost = round(sum(float(r.get("cost_usd") or 0.0) for r in prior_rows), 6)
    partial = False
    stopped_reason: str | None = None
    cells_total = len(workload) * n * len(candidates)
    cells_done = len(already)
    throttles = 0
    failures = 0
    raw_records: list[dict[str, Any]] = []
    # Diagnostic-only mid-run tallies (per-arm content coverage + pass counts) so a
    # detached run can be watched for a coverage collapse. These are computed from
    # the same terminal rows that seal into traces, but they are carried ONLY on the
    # ephemeral progress event — never written to traces/summary/manifest and never
    # part of plan_hash. They inform an abort decision; they do not adjudicate.
    arm_progress: dict[str, dict[str, int]] = {
        m: {"attempted": 0, "content": 0, "passed": 0} for m in candidate_models
    }
    content_done = 0
    passed_done = 0
    if prior_rows:  # resume: seed from each cell's terminal row
        _terminal: dict[Any, dict[str, Any]] = {}
        for _r in prior_rows:
            _terminal[_cell_key(_r)] = _r
        for _r in _terminal.values():
            _seed = arm_progress.get(str(_r.get("candidate_model")))
            if _seed is None:
                continue
            _seed["attempted"] += 1
            if _r.get("output_sha256"):
                _seed["content"] += 1
                content_done += 1
            if _r.get("pass") is True:
                _seed["passed"] += 1
                passed_done += 1

    def _emit(**extra: Any) -> None:
        if progress is None:
            return
        progress(
            {
                "cells_done": cells_done,
                "cells_total": cells_total,
                "running_cost_usd": running_cost,
                "budget_usd": budget_usd,
                "throttles": throttles,
                "failures": failures,
                "graded_content": content_done,
                "passed": passed_done,
                "coverage": round(content_done / cells_done, 6) if cells_done else 0.0,
                "arms": {m: dict(st) for m, st in arm_progress.items()},
                **extra,
            }
        )

    for task_id in workload:
        task = workload[task_id]
        for repeat_idx in range(1, n + 1):
            for candidate in candidates:
                if (task_id, repeat_idx, candidate.model) in already:
                    continue
                if budget_usd is not None and running_cost >= budget_usd:
                    partial = True
                    stopped_reason = (
                        f"budget cap reached: ${running_cost:.6f} ≥ ${budget_usd:.6f}"
                    )
                    _emit(event="budget_halt", stopped_reason=stopped_reason)
                    break
                cell_id = CellId(task_id=task_id, repeat_idx=repeat_idx, model=candidate.model)
                if hooks is not None and hooks.before_cell is not None:
                    halt_reason = hooks.before_cell(cell_id)
                    if halt_reason:
                        partial = True
                        stopped_reason = halt_reason
                        _emit(event="halt", stopped_reason=stopped_reason)
                        break
                new_rows, final_result = run_candidate(
                    client, task, candidate,
                    run_id=run_id, exp_id=exp_id, repeat_idx=repeat_idx, pricing=engine,
                    retry=retry, grader=grader, sleeper=sleeper, clock=clock,
                )
                if hooks is not None and hooks.after_cell is not None:
                    hooks.after_cell(cell_id, new_rows)
                rows.extend(new_rows)
                # Retain the raw model output for later grader reruns (spec §9
                # L682). Kept only when a content grader hashed it, so ungraded /
                # offline runs never grow a raw_outputs/ directory.
                ok_row = new_rows[-1] if new_rows else {}
                out_sha = ok_row.get("output_sha256")
                if grader is not None and out_sha and final_result is not None:
                    raw_records.append(
                        {
                            "task_id": task_id,
                            "repeat_idx": repeat_idx,
                            "model": candidate.model,
                            "output_sha256": out_sha,
                            "pass": ok_row.get("pass"),
                            "content": final_result.content or "",
                        }
                    )
                running_cost = round(
                    running_cost + sum(float(r.get("cost_usd") or 0.0) for r in new_rows), 6
                )
                cells_done += 1
                throttles += sum(1 for r in new_rows if int(r.get("http_status", 0)) == 429)
                last = new_rows[-1] if new_rows else {}
                cell_failed = bool(last.get("fail_reason")) or not (
                    200 <= int(last.get("http_status", 0)) < 300
                )
                if cell_failed:
                    failures += 1
                arm_stat = arm_progress.get(candidate.model)
                if arm_stat is not None:
                    arm_stat["attempted"] += 1
                    if last.get("output_sha256"):
                        arm_stat["content"] += 1
                        content_done += 1
                    if last.get("pass") is True:
                        arm_stat["passed"] += 1
                        passed_done += 1
                _emit(
                    event="cell_done",
                    task_id=task_id,
                    repeat_idx=repeat_idx,
                    candidate=candidate.model,
                    http_status=int(last.get("http_status", 0)),
                    failed=cell_failed,
                )
            if partial:
                break
        if partial:
            break

    summary = compute_summary(
        rows, engine,
        exp_id=exp_id, run_id=run_id, n=n,
        task_ids=[str(r.get("task_id")) for r in rows],
        candidate_models=candidate_models, partial=partial,
        planned_cells=cells_total,
    )

    # Write payload files first, then fingerprint them into the manifest.
    traces_text = _dump_traces(rows)
    summary_text = _dumps(summary)
    pricing_text = engine.snapshot_yaml()
    prereg_text = _prereg_text(prereg)
    files = {
        "traces.jsonl": traces_text,
        "summary.json": summary_text,
        "pricing.snapshot.yaml": pricing_text,
        "prereg.md": prereg_text,
    }
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "plan_hash": plan_hash,
        "run_id": run_id,
        "exp_id": exp_id,
        "timestamp": started.isoformat(timespec="seconds"),
        "runner_version": MEASURE_RUNNER_VERSION,
        "git_commit": git_commit,
        "endpoint": endpoint,
        "region": region,
        "deployments": sorted({c.deployment for c in candidates}),
        "candidates": [
            {"model": c.model, "deployment": c.deployment, "provider": c.provider}
            for c in candidates
        ],
        "n": n,
        "budget_usd": budget_usd,
        "partial": partial,
        "stopped_reason": stopped_reason,
        "measured_cost_usd": summary["cost"]["total_usd"],
        "retry": retry.to_dict(),
        "pricing_path": pricing_path,
        "pricing_version": engine.version,
        "workload_fingerprint": workload_fingerprint(workload),
        "prereg": {
            "commit_hash": prereg.commit_hash if prereg else None,
            "committed_at": prereg.committed_at if prereg else None,
            "bypassed": bool(prereg.bypassed) if prereg else True,
            "note": prereg.note if prereg else "no prereg supplied",
        },
        "labels": {
            "measured": summary["labels"]["measured"],
            **(
                {"quality_graded": summary["labels"]["quality_graded"]}
                if "quality_graded" in summary["labels"]
                else {}
            ),
        },
        "fingerprints": _fingerprints(files),
    }
    (run_path / "traces.jsonl").write_text(traces_text, encoding="utf-8")
    (run_path / "summary.json").write_text(summary_text, encoding="utf-8")
    (run_path / "pricing.snapshot.yaml").write_text(pricing_text, encoding="utf-8")
    (run_path / "prereg.md").write_text(prereg_text, encoding="utf-8")
    (run_path / "manifest.json").write_text(_dumps(manifest), encoding="utf-8")
    _write_raw_outputs(run_path, raw_records)

    return MeasureRunResult(
        run_dir=run_path, run_id=run_id, exp_id=exp_id, summary=summary,
        manifest=manifest, partial=partial, stopped_reason=stopped_reason,
    )


def _write_raw_outputs(run_path: Path, raw_records: Sequence[Mapping[str, Any]]) -> None:
    """Persist captured model outputs for grader reruns, always gitignored.

    Raw prompts/outputs must never reach a public bundle or a commit (spec §9
    L682): only ``output_sha256`` and the grading verdict travel in traces. A
    ``.gitignore`` of ``*`` inside the directory guarantees the raw bytes stay
    local even if a run directory is created outside the ignored results tree.
    """

    if not raw_records:
        return
    raw_dir = run_path / "raw_outputs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / ".gitignore").write_text("*\n", encoding="utf-8")
    lines = [json.dumps(rec, sort_keys=True, ensure_ascii=False) for rec in raw_records]
    (raw_dir / "outputs.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _prereg_text(prereg: PreregDecision | None) -> str:
    if prereg and prereg.commit_hash:
        return (
            f"# Pre-registration (committed {prereg.committed_at}, "
            f"commit {prereg.commit_hash})\n\n"
            f"{prereg.note}\n"
        )
    note = prereg.note if prereg else "no prereg supplied"
    return f"# Pre-registration (not committed)\n\n{note}\n"


# --------------------------------------------------------------------------- #
# Deterministic replay (§3.4) — credential-free
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReplayResult:
    """Result of recomputing a snapshot's summary from its recorded traces."""

    run_dir: Path
    ok: bool
    summary_matches: bool
    fingerprints_ok: bool
    cost_mismatches: tuple[dict[str, Any], ...]
    fingerprint_issues: tuple[str, ...]
    recomputed_summary: dict[str, Any]
    plan_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_dir": str(self.run_dir),
            "ok": self.ok,
            "summary_matches": self.summary_matches,
            "fingerprints_ok": self.fingerprints_ok,
            "cost_mismatches": list(self.cost_mismatches),
            "fingerprint_issues": list(self.fingerprint_issues),
            "plan_hash": self.plan_hash,
        }


def replay_measure(run_dir: Path | str) -> ReplayResult:
    """Recompute ``summary.json`` from the snapshot alone and verify integrity.

    Credential-free and deterministic: reads ``traces.jsonl`` +
    ``pricing.snapshot.yaml``, recomputes the summary, and checks (a) it is
    byte-identical to the stored ``summary.json`` and (b) every file's SHA-256
    matches the manifest. This is the only thing CI runs for measured tracks.
    """

    path = Path(run_dir)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    traces_text = (path / "traces.jsonl").read_text(encoding="utf-8")
    pricing_text = (path / "pricing.snapshot.yaml").read_text(encoding="utf-8")
    stored_summary_text = (path / "summary.json").read_text(encoding="utf-8")
    prereg_text = (path / "prereg.md").read_text(encoding="utf-8")

    traces = [json.loads(line) for line in traces_text.splitlines() if line.strip()]
    engine = engine_from_snapshot(pricing_text)
    stored_summary = json.loads(stored_summary_text)

    stored_partial = bool(
        stored_summary.get("labels", {}).get("partial", manifest.get("partial", False))
    )
    recomputed = compute_summary(
        traces, engine,
        exp_id=stored_summary.get("exp_id", manifest.get("exp_id", "")),
        run_id=stored_summary.get("run_id", manifest.get("run_id", "")),
        n=int(stored_summary.get("n", manifest.get("n", 1))),
        task_ids=[str(r.get("task_id")) for r in traces],
        candidate_models=stored_summary.get("candidates", []),
        partial=stored_partial,
        planned_cells=stored_summary.get("grading", {}).get("planned_cells"),
    )
    recomputed_text = _dumps(recomputed)
    summary_matches = recomputed_text == stored_summary_text
    cost_mismatches = tuple(recomputed.get("integrity", {}).get("cost_mismatches", []))

    files = {
        "traces.jsonl": traces_text,
        "summary.json": stored_summary_text,
        "pricing.snapshot.yaml": pricing_text,
        "prereg.md": prereg_text,
    }
    recomputed_fps = _fingerprints(files)
    stored_fps = manifest.get("fingerprints", {})
    fingerprint_issues: list[str] = []
    for name, digest in recomputed_fps.items():
        if stored_fps.get(name) != digest:
            fingerprint_issues.append(name)
    fingerprints_ok = not fingerprint_issues
    ok = summary_matches and fingerprints_ok and not cost_mismatches
    return ReplayResult(
        run_dir=path,
        ok=ok,
        summary_matches=summary_matches,
        fingerprints_ok=fingerprints_ok,
        cost_mismatches=cost_mismatches,
        fingerprint_issues=tuple(fingerprint_issues),
        recomputed_summary=recomputed,
        plan_hash=manifest.get("plan_hash"),
    )


# --------------------------------------------------------------------------- #
# Publish (C8) — turn a sealed snapshot into a public-mockup bundle
# --------------------------------------------------------------------------- #


def build_publish_bundle(run_dir: Path | str) -> dict[str, Any]:
    """Transform a sealed snapshot into the JSON the public mockup (Phase D) reads.

    Keeps the measured **result** (costs, coverage, savings, tokens, latency,
    run date, commit, n, fingerprint) but drops tenant-specific rate-card data:
    the absolute ``pricing_path`` and the raw ``pricing.snapshot.yaml`` never
    ship, and the endpoint is redacted to host-only. Refuses to publish a
    snapshot that does not replay (the replay is the integrity gate), so a
    corrupted or hand-edited snapshot can never reach the public site.
    """

    from .foundry_live import _redact_endpoint

    path = Path(run_dir)
    report = replay_measure(path)
    if not report.ok:
        raise ValueError(
            f"refusing to publish {path}: snapshot does not replay "
            f"(summary_matches={report.summary_matches}, "
            f"fingerprints_ok={report.fingerprints_ok}, "
            f"cost_mismatches={len(report.cost_mismatches)})"
        )
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    labels = dict(summary.get("labels") or {})
    return {
        "schema": "cost-router/measured-publish/v1",
        "exp_id": summary.get("exp_id", manifest.get("exp_id")),
        "run_id": summary.get("run_id", manifest.get("run_id")),
        "captured_at": manifest.get("timestamp"),
        "git_commit": manifest.get("git_commit"),
        "n": summary.get("n", manifest.get("n")),
        "partial": bool(labels.get("partial", manifest.get("partial", False))),
        "workload_fingerprint": manifest.get("workload_fingerprint"),
        "deployments": manifest.get("deployments", summary.get("candidates", [])),
        "candidates": summary.get("candidates", []),
        "labels": labels,
        "result": {
            "cost": summary.get("cost"),
            "coverage": summary.get("coverage"),
            "grading": summary.get("grading"),
            "quality": summary.get("quality"),
            "tokens": summary.get("tokens"),
            "cache": summary.get("cache"),
            "latency_ms": summary.get("latency_ms"),
            "throttle": summary.get("throttle"),
            "failures": len(summary.get("failures", [])),
        },
        "provenance": {
            "measured": bool(labels.get("measured", manifest.get("labels", {}).get("measured"))),
            "endpoint": _redact_endpoint(manifest.get("endpoint")),
            "region": manifest.get("region"),
            "pricing": {
                "version": manifest.get("pricing_version"),
                "basis": labels.get("cost_basis", "list-price"),
                "note": "tenant rate card masked — absolute unit prices not published",
            },
            "replay_ok": report.ok,
            "summary_matches": report.summary_matches,
        },
    }


def publish_bundle_json(run_dir: Path | str) -> str:
    """Stable, byte-reproducible JSON for a publish bundle."""

    return _dumps(build_publish_bundle(run_dir))


def regrade_from_raw(
    run_dir: Path | str, benchmark_root: Path | str, *, timeout: int = 15
) -> dict[str, Any]:
    """Re-grade retained raw outputs and compare to the sealed verdicts.

    Publishability evidence (spec §9 L682): the private ``raw_outputs`` are the
    only thing that lets a reviewer rerun the grader. Re-grading them and
    checking the fresh verdict equals the ``pass`` sealed in the snapshot proves
    (a) the retention is complete and (b) the recorded grades were not fabricated
    — any edited ``pass`` shows up as a mismatch. Credential-free and offline.
    """

    from .benchmark_grader import ExecSignalsGrader

    path = Path(run_dir)
    raw_path = path / "raw_outputs" / "outputs.jsonl"
    if not raw_path.is_file():
        return {"available": False, "checked": 0, "matches": 0, "mismatches": [], "ok": True}

    grader = ExecSignalsGrader(benchmark_root, timeout=timeout)
    records = [
        json.loads(line)
        for line in raw_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matches = 0
    mismatches: list[dict[str, Any]] = []
    for rec in records:
        task_id = str(rec.get("task_id"))
        verdict = grader(
            task_id, {"task_id": task_id}, str(rec.get("model", "")), {}, rec.get("content")
        )
        sealed = rec.get("pass")
        if verdict.passed == sealed and verdict.output_sha256 == rec.get("output_sha256"):
            matches += 1
        else:
            mismatches.append(
                {
                    "task_id": task_id,
                    "repeat_idx": rec.get("repeat_idx"),
                    "sealed": sealed,
                    "regraded": verdict.passed,
                }
            )
    return {
        "available": True,
        "checked": len(records),
        "matches": matches,
        "mismatches": mismatches,
        "ok": not mismatches,
    }


# --------------------------------------------------------------------------- #
# Measured range-contract (§7.2) — validated over a replayed snapshot
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MeasuredContract:
    """Range/floor contract for a measured snapshot (never exact values)."""

    min_coverage: float | None = None
    min_savings_pct: float | None = None
    max_savings_pct: float | None = None
    max_tax_ratio: float | None = None
    min_escalation_gain: float | None = None
    max_failure_rate: float | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> MeasuredContract:
        data = data or {}

        def _opt(key: str) -> float | None:
            value = data.get(key)
            return None if value is None else float(value)

        return cls(
            min_coverage=_opt("min_coverage"),
            min_savings_pct=_opt("min_savings_pct"),
            max_savings_pct=_opt("max_savings_pct"),
            max_tax_ratio=_opt("max_tax_ratio"),
            min_escalation_gain=_opt("min_escalation_gain"),
            max_failure_rate=_opt("max_failure_rate"),
        )


@dataclass(frozen=True)
class ContractCheck:
    name: str
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


def verify_contract(
    summary: Mapping[str, Any],
    contract: MeasuredContract,
    *,
    manifest: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> list[ContractCheck]:
    """Check a measured snapshot's summary against range/floor bounds.

    Only bounds that are set are checked (like the offline ``Expectation``), so
    a partial contract is valid. Adds a non-fatal freshness warning when the
    snapshot's manifest timestamp is older than :data:`SNAPSHOT_FRESHNESS_DAYS`.
    """

    checks: list[ContractCheck] = []
    cost = summary.get("cost", {})
    coverage_block = summary.get("coverage")

    if contract.min_coverage is not None:
        coverage = None if coverage_block is None else float(coverage_block.get("coverage", 0.0))
        if coverage is None:
            checks.append(ContractCheck("coverage_floor", False, "ungraded (no grader supplied)"))
        else:
            checks.append(
                ContractCheck(
                    "coverage_floor", coverage >= contract.min_coverage,
                    f"{coverage:.1%} ≥ {contract.min_coverage:.1%}",
                )
            )
    if contract.min_savings_pct is not None:
        savings = float(cost.get("savings_pct", 0.0))
        checks.append(
            ContractCheck(
                "savings_floor", savings >= contract.min_savings_pct,
                f"{savings:.1f}% ≥ {contract.min_savings_pct:.1f}%",
            )
        )
    if contract.max_savings_pct is not None:
        savings = float(cost.get("savings_pct", 0.0))
        checks.append(
            ContractCheck(
                "savings_ceiling", savings <= contract.max_savings_pct,
                f"{savings:.1f}% ≤ {contract.max_savings_pct:.1f}%",
            )
        )
    if contract.max_tax_ratio is not None:
        priced = {
            m: v["total_usd"]
            for m, v in cost.get("by_candidate", {}).items()
            if v.get("calls", 0) > 0
        }
        smallest = min(priced.values()) if priced else 0.0
        tax_ratio = (max(priced.values()) / smallest) if smallest else 0.0
        checks.append(
            ContractCheck(
                "tax_ceiling", tax_ratio <= contract.max_tax_ratio,
                f"{tax_ratio:.2f}x ≤ {contract.max_tax_ratio:.2f}x",
            )
        )
    if contract.min_escalation_gain is not None:
        # Escalation gain requires a graded strategy comparison; when the snapshot
        # is ungraded this check is honestly not evaluable.
        strategies = summary.get("strategies") or {}
        single = strategies.get("single_call") or {}
        mix = strategies.get("mix") or {}
        if single and mix:
            gain = float(mix.get("coverage", 0.0)) - float(single.get("coverage", 0.0))
            checks.append(
                ContractCheck(
                    "escalation_gain", gain >= contract.min_escalation_gain,
                    f"+{gain:.1%} ≥ {contract.min_escalation_gain:.1%}",
                )
            )
        else:
            checks.append(
                ContractCheck(
                    "escalation_gain", False,
                    "no single_call/mix strategy block in snapshot (ungraded)",
                )
            )
    if contract.max_failure_rate is not None:
        attempts = int(summary.get("attempts", 0))
        failures = len(summary.get("failures", []))
        rate = (failures / attempts) if attempts else 0.0
        checks.append(
            ContractCheck(
                "failure_rate", rate <= contract.max_failure_rate,
                f"{rate:.1%} ≤ {contract.max_failure_rate:.1%}",
            )
        )

    if manifest is not None:
        stamp = manifest.get("timestamp")
        if isinstance(stamp, str):
            try:
                ts = datetime.fromisoformat(stamp)
                age_days = ((now or datetime.now(UTC)) - ts).days
                fresh = age_days <= SNAPSHOT_FRESHNESS_DAYS
                checks.append(
                    ContractCheck(
                        "freshness", fresh,
                        f"{age_days}d old (≤ {SNAPSHOT_FRESHNESS_DAYS}d)"
                        if fresh
                        else f"STALE: {age_days}d old (> {SNAPSHOT_FRESHNESS_DAYS}d)",
                    )
                )
            except ValueError:  # pragma: no cover - manifest always ISO
                pass
    return checks
