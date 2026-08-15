"""The preregistration gate that stands in front of paid dispatch.

Before this suite existed, ``benchmark run --live`` resolved a preregistration,
wrote the verdict into the sealed manifest, and dispatched regardless of what the
verdict said. The pinned blob had no reader at all. Two ways to spend money on a
preregistration that did not hold were therefore open at once: pin a blob that
was never committed, or never commit the file.

What is checked here is the **pinned git object**, never the file in the working
tree. That distinction is the whole design. All three preregistrations in this
repository have had errata appended to them since their runs sealed — recording
what the implementation turned out to be, without altering one approved character
— so a working-tree comparison would now report every sealed run as tampered.
``git show <commit>:<path>`` still returns exactly the approved bytes, because
git objects are immutable and an append cannot reach backwards.

The other half is telling two failures apart. A blob that disagrees with its
commit is tampering. A blob that cannot be looked up *at all*, because the clone
is shallow or has no ``.git``, is an absence of evidence — a different sentence,
a different remedy, and never phrased as a verification failure.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from router import cli
from router.measure import AttemptResult, git_committed_at, replay_measure
from router.preregistration import (
    PREREG_EVIDENCE_UNAVAILABLE,
    PREREG_INCOMPLETE_PIN,
    PREREG_NOT_PINNED,
    PREREG_TAMPERED,
    PREREG_VERIFIED,
    git_blob_hash,
    git_tracked_and_clean,
    prereg_dispatch_gate,
    verify_pinned_prereg,
)
from router.run_plan import LocalRunConfig, execute_benchmark, resolve_run_plan

ROOT = Path(__file__).resolve().parents[1]
SMOKE_WORKLOAD = ROOT / "samples/workloads/validated-smoke.example.jsonl"

#: The three sealed 03D runs: ``(run_id, prereg file, approval commit, pinned blob)``.
#: Commits come from each run's ``manifest.json`` (``prereg.commit_hash``); blobs are
#: what those commits hold for that path. Every one of these files has since had an
#: errata section appended, which is exactly why they are pinned here.
SEALED_RUNS: tuple[tuple[str, str, str, str], ...] = (
    (
        "20260806T023822Z",
        "benchmarks/original-coding/prereg-03d-router-modes.md",
        "1f0a334104d50dc74116a20071dffb3fa4b3d66a",
        "2b9afe6706c7070ecdd4dffbe7e39814ff481e7a",
    ),
    (
        "20260806T075344Z",
        "benchmarks/original-coding/prereg-03d2-router-modes.md",
        "ea3a55165dd0cfaccbe965019b7197e4675b78ca",
        "4158ca8ab1b5cda4290e289c1d27a68114e58e9a",
    ),
    (
        "20260814T141510Z",
        "benchmarks/original-coding/prereg-03d3-router-modes.md",
        "454c8159e6e3666a6b24982ef30766ea73059f22",
        "8584e1f8c6031d7be6b03d01a9e292c83d57bab5",
    ),
)

FUTURE = datetime(2099, 1, 1, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Fixtures: real git repositories, because the thing under test is git
# --------------------------------------------------------------------------- #


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        [
            "git",
            "-c", "user.name=prereg-test",
            "-c", "user.email=prereg-test@example.invalid",
            "-c", "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    return path


def _commit(repo: Path, relative: str, text: str, message: str) -> tuple[str, str]:
    """Write, commit, and return ``(commit_hash, blob_hash)`` for ``relative``."""

    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _git(repo, "add", "--", relative)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD"), _git(repo, "rev-parse", f"HEAD:{relative}")


@pytest.fixture
def pinned_repo(tmp_path: Path) -> dict[str, Any]:
    """A repo with a committed preregistration and the pin a plan would carry."""

    repo = _init_repo(tmp_path / "repo")
    commit, blob = _commit(repo, "prereg.md", "# preregistration\nas approved\n", "prereg")
    return {
        "repo": repo,
        "path": repo / "prereg.md",
        "pin": {"path": "prereg.md", "blob": blob, "commit": commit},
    }


def _has_history(commit: str) -> bool:
    """Whether this checkout actually carries ``commit`` (a full clone does)."""

    return subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).returncode == 0


# --------------------------------------------------------------------------- #
# The relative-path defect in the three git helpers
# --------------------------------------------------------------------------- #


def test_git_helpers_give_the_same_answer_from_a_relative_path(
    pinned_repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repo-relative path must not read as "untracked".

    Each helper shells out with ``cwd`` set to the file's own directory. Handing
    git a repo-relative path as well made it resolve the path twice, and the
    resulting failure surfaced as ``None``/``False`` — indistinguishable from a
    real negative. With the gate wired, that would have made a path typo and a
    tamper signal look identical to whoever read the refusal.
    """

    absolute = pinned_repo["path"]
    monkeypatch.chdir(pinned_repo["repo"])

    assert git_blob_hash("prereg.md") == git_blob_hash(absolute) == pinned_repo["pin"]["blob"]
    assert git_tracked_and_clean("prereg.md") is git_tracked_and_clean(absolute) is True

    relative_commit = git_committed_at("prereg.md")
    assert relative_commit is not None
    assert relative_commit == git_committed_at(absolute)
    assert relative_commit[0] == pinned_repo["pin"]["commit"]


