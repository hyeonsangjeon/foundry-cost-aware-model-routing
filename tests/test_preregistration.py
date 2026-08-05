"""Tests for the preregistration hash-order contract (BOLT-03B step 5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from router.preregistration import (
    PreregistrationBody,
    experiment_spec_hash,
    resolve_preregistration,
    verify_unmodified,
)


def _draft(model: str = "grok", *, locale: str = "en") -> dict:
    return {
        "arms": [{"id": "router", "kind": "model_router", "deployment": model}],
        "workload": {"path": "workloads/smoke.jsonl", "fingerprint": "wf123"},
        "budget": {"budget_usd": "0.10"},
        "repetitions": 1,
        "display": {"locale": locale},  # display-only, excluded from the hash
        "created_at": "2026-07-29T00:00:00Z",  # wall-clock, excluded
    }


def _body(spec_hash: str, **overrides) -> PreregistrationBody:
    base = dict(
        experiment_spec_hash=spec_hash,
        workload_fingerprint="wf123",
        rate_card_hash="rc456",
        arm_set=("router", "premium"),
        repetitions=1,
        grader={"kind": "exec-signals", "version": 1},
        quality_gate={"min_pass_rate": 0.5},
        budget_usd="0.10",
        estimand="cost_per_passed_task",
        analysis_unit="task",
        repeat_aggregation="mean",
        denominator="all_tasks",
        failure_policy="count_as_fail",
        missing_cell_policy="exclude",
        cost_per_pass_formula="known_cost / passes",
        paired_statistic="wilcoxon",
    )
    base.update(overrides)
    return PreregistrationBody(**base)


def test_spec_hash_excludes_display_and_wall_clock() -> None:
    # Locale/display and wall-clock changes never move the spec hash.
    assert experiment_spec_hash(_draft(locale="en")) == experiment_spec_hash(
        _draft(locale="ko")
    )
    with_ts = _draft()
    with_ts["created_at"] = "2099-01-01T00:00:00Z"
    assert experiment_spec_hash(with_ts) == experiment_spec_hash(_draft())


def test_spec_hash_moves_when_an_execution_field_changes() -> None:
    assert experiment_spec_hash(_draft("grok")) != experiment_spec_hash(_draft("gpt-4o"))


@pytest.fixture
def prereg_file(tmp_path: Path) -> Path:
    path = tmp_path / "prereg.yaml"
    path.write_text("preregistration: v1\n", encoding="utf-8")
    return path


def _git(commit: str = "c0ffee", blob: str = "blob1", clean: bool = True):
    return dict(
        blob_hash_fn=lambda _p: blob,
        committed_fn=lambda _p: (commit, "2026-07-29T00:00:00+00:00"),
        clean_fn=lambda _p: clean,
    )


def test_happy_path_binds_a_final_plan_hash(prereg_file: Path) -> None:
    spec = experiment_spec_hash(_draft())
    outcome = resolve_preregistration(
        spec_hash=spec, body=_body(spec), prereg_path=prereg_file,
        run_mode="benchmark", **_git(),
    )
    assert outcome.allowed and outcome.plan_hash
    assert outcome.evidence is not None and outcome.evidence.blob_hash == "blob1"


def test_changing_prereg_blob_changes_the_plan_hash(prereg_file: Path) -> None:
    spec = experiment_spec_hash(_draft())
    first = resolve_preregistration(
        spec_hash=spec, body=_body(spec), prereg_path=prereg_file,
        run_mode="benchmark", **_git(blob="blobAAA"),
    )
    second = resolve_preregistration(
        spec_hash=spec, body=_body(spec), prereg_path=prereg_file,
        run_mode="benchmark", **_git(blob="blobBBB"),
    )
    assert first.plan_hash != second.plan_hash  # prereg blob is bound into the hash


def test_benchmark_cannot_bypass_preregistration() -> None:
    spec = experiment_spec_hash(_draft())
    outcome = resolve_preregistration(
        spec_hash=spec, body=_body(spec), prereg_path=None, run_mode="benchmark",
    )
    assert outcome.allowed is False
    assert "cannot bypass" in outcome.note


def test_wiring_only_smoke_may_bypass() -> None:
    spec = experiment_spec_hash(_draft())
    outcome = resolve_preregistration(
        spec_hash=spec, body=_body(spec), prereg_path=None, run_mode="smoke",
        wiring_only=True, benchmark_eligible=False,
    )
    assert outcome.allowed is True and outcome.bypassed is True


def test_smoke_without_wiring_flags_cannot_bypass() -> None:
    spec = experiment_spec_hash(_draft())
    outcome = resolve_preregistration(
        spec_hash=spec, body=_body(spec), prereg_path=None, run_mode="smoke",
        wiring_only=False, benchmark_eligible=True,
    )
    assert outcome.allowed is False


def test_modified_after_approval_is_rejected(prereg_file: Path) -> None:
    spec = experiment_spec_hash(_draft())
    # The committed body references a DIFFERENT spec hash than the current draft.
    stale_body = _body("some-other-spec-hash")
    outcome = resolve_preregistration(
        spec_hash=spec, body=stale_body, prereg_path=prereg_file,
        run_mode="benchmark", **_git(),
    )
    assert outcome.allowed is False and "modified after" in outcome.note


def test_dirty_prereg_fails_closed(prereg_file: Path) -> None:
    spec = experiment_spec_hash(_draft())
    outcome = resolve_preregistration(
        spec_hash=spec, body=_body(spec), prereg_path=prereg_file,
        run_mode="benchmark", **_git(clean=False),
    )
    assert outcome.allowed is False and "tracked and clean" in outcome.note


def test_verify_unmodified_detects_blob_change(prereg_file: Path) -> None:
    assert verify_unmodified(
        prereg_path=prereg_file, approved_blob_hash="blobX",
        blob_hash_fn=lambda _p: "blobX",
    )
    assert not verify_unmodified(
        prereg_path=prereg_file, approved_blob_hash="blobX",
        blob_hash_fn=lambda _p: "blobY",
    )


def test_body_validate_rejects_bad_analysis_unit_and_missing_fields() -> None:
    spec = "s"
    with pytest.raises(ValueError):
        _body(spec, analysis_unit="majority").validate()
    with pytest.raises(ValueError):
        _body(spec, denominator="").validate()
