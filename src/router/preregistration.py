"""Preregistration contract with a non-circular hash order (BOLT-03B, step 5).

A benchmark's analysis choices must be fixed *before* results exist, and the
plan hash must bind the preregistration without a circular reference. The order
(from §8) is:

1. Normalize the execution-affecting draft WITHOUT prereg commit/blob fields and
   compute ``experiment_spec_hash``.
2. Write and commit the preregistration referencing that spec hash.
3. Resolve the clean prereg blob and commit.
4. Compute the final ``plan_hash`` from the spec hash plus the prereg evidence.
5. Present the final plan/hash for human approval.

Absolute local paths, wall-clock timestamps, locale, and display-only fields are
excluded from these hashes; normalized logical paths and content fingerprints
are included. A preregistration modified after the approved plan is rejected. A
``smoke`` run may bypass preregistration only with ``wiring_only=true`` and
``benchmark_eligible=false``; a ``benchmark`` can never bypass.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ledger.record import stable_hash

# Keys stripped from the execution-affecting draft before hashing: display-only,
# locale, and wall-clock/absolute-path fields never change the science.
_DISPLAY_KEYS = frozenset(
    {"locale", "display", "presentation", "local_root", "output_dir", "site_dir"}
)
VALID_ANALYSIS_UNITS = frozenset({"attempt", "task"})


def _strip_for_hash(value: Any) -> Any:
    """Recursively drop display/locale/wall-clock/absolute-path fields."""

    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            key_l = str(key).lower()
            if key_l in _DISPLAY_KEYS or key_l.endswith("_at") or key_l.endswith("_abs"):
                continue
            if key_l in {"timestamp", "captured_at", "created_at", "generated_at"}:
                continue
            cleaned[str(key)] = _strip_for_hash(item)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [_strip_for_hash(item) for item in value]
    return value


def experiment_spec_hash(draft: Mapping[str, Any]) -> str:
    """Step 1: hash the execution-affecting draft, excluding display-only fields.

    The draft MUST NOT contain preregistration commit/blob fields — this is what
    keeps the hash acyclic (the prereg references this hash, not vice versa).
    """

    return stable_hash(_strip_for_hash(dict(draft)))


@dataclass(frozen=True)
class PreregistrationBody:
    """The fixed analysis decisions + run bindings, sealed before results.

    Every field is chosen up front so no post-hoc aggregation (majority /
    any-pass / …) can be selected after seeing results.
    """

    experiment_spec_hash: str
    workload_fingerprint: str
    rate_card_hash: str
    arm_set: tuple[str, ...]
    repetitions: int
    grader: dict[str, Any]
    quality_gate: dict[str, Any]
    budget_usd: str
    estimand: str
    # Pre-result analysis decisions:
    analysis_unit: str  # "attempt" | "task"
    repeat_aggregation: str
    denominator: str
    failure_policy: str
    missing_cell_policy: str
    cost_per_pass_formula: str
    paired_statistic: str

    def validate(self) -> None:
        if self.analysis_unit not in VALID_ANALYSIS_UNITS:
            raise ValueError(
                f"analysis_unit must be one of {sorted(VALID_ANALYSIS_UNITS)}, "
                f"got {self.analysis_unit!r}"
            )
        required = {
            "repeat_aggregation": self.repeat_aggregation,
            "denominator": self.denominator,
            "failure_policy": self.failure_policy,
            "missing_cell_policy": self.missing_cell_policy,
            "cost_per_pass_formula": self.cost_per_pass_formula,
            "paired_statistic": self.paired_statistic,
            "estimand": self.estimand,
            "experiment_spec_hash": self.experiment_spec_hash,
            "workload_fingerprint": self.workload_fingerprint,
            "rate_card_hash": self.rate_card_hash,
        }
        missing = [name for name, val in required.items() if not str(val).strip()]
        if missing:
            raise ValueError(f"preregistration is missing required fields: {missing}")
        if not self.arm_set:
            raise ValueError("preregistration must bind a non-empty arm_set")
        if int(self.repetitions) <= 0:
            raise ValueError("preregistration repetitions must be positive")

    def to_canonical(self) -> dict[str, Any]:
        return {
            "experiment_spec_hash": self.experiment_spec_hash,
            "workload_fingerprint": self.workload_fingerprint,
            "rate_card_hash": self.rate_card_hash,
            "arm_set": list(self.arm_set),
            "repetitions": int(self.repetitions),
            "grader": dict(self.grader),
            "quality_gate": dict(self.quality_gate),
            "budget_usd": str(self.budget_usd),
            "estimand": self.estimand,
            "analysis_unit": self.analysis_unit,
            "repeat_aggregation": self.repeat_aggregation,
            "denominator": self.denominator,
            "failure_policy": self.failure_policy,
            "missing_cell_policy": self.missing_cell_policy,
            "cost_per_pass_formula": self.cost_per_pass_formula,
            "paired_statistic": self.paired_statistic,
        }

    def body_hash(self) -> str:
        return stable_hash(self.to_canonical())


@dataclass(frozen=True)
class PreregEvidence:
    """Clean, committed evidence resolved from the tracked prereg file."""

    blob_hash: str
    commit_hash: str
    committed_at: str


@dataclass(frozen=True)
class PreregOutcome:
    allowed: bool
    plan_hash: str | None
    experiment_spec_hash: str | None
    evidence: PreregEvidence | None
    note: str
    bypassed: bool = False


def final_plan_hash(
    spec_hash: str, evidence: PreregEvidence, body: PreregistrationBody
) -> str:
    """Step 4: bind spec hash + prereg body + clean blob/commit into one hash."""

    return stable_hash(
        {
            "experiment_spec_hash": spec_hash,
            "prereg_body_hash": body.body_hash(),
            "prereg_blob_hash": evidence.blob_hash,
            "prereg_commit": evidence.commit_hash,
        }
    )


# --------------------------------------------------------------------------- #
# git helpers (injectable so tests stay hermetic)
# --------------------------------------------------------------------------- #


def git_blob_hash(path: Path | str) -> str | None:
    """Working-tree blob hash of ``path`` (``git hash-object``)."""

    file_path = Path(path)
    try:
        out = subprocess.run(
            ["git", "hash-object", str(file_path)],
            cwd=file_path.parent if file_path.parent.exists() else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):  # pragma: no cover - git absent
        return None
    value = out.stdout.strip()
    return value or None


def git_tracked_and_clean(path: Path | str) -> bool:
    """True when ``path`` is tracked and has no uncommitted working-tree change."""

    file_path = Path(path)
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", str(file_path)],
            cwd=file_path.parent if file_path.parent.exists() else None,
            capture_output=True,
            text=True,
            check=False,
        )
        if tracked.returncode != 0:
            return False
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", str(file_path)],
            cwd=file_path.parent if file_path.parent.exists() else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):  # pragma: no cover - git absent
        return False
    return status.returncode == 0 and status.stdout.strip() == ""


# Injectable facts so the orchestration can be tested without real commits.
BlobHashFn = Callable[[Path | str], str | None]
CommittedFn = Callable[[Path | str], tuple[str, str] | None]
CleanFn = Callable[[Path | str], bool]


def resolve_preregistration(
    *,
    spec_hash: str,
    body: PreregistrationBody,
    prereg_path: Path | str | None,
    run_mode: str,
    wiring_only: bool = False,
    benchmark_eligible: bool = True,
    blob_hash_fn: BlobHashFn = git_blob_hash,
    committed_fn: CommittedFn | None = None,
    clean_fn: CleanFn = git_tracked_and_clean,
) -> PreregOutcome:
    """Steps 2–5: resolve clean prereg evidence and the final plan hash.

    ``benchmark`` never bypasses. ``smoke`` bypasses only when it is explicitly a
    wiring run (``wiring_only=true`` and ``benchmark_eligible=false``). A prereg
    file that is untracked, dirty, or whose committed spec hash disagrees with the
    draft fails closed.
    """

    from .measure import git_committed_at

    committed_fn = committed_fn or git_committed_at
    mode = str(run_mode or "").strip().lower()

    if prereg_path is None:
        if mode == "benchmark":
            return PreregOutcome(
                False, None, spec_hash, None,
                "benchmark mode requires a committed preregistration; it cannot bypass",
            )
        if wiring_only and not benchmark_eligible:
            return PreregOutcome(
                True, None, spec_hash, None,
                "wiring-only smoke (benchmark_eligible=false) may bypass preregistration",
                bypassed=True,
            )
        return PreregOutcome(
            False, None, spec_hash, None,
            "smoke may bypass preregistration only with wiring_only=true and "
            "benchmark_eligible=false",
        )

    path = Path(prereg_path)
    if not path.is_file():
        return PreregOutcome(False, None, spec_hash, None, f"prereg file not found: {path}")

    try:
        body.validate()
    except ValueError as exc:
        return PreregOutcome(False, None, spec_hash, None, f"invalid preregistration: {exc}")

    if body.experiment_spec_hash != spec_hash:
        return PreregOutcome(
            False, None, spec_hash, None,
            "preregistration was modified after the approved plan: its "
            f"experiment_spec_hash {body.experiment_spec_hash!r} != draft {spec_hash!r}",
        )

    if not clean_fn(path):
        return PreregOutcome(
            False, None, spec_hash, None,
            f"preregistration {path} must be tracked and clean (commit it first)",
        )

    committed = committed_fn(path)
    if committed is None:
        return PreregOutcome(
            False, None, spec_hash, None,
            f"preregistration {path} is not committed; commit it before the run",
        )
    commit_hash, committed_at = committed
    blob_hash = blob_hash_fn(path)
    if not blob_hash:
        return PreregOutcome(
            False, None, spec_hash, None, f"could not resolve a blob hash for {path}"
        )

    evidence = PreregEvidence(
        blob_hash=blob_hash, commit_hash=commit_hash, committed_at=committed_at
    )
    plan_hash = final_plan_hash(spec_hash, evidence, body)
    return PreregOutcome(
        True, plan_hash, spec_hash, evidence, "preregistration committed and bound"
    )


def verify_unmodified(
    *,
    prereg_path: Path | str,
    approved_blob_hash: str,
    blob_hash_fn: BlobHashFn = git_blob_hash,
) -> bool:
    """Reject a preregistration modified after the approved plan.

    Re-reads the current blob hash and compares it to the one bound at approval;
    any change means the file was edited post-approval.
    """

    current = blob_hash_fn(prereg_path)
    return bool(current) and current == approved_blob_hash