def test_a_genuinely_untracked_file_still_reads_as_untracked(
    pinned_repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of the fix: normalizing paths must not soften a real answer."""

    (pinned_repo["repo"] / "scratch.md").write_text("not committed\n", encoding="utf-8")
    monkeypatch.chdir(pinned_repo["repo"])

    assert git_tracked_and_clean("scratch.md") is False
    assert git_committed_at("scratch.md") is None
    # hash-object needs no repository at all, so it still answers.
    assert git_blob_hash("scratch.md")


# --------------------------------------------------------------------------- #
# verify_pinned_prereg — the pinned object, not the working tree
# --------------------------------------------------------------------------- #


def test_a_matching_pin_verifies(pinned_repo: dict[str, Any]) -> None:
    verdict = verify_pinned_prereg(pinned_repo["pin"], resolved_path=pinned_repo["path"])
    assert verdict.status == PREREG_VERIFIED
    assert verdict.verified is True
    assert verdict.committed_blob == pinned_repo["pin"]["blob"]


def test_appending_to_the_file_does_not_break_the_pin(pinned_repo: dict[str, Any]) -> None:
    """The errata case, in miniature. This is the reason for object comparison."""

    pinned_repo["path"].write_text(
        "# preregistration\nas approved\n\n## Errata (2026-08-14)\nwritten later\n",
        encoding="utf-8",
    )
    # The working tree has genuinely moved…
    assert git_blob_hash(pinned_repo["path"]) != pinned_repo["pin"]["blob"]
    # …and the approved object is untouched, because objects cannot be appended to.
    assert verify_pinned_prereg(
        pinned_repo["pin"], resolved_path=pinned_repo["path"]
    ).status == PREREG_VERIFIED


def test_a_blob_that_was_never_committed_is_tampering(pinned_repo: dict[str, Any]) -> None:
    pin = {**pinned_repo["pin"], "blob": "0" * 40}
    verdict = verify_pinned_prereg(pin, resolved_path=pinned_repo["path"])
    assert verdict.status == PREREG_TAMPERED
    assert verdict.committed_blob == pinned_repo["pin"]["blob"]


def test_a_path_missing_from_the_pinned_commit_is_tampering(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    first, _ = _commit(repo, "other.md", "unrelated\n", "first")
    _, blob = _commit(repo, "prereg.md", "# preregistration\n", "prereg")
    verdict = verify_pinned_prereg(
        {"path": "prereg.md", "blob": blob, "commit": first},
        resolved_path=repo / "prereg.md",
    )
    assert verdict.status == PREREG_TAMPERED
    assert verdict.committed_blob is None


def test_a_shallow_clone_reports_absent_evidence_not_a_mismatch(tmp_path: Path) -> None:
    """The exact shape of this repository's own CI before ``fetch-depth: 0``."""

    origin = _init_repo(tmp_path / "origin")
    approval, blob = _commit(origin, "prereg.md", "# preregistration\n", "prereg")
    _commit(origin, "prereg.md", "# preregistration\n\n## Errata\nlater\n", "errata")

    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", origin.as_uri(), str(shallow)],
        capture_output=True, text=True, check=True,
    )
    # The file is present; the commit that pins it is not.
    assert (shallow / "prereg.md").is_file()

    verdict = verify_pinned_prereg(
        {"path": "prereg.md", "blob": blob, "commit": approval},
        resolved_path=shallow / "prereg.md",
    )
    assert verdict.status == PREREG_EVIDENCE_UNAVAILABLE
    assert "shallow" in verdict.detail


