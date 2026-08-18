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


def git_dir_and_path(path: Path | str) -> tuple[Path | None, Path]:
    """Normalize ``path`` to an absolute file and the directory to run git in.

    Every helper below shells out with ``cwd`` set to the file's own directory,
    so the path handed to git MUST be absolute. Passing a repo-relative path with
    a repo-relative ``cwd`` makes git resolve it twice (``a/b/a/b/file``), which
    fails and used to surface as ``None``/``False`` — indistinguishable from "the
    file is untracked". Resolving here keeps a caller's relative path working and
    keeps a real negative answer meaning what it says.
    """

    file_path = Path(path).expanduser().resolve()
    parent = file_path.parent
    return (parent if parent.is_dir() else None), file_path


def git_blob_hash(path: Path | str) -> str | None:
    """Working-tree blob hash of ``path`` (``git hash-object``).

    This hashes the bytes on disk, not any committed object, and it does not need
    a repository. It is therefore the wrong tool for verifying an approved
    preregistration — see :func:`verify_pinned_prereg`.
    """

    cwd, file_path = git_dir_and_path(path)
    try:
        out = subprocess.run(
            ["git", "hash-object", str(file_path)],
            cwd=cwd,
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

    cwd, file_path = git_dir_and_path(path)
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", str(file_path)],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if tracked.returncode != 0:
            return False
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", str(file_path)],
            cwd=cwd,
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
    """Compare the *working-tree* file against a blob hash bound at approval.

    .. warning::
       This is **not** the paid-dispatch tamper check, and it is deliberately not
       wired into one. It hashes the bytes currently on disk, so appending an
       errata section to a preregistration — recording what the implementation
       turned out to be, without touching a single approved character — reads as
       a violation here. This repository's practice is to keep the record and add
       a note, so a working-tree comparison is the wrong contract.

       :func:`verify_pinned_prereg` is the check that gates spend. It compares the
       *pinned git object*, which is content-addressed and therefore unreachable
       by any later append.
    """

    current = blob_hash_fn(prereg_path)
    return bool(current) and current == approved_blob_hash


# --------------------------------------------------------------------------- #
# Pinned-object verification — the check that gates paid dispatch
# --------------------------------------------------------------------------- #

#: The pinned commit holds exactly the declared blob for the declared path.
PREREG_VERIFIED = "verified"
#: The commit is readable here and does NOT hold the declared blob. Tampering.
PREREG_TAMPERED = "tampered"
#: The objects needed to check are not in this clone (shallow / no .git).
#: Not a verification failure — an absence of evidence, reported as such.
PREREG_EVIDENCE_UNAVAILABLE = "evidence_unavailable"
#: The plan pins a preregistration path but no blob+commit to check it against.
PREREG_INCOMPLETE_PIN = "incomplete_pin"
#: The plan pins no preregistration at all.
PREREG_NOT_PINNED = "not_pinned"


@dataclass(frozen=True)
class PinnedPreregVerdict:
    """What the pinned git objects say about the approved preregistration."""

    status: str
    declared_blob: str | None = None
    committed_blob: str | None = None
    declared_commit: str | None = None
    path: str | None = None
    detail: str = ""

    @property
    def verified(self) -> bool:
        return self.status == PREREG_VERIFIED


def _git_text(args: list[str], *, cwd: Path | None) -> tuple[int, str, str]:
    """Run git, returning ``(returncode, stdout, stderr)``; 127 when git is absent."""

    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    except (OSError, ValueError):  # pragma: no cover - git absent
        return 127, "", "git is not available"
    return out.returncode, out.stdout.strip(), out.stderr.strip()


def repo_relative_path(path: Path | str) -> str | None:
    """``path`` expressed relative to its repository root, or ``None`` if unknown.

    The pin is looked up as ``<commit>:<repo-relative-path>``, so the path written
    in the config (which is relative to the *config*, not necessarily the repo)
    can never be used directly.
    """

    cwd, file_path = git_dir_and_path(path)
    code, top, _ = _git_text(["git", "rev-parse", "--show-toplevel"], cwd=cwd)
    if code != 0 or not top:
        return None
    try:
        return file_path.relative_to(Path(top).resolve()).as_posix()
    except ValueError:
        return None


def verify_pinned_prereg(
    prereg_block: Mapping[str, Any] | None,
    *,
    resolved_path: Path | str | None = None,
) -> PinnedPreregVerdict:
    """Check the plan's pinned ``{path, blob, commit}`` against git's own objects.

    The subject is the **git object the approved plan pinned**, never the file in
    the working tree. Git objects are content-addressed, so a later append to the
    file cannot reach the pinned blob: the approved bytes stay exactly as approved
    and stay independently retrievable with ``git show <commit>:<path>``.

    The two failure modes are kept apart on purpose:

    ``PREREG_TAMPERED``
        The commit is readable here and its tree holds a different blob (or no
        entry) for that path. The declaration and the history disagree.

    ``PREREG_EVIDENCE_UNAVAILABLE``
        The commit is not in this clone — a shallow clone or a ``.git``-less
        source export. Nothing suggests the preregistration was modified; the
        evidence simply is not here to look at.
    """

    block = dict(prereg_block or {})
    declared_path = str(block.get("path") or "").strip()
    if not declared_path:
        return PinnedPreregVerdict(
            PREREG_NOT_PINNED, detail="the plan pins no preregistration"
        )

    declared_blob = str(block.get("blob") or "").strip()
    declared_commit = str(block.get("commit") or "").strip()
    if not declared_blob or not declared_commit:
        missing = [
            name
            for name, value in (("blob", declared_blob), ("commit", declared_commit))
            if not value
        ]
        return PinnedPreregVerdict(
            PREREG_INCOMPLETE_PIN,
            declared_blob=declared_blob or None,
            declared_commit=declared_commit or None,
            path=declared_path,
            detail=f"the pin is missing {' and '.join(missing)}",
        )

    target = Path(resolved_path) if resolved_path else Path(declared_path)
    cwd, _ = git_dir_and_path(target)

    # Is there a repository here at all?
    code, _, _ = _git_text(["git", "rev-parse", "--git-dir"], cwd=cwd)
    if code != 0:
        return PinnedPreregVerdict(
            PREREG_EVIDENCE_UNAVAILABLE,
            declared_blob=declared_blob,
            declared_commit=declared_commit,
            path=declared_path,
            detail="there is no git repository here (a source export / zip download "
            "carries no history)",
        )

    # Is the pinned commit itself present? A shallow clone has the files but not
    # the history, and that must not be reported as a mismatch.
    code, _, _ = _git_text(
        ["git", "cat-file", "-e", f"{declared_commit}^{{commit}}"], cwd=cwd
    )
    if code != 0:
        shallow = _git_text(["git", "rev-parse", "--is-shallow-repository"], cwd=cwd)[1]
        reason = (
            "this is a shallow clone, so the pinned commit was never fetched"
            if shallow == "true"
            else "the pinned commit is not present in this clone"
        )
        return PinnedPreregVerdict(
            PREREG_EVIDENCE_UNAVAILABLE,
            declared_blob=declared_blob,
            declared_commit=declared_commit,
            path=declared_path,
            detail=reason,
        )

    lookup = repo_relative_path(target) or declared_path
    # Reads the commit's tree only; the blob's *content* need not be present, so
    # this still works in a blobless partial clone.
    code, committed_blob, stderr = _git_text(
        ["git", "rev-parse", f"{declared_commit}:{lookup}"], cwd=cwd
    )
    if code != 0 or not committed_blob:
        return PinnedPreregVerdict(
            PREREG_TAMPERED,
            declared_blob=declared_blob,
            committed_blob=None,
            declared_commit=declared_commit,
            path=lookup,
            detail=f"the pinned commit has no {lookup!r} in its tree ({stderr or 'no entry'})",
        )

    if committed_blob != declared_blob:
        return PinnedPreregVerdict(
            PREREG_TAMPERED,
            declared_blob=declared_blob,
            committed_blob=committed_blob,
            declared_commit=declared_commit,
            path=lookup,
            detail="the pinned commit holds a different blob for that path",
        )

    return PinnedPreregVerdict(
        PREREG_VERIFIED,
        declared_blob=declared_blob,
        committed_blob=committed_blob,
        declared_commit=declared_commit,
        path=lookup,
        detail="the pinned commit holds exactly the declared blob",
    )


# --------------------------------------------------------------------------- #
# The paid-dispatch gate
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DispatchGate:
    """Verdict of the preregistration gate on a path that is about to spend money."""

    allowed: bool
    status: str
    summary: str
    refusal: str = ""
    verdict: PinnedPreregVerdict | None = None
    commit_hash: str | None = None
    committed_at: str | None = None


def _sentence(text: str) -> str:
    """Capitalize a ``detail`` clause so it can start a line of operator prose."""

    return (text[:1].upper() + text[1:]) if text else text


def _tampered_refusal(label: str, verdict: PinnedPreregVerdict) -> str:
    held = verdict.committed_blob or "(no entry for that path)"
    return "\n".join(
        [
            f"{label}: refusing to dispatch — the approved preregistration does not "
            "match the git history.",
            f"    path          : {verdict.path}",
            f"    pinned commit : {verdict.declared_commit}",
            f"    plan declares : blob {verdict.declared_blob}",
            f"    commit holds  : {held}",
            f"  {_sentence(verdict.detail)}. The objects were read successfully, so "
            "this is a mismatch and not a missing-evidence problem: what the "
            "approved plan says was preregistered is not what was committed.",
            "  Nothing in your working tree was compared — appending an errata "
            "section to a preregistration cannot cause this.",
            "  Re-resolve the plan, re-read what it pins, and take a fresh approval "
            "before spending.",
        ]
    )


def _unavailable_refusal(label: str, verdict: PinnedPreregVerdict) -> str:
    return "\n".join(
        [
            f"{label}: refusing to dispatch — this clone cannot show the approved "
            "preregistration.",
            f"    path          : {verdict.path}",
            f"    pinned commit : {verdict.declared_commit}",
            f"    plan declares : blob {verdict.declared_blob}",
            "  This is NOT a verification failure: nothing here says the "
            "preregistration was modified. There is simply no object to compare "
            f"against — {verdict.detail}.",
            "  Fetch the history and re-run:",
            "      git fetch --unshallow      # or: git clone without --depth",
            "  (a source zip / `git archive` export has no history at all — clone "
            "the repository instead).",
            "  Only paid dispatch needs this. `benchmark plan`, `measure replay`, "
            "the docs build and the test suite all run fine in a shallow or "
            ".git-less tree.",
        ]
    )



def prereg_dispatch_gate(
    prereg_block: Mapping[str, Any] | None,
    *,
    resolved_path: Path | str | None,
    run_started_at: Any,
    run_mode: str,
    label: str,
    verify_fn: Callable[..., PinnedPreregVerdict] = verify_pinned_prereg,
    evaluate_fn: Callable[..., Any] | None = None,
) -> DispatchGate:
    """Fail closed unless the approved preregistration is both pinned and prior.

    Two conditions, one gate. They fail in different ways and so are checked
    separately, but neither may be waived — there is no bypass flag on this path.

    1. **Identity.** ``git rev-parse <commit>:<path>`` must hand back the blob the
       approved plan declared. The subject is the pinned object, not the working
       tree, so a later errata append is not a violation and a rewrite of history
       is.
    2. **Priority in time.** The same :func:`~router.measure.evaluate_prereg` that
       the plan-bound cockpit already enforces must agree the file was committed
       before this run started. Sharing that function is the point: entry points
       that disagree about what counts as preregistered would be worse than none
       of them checking.

    ``run_mode == "benchmark"`` additionally may not dispatch with no pin at all.
    A gate that a deleted YAML block switches off is not a gate; the module has
    said "benchmark ... cannot bypass" since it was written, and this is where
    that sentence finally costs something.
    """

    from .measure import evaluate_prereg

    evaluate = evaluate_fn or evaluate_prereg
    mode = str(run_mode or "").strip().lower()
    verdict = verify_fn(prereg_block, resolved_path=resolved_path)

    if verdict.status == PREREG_NOT_PINNED:
        if mode == "benchmark":
            return DispatchGate(
                False,
                PREREG_NOT_PINNED,
                "no preregistration pinned",
                refusal=(
                    f"{label}: refusing to dispatch — this plan pins no "
                    "preregistration.\n"
                    "  A benchmark run cannot bypass preregistration: its analysis "
                    "choices have to be fixed, committed and hashed into the plan "
                    "before any result exists, or the numbers it produces cannot be "
                    "told apart from ones chosen after the fact.\n"
                    "  Add benchmark.preregistration: {path, blob, commit} to the run "
                    "config, commit the preregistration first, then re-approve the "
                    "resulting plan_hash."
                ),
                verdict=verdict,
            )
        return DispatchGate(
            True, PREREG_NOT_PINNED, "no preregistration pinned (wiring smoke)",
            verdict=verdict,
        )

    if verdict.status == PREREG_TAMPERED:
        return DispatchGate(
            False, PREREG_TAMPERED, "pinned blob does not match the pinned commit",
            refusal=_tampered_refusal(label, verdict), verdict=verdict,
        )

    if verdict.status == PREREG_EVIDENCE_UNAVAILABLE:
        return DispatchGate(
            False, PREREG_EVIDENCE_UNAVAILABLE, "pinned objects are not in this clone",
            refusal=_unavailable_refusal(label, verdict), verdict=verdict,
        )

    if verdict.status == PREREG_INCOMPLETE_PIN:
        return DispatchGate(
            False, PREREG_INCOMPLETE_PIN, "the pin is incomplete",
            refusal=(
                f"{label}: refusing to dispatch — {verdict.detail}, so there is "
                "nothing to verify the preregistration against.\n"
                f"    path          : {verdict.path}\n"
                "  Resolve the plan against a committed preregistration so the blob "
                "and commit are filled in, then re-approve."
            ),
            verdict=verdict,
        )

    decision = evaluate(
        Path(resolved_path) if resolved_path else Path(str(verdict.path)),
        run_started_at=run_started_at,
        allow_no_prereg=False,
    )
    if not decision.allowed:
        return DispatchGate(
            False, "not_committed_before_run", "committed too late (or not at all)",
            refusal=(
                f"{label}: refusing to dispatch — the preregistration is not older "
                f"than this run.\n"
                f"  {decision.note}\n"
                "  The commit timestamp is what makes a preregistration evidence "
                "rather than a description; a file written or committed after the "
                "run began proves nothing about what was predicted.\n"
                "  There is no bypass on this path: commit the preregistration, "
                "re-resolve the plan, and approve the new plan_hash."
            ),
            verdict=verdict,
            commit_hash=decision.commit_hash,
            committed_at=decision.committed_at,
        )

    return DispatchGate(
        True,
        PREREG_VERIFIED,
        f"verified against {verdict.declared_commit[:12]}"
        if verdict.declared_commit
        else "verified",
        verdict=verdict,
        commit_hash=decision.commit_hash,
        committed_at=decision.committed_at,
    )