def test_a_tree_without_git_reports_absent_evidence(pinned_repo: dict[str, Any]) -> None:
    """A source zip or ``git archive`` export: files, no history."""

    export = pinned_repo["repo"].parent / "export"
    export.mkdir()
    (export / "prereg.md").write_text(
        pinned_repo["path"].read_text(encoding="utf-8"), encoding="utf-8"
    )
    verdict = verify_pinned_prereg(pinned_repo["pin"], resolved_path=export / "prereg.md")
    assert verdict.status == PREREG_EVIDENCE_UNAVAILABLE
    assert "no git repository" in verdict.detail


def test_an_absent_or_partial_pin_is_classified_separately(pinned_repo: dict[str, Any]) -> None:
    assert verify_pinned_prereg(None).status == PREREG_NOT_PINNED
    assert verify_pinned_prereg({}).status == PREREG_NOT_PINNED
    partial = {"path": "prereg.md", "blob": pinned_repo["pin"]["blob"], "commit": None}
    verdict = verify_pinned_prereg(partial, resolved_path=pinned_repo["path"])
    assert verdict.status == PREREG_INCOMPLETE_PIN
    assert "commit" in verdict.detail


# --------------------------------------------------------------------------- #
# The gate: both conditions, no bypass
# --------------------------------------------------------------------------- #


def _gate(pinned: dict[str, Any], **overrides: Any):
    kwargs: dict[str, Any] = {
        "resolved_path": pinned["path"],
        "run_started_at": FUTURE,
        "run_mode": "benchmark",
        "label": "benchmark run --live",
    }
    kwargs.update(overrides)
    block = kwargs.pop("prereg_block", pinned["pin"])
    return prereg_dispatch_gate(block, **kwargs)


def test_a_verified_pin_committed_first_passes(pinned_repo: dict[str, Any]) -> None:
    gate = _gate(pinned_repo)
    assert gate.allowed is True
    assert gate.status == PREREG_VERIFIED
    assert gate.refusal == ""
    assert gate.commit_hash == pinned_repo["pin"]["commit"]


def test_tampering_refuses_and_says_so_without_blaming_the_clone(
    pinned_repo: dict[str, Any],
) -> None:
    gate = _gate(pinned_repo, prereg_block={**pinned_repo["pin"], "blob": "0" * 40})
    assert gate.allowed is False
    assert gate.status == PREREG_TAMPERED
    assert "does not match the git history" in gate.refusal
    assert "The objects were read successfully" in gate.refusal
    # It must not send the reader off to fix their clone…
    assert "unshallow" not in gate.refusal
    # …and it must not let an errata append be read as the cause.
    assert "Nothing in your working tree was compared" in gate.refusal


def test_absent_evidence_refuses_but_is_not_called_a_verification_failure(
    pinned_repo: dict[str, Any],
) -> None:
    export = pinned_repo["repo"].parent / "export"
    export.mkdir()
    (export / "prereg.md").write_text("# preregistration\n", encoding="utf-8")

    gate = _gate(pinned_repo, resolved_path=export / "prereg.md")
    assert gate.allowed is False
    assert gate.status == PREREG_EVIDENCE_UNAVAILABLE
    assert "This is NOT a verification failure" in gate.refusal
    assert "git fetch --unshallow" in gate.refusal
    assert "does not match the git history" not in gate.refusal
    # It has to name what still works, or the remedy reads as "give up".
    assert "measure replay" in gate.refusal


def test_an_uncommitted_preregistration_refuses(tmp_path: Path) -> None:
    """Fork 2: pinning is not enough on its own, the commit has to come first."""

    repo = _init_repo(tmp_path / "repo")
    commit, blob = _commit(repo, "prereg.md", "# preregistration\n", "prereg")
    committed_at = git_committed_at(repo / "prereg.md")
    assert committed_at is not None

    gate = prereg_dispatch_gate(
        {"path": "prereg.md", "blob": blob, "commit": commit},
        resolved_path=repo / "prereg.md",
        # The run began a day before the preregistration was committed.
        run_started_at=datetime.fromisoformat(committed_at[1]) - timedelta(days=1),
        run_mode="benchmark",
        label="benchmark run --live",
    )
    assert gate.allowed is False
    assert gate.status == "not_committed_before_run"
    assert "not older than this run" in gate.refusal
    assert "There is no bypass on this path" in gate.refusal


def test_a_deleted_preregistration_refuses_even_though_the_object_verifies(
    pinned_repo: dict[str, Any],
) -> None:
    """The two conditions are independent, and both have to hold.

    The pinned object is still in the repository — history cannot be deleted by
    removing a file — so the identity check passes. The timestamp check does not:
    there is nothing on disk that the run can claim to have preregistered.
    """

    pinned_repo["path"].unlink()
    assert verify_pinned_prereg(
        pinned_repo["pin"], resolved_path=pinned_repo["path"]
    ).status == PREREG_VERIFIED

    gate = _gate(pinned_repo)
    assert gate.allowed is False
    assert gate.status == "not_committed_before_run"
    assert "prereg file not found" in gate.refusal



def test_a_benchmark_with_no_pin_at_all_refuses(pinned_repo: dict[str, Any]) -> None:
    """Otherwise deleting one YAML block is the bypass flag we said we would not add."""

    gate = _gate(pinned_repo, prereg_block=None, resolved_path=None)
    assert gate.allowed is False
    assert gate.status == PREREG_NOT_PINNED
    assert "cannot bypass preregistration" in gate.refusal


def test_a_wiring_smoke_with_no_pin_still_runs(pinned_repo: dict[str, Any]) -> None:
    """Unchanged behaviour: a smoke run is a wiring check, not a measurement."""

    gate = _gate(pinned_repo, prereg_block=None, resolved_path=None, run_mode="smoke")
    assert gate.allowed is True


def test_the_gate_shares_its_timestamp_judgment_with_the_other_enforcers(
    pinned_repo: dict[str, Any],
) -> None:
    """``measure run --live`` and the cockpit call the same function, by injection.

    Three entry points that disagreed about what counts as preregistered would be
    worse than one that checked. The gate takes ``evaluate_fn`` for tests only —
    production always gets :func:`router.measure.evaluate_prereg`.
    """

    seen: list[dict[str, Any]] = []

    def _spy(path, **kwargs):
        seen.append({"path": Path(path), **kwargs})
        from router.measure import evaluate_prereg

        return evaluate_prereg(path, **kwargs)

    gate = _gate(pinned_repo, evaluate_fn=_spy)
    assert gate.allowed is True
    assert len(seen) == 1
    assert seen[0]["path"] == pinned_repo["path"]
    # Fork 1: no bypass flag reaches this path, ever.
    assert seen[0]["allow_no_prereg"] is False


# --------------------------------------------------------------------------- #
# The three sealed 03D runs, as this repository stands today
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("run_id,rel_path,commit,blob", SEALED_RUNS)
def test_sealed_runs_still_verify_after_their_errata(
    run_id: str, rel_path: str, commit: str, blob: str
) -> None:
    """The case the whole design exists for.

    Each of these preregistrations has an errata section appended after its run
    sealed. The approved object still verifies; the file on disk no longer hashes
    to the pinned blob. A working-tree check would call all three tampered.
    """

    if not _has_history(commit):
        pytest.skip(f"{commit[:12]} is not in this checkout (shallow clone)")

    pin = {"path": rel_path, "blob": blob, "commit": commit}
    verdict = verify_pinned_prereg(pin, resolved_path=ROOT / rel_path)
    assert verdict.status == PREREG_VERIFIED, verdict.detail

    assert git_blob_hash(ROOT / rel_path) != blob, (
        f"{rel_path} now hashes to the blob its run pinned, so this test no longer "
        "proves that an appended errata survives verification."
    )


def test_the_sealed_commit_hashes_are_the_ones_the_manifests_recorded() -> None:
    """Keep :data:`SEALED_RUNS` honest against the artifacts it claims to describe."""

    for run_id, _rel_path, commit, _blob in SEALED_RUNS:
        manifest_path = ROOT / "results/local/03d/run" / run_id / "manifest.json"
        if not manifest_path.is_file():  # pragma: no cover - sealed runs are local
            pytest.skip(f"{manifest_path} is not present in this checkout")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["prereg"]["commit_hash"] == commit
        assert manifest["prereg"]["bypassed"] is False


# --------------------------------------------------------------------------- #
# CLI wiring: the gate stands in front of the client, and only there
# --------------------------------------------------------------------------- #


class _FakeClient:
    def attempt(self, *, deployment: str, provider: str, task: dict[str, Any]) -> AttemptResult:
        return AttemptResult(
            http_status=200, model=deployment,
            usage={"input": 1000, "cached": 0, "output": 400, "reasoning": 0},
            latency_ms=10.0, provenance="live",
        )


def _rate_card(base: Path) -> None:
    (base / "tenant-rates.yaml").write_text(
        "version: 7\n"
        "currency: USD\n"
        "source: acme-tenant\n"
        "effective_date: 2026-08-01\n"
        "pricing_basis: composite\n"
        "models:\n"
        "  model-router: {input: 3.0, cached: 1.5, output: 10.0, reasoning: 10.0}\n"
        "  premium-max: {input: 5.0, cached: 2.5, output: 15.0, reasoning: 15.0}\n"
        "default: {input: 1.0, cached: 0.5, output: 2.0, reasoning: 2.0}\n",
        encoding="utf-8",
    )


def _config_mapping(prereg: dict[str, Any] | None) -> dict[str, Any]:
    mapping: dict[str, Any] = {
        "schema_version": 1,
        "template": False,
        "run_mode": "benchmark",
        "foundry": {
            "auth": "entra",
            "endpoint_kind": "azure_openai",
            "azure_openai_endpoint": "https://acme-res.example.com/",
            "api_version": "2024-10-21",
        },
        "arms": [
            {
                "id": "router-cost", "kind": "model_router", "provider": "openai",
                "requested_model": "model-router", "deployment": "model-router",
                "expected": {"format": "router", "name": "cost", "version": "2025-01"},
            },
            {
                "id": "direct-premium", "kind": "direct", "provider": "openai",
                "requested_model": "premium-max", "deployment": "premium-max",
            },
        ],
        "benchmark": {
            # Config-relative on purpose: the plan hashes these strings verbatim,
            # so an absolute path would make plan_hash differ per machine and the
            # invariance test below could not pin a literal.
            "workload": "workload.jsonl",
            "rate_card": "tenant-rates.yaml",
            "smoke_authorization_ceiling_usd": None,
            "repetitions": 2,
            "max_output_tokens": 256,
            "budget_usd": 5.0,
            "random_seed": 7,
            "estimand": {
                "analysis_unit": "task",
                "repeat_aggregation": "mean",
                "denominator_policy": "all-attempted",
                "failure_policy": "count-as-zero",
                "cost_per_pass_formula": "total_cost / passes",
                "paired_statistic": "wilcoxon",
            },
            "grader": {"kind": "exec-signals", "version": 1},
            "retry": {"max_retries": 3},
            "preregistration": prereg,
        },
        "privacy": {"retain_raw_prompts": True, "retain_raw_outputs": True},
        "artifacts": {"local_root": "results/local"},
        "display": {"locale": "en"},
    }
    return mapping


def _fixtures(base: Path) -> None:
    _rate_card(base)
    (base / "workload.jsonl").write_text(
        SMOKE_WORKLOAD.read_text(encoding="utf-8"), encoding="utf-8"
    )


def _write_config(base: Path, prereg: dict[str, Any] | None) -> Path:
    _fixtures(base)
    path = base / ".foundry.local.yaml"
    path.write_text(yaml.safe_dump(_config_mapping(prereg)), encoding="utf-8")
    return path


def _resolved(base: Path, prereg: dict[str, Any] | None):
    _fixtures(base)
    config = LocalRunConfig.from_mapping(
        _config_mapping(prereg), base_dir=base, source=str(base / ".foundry.local.yaml")
    )
    return config, resolve_run_plan(config, env={}, require_run_ready=True)



@pytest.fixture
def no_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trip an assertion if control ever reaches the credentialed client.

    These tests drive ``--live``. The gate is supposed to return before anything
    reads a credential; if it ever stops doing that, this fixture is what turns a
    silently-passing test into a loud one instead of a paid call.
    """

    def _boom(*_args: Any, **_kwargs: Any):
        raise AssertionError("reached FoundryConfig.from_env(): the prereg gate let go")

    monkeypatch.setattr(cli.FoundryConfig, "from_env", staticmethod(_boom))


def test_cli_live_run_refuses_a_tampered_pin_before_any_credential(
    pinned_repo: dict[str, Any], capsys: pytest.CaptureFixture[str], no_dispatch: None
) -> None:
    repo = pinned_repo["repo"]
    config_path = _write_config(
        repo, {"path": "prereg.md", "blob": "0" * 40, "commit": pinned_repo["pin"]["commit"]}
    )
    _, plan = _resolved(repo, {"path": "prereg.md", "blob": "0" * 40,
                               "commit": pinned_repo["pin"]["commit"]})

    code = cli.main(
        ["benchmark", "run", "--config", str(config_path), "--live",
         "--approve-plan", plan.plan_hash, "--env-file", str(repo / "absent.env")]
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "does not match the git history" in out
    assert "unshallow" not in out


def test_cli_live_run_refuses_when_the_pin_cannot_be_read_here(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], no_dispatch: None
) -> None:
    """Fork 1: absent evidence blocks the spend, and says why in its own words."""

    base = tmp_path / "export"
    base.mkdir()
    (base / "prereg.md").write_text("# preregistration\n", encoding="utf-8")
    pin = {"path": "prereg.md", "blob": "a" * 40, "commit": "b" * 40}
    config_path = _write_config(base, pin)
    _, plan = _resolved(base, pin)

    code = cli.main(
        ["benchmark", "run", "--config", str(config_path), "--live",
         "--approve-plan", plan.plan_hash, "--env-file", str(base / "absent.env")]
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "This is NOT a verification failure" in out
    assert "git fetch --unshallow" in out


def test_cli_live_run_refuses_an_uncommitted_preregistration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], no_dispatch: None
) -> None:
    repo = _init_repo(tmp_path / "repo")
    _commit(repo, "seed.md", "seed\n", "seed")
    (repo / "prereg.md").write_text("# preregistration, never committed\n", encoding="utf-8")
    pin = {
        "path": "prereg.md",
        "blob": git_blob_hash(repo / "prereg.md"),
        "commit": _git(repo, "rev-parse", "HEAD"),
    }
    config_path = _write_config(repo, pin)
    _, plan = _resolved(repo, pin)

    code = cli.main(
        ["benchmark", "run", "--config", str(config_path), "--live",
         "--approve-plan", plan.plan_hash, "--env-file", str(repo / "absent.env")]
    )
    out = capsys.readouterr().out
    assert code == 1
    # The pin cannot resolve either, so the identity check speaks first — what
    # matters is that neither wording lets the run through.
    assert "refusing to dispatch" in out


def test_cli_live_run_refuses_a_benchmark_that_pins_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], no_dispatch: None
) -> None:
    repo = _init_repo(tmp_path / "repo")
    config_path = _write_config(repo, None)
    _, plan = _resolved(repo, None)

    code = cli.main(
        ["benchmark", "run", "--config", str(config_path), "--live",
         "--approve-plan", plan.plan_hash, "--env-file", str(repo / "absent.env")]
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "this plan pins no preregistration" in out


# --------------------------------------------------------------------------- #
# The offline paths owe git nothing
# --------------------------------------------------------------------------- #


def test_benchmark_plan_works_in_a_tree_with_no_git(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fork 1: fail-closed is for paid dispatch only.

    The preview is where somebody decides whether to spend at all. Requiring a
    full clone to read it would push people toward approving a plan they could
    not inspect.
    """

    base = tmp_path / "export"
    base.mkdir()
    (base / "prereg.md").write_text("# preregistration\n", encoding="utf-8")
    config_path = _write_config(
        base, {"path": "prereg.md", "blob": "a" * 40, "commit": "b" * 40}
    )

    assert cli.main(["benchmark", "plan", "--config", str(config_path)]) == 0
    out = capsys.readouterr().out
    # The approval screen states the pin and what will be done with it.
    assert "preregistration   : prereg.md" in out
    assert "blob " + "a" * 40 in out
    assert "checked at dispatch" in out
    assert "an appended errata section is not a violation" in out


def test_replay_works_in_a_tree_with_no_git(tmp_path: Path) -> None:
    """Replaying a sealed run re-reads artifacts; it never consults history."""

    base = tmp_path / "export"
    base.mkdir()
    (base / "prereg.md").write_text("# preregistration\n", encoding="utf-8")
    config, plan = _resolved(base, {"path": "prereg.md", "blob": "a" * 40, "commit": "b" * 40})

    result = execute_benchmark(
        config, plan, client=_FakeClient(), run_dir=base / "run", exp_id="benchmark",
        now=datetime(2026, 8, 5, tzinfo=UTC), sleeper=lambda _s: None,
        clock=lambda: "2026-08-05T00:00:00Z",
    )
    replay = replay_measure(result.run_dir)
    assert replay.ok is True
    assert replay.plan_hash == plan.plan_hash


def test_a_benchmark_plan_without_a_pin_says_the_live_run_will_refuse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal must be visible at preview time, not discovered at dispatch."""

    base = tmp_path / "repo"
    base.mkdir()
    config_path = _write_config(base, None)
    assert cli.main(["benchmark", "plan", "--config", str(config_path)]) == 0
    out = capsys.readouterr().out
    assert "NONE PINNED" in out
    assert "will refuse" in out


# --------------------------------------------------------------------------- #
# plan_hash does not move
# --------------------------------------------------------------------------- #


def test_giving_the_pinned_blob_a_reader_does_not_move_plan_hash(tmp_path: Path) -> None:
    """Reading a field is not the same as hashing one.

    ``plan_hash`` is computed over the ``execution`` mapping, and the
    preregistration block is copied into it verbatim from the config. Nothing in
    this change writes to that mapping, so every previously-approved plan_hash —
    including the three the sealed 03D runs were approved under — still resolves
    to the same value. If this literal ever has to change, an approval somewhere
    was silently invalidated.
    """

    pin = {
        "path": "benchmarks/original-coding/prereg-03d3-router-modes.md",
        "blob": "8584e1f8c6031d7be6b03d01a9e292c83d57bab5",
        "commit": "454c8159e6e3666a6b24982ef30766ea73059f22",
    }
    _config, plan = _resolved(tmp_path, pin)
    assert plan.plan_hash == (
        "sha256:0c782385adb508880c3a63540ba43cd5757adbc84510ae52dfc712c2c8d1f58d"
    )
    assert plan.execution["preregistration"] == pin
