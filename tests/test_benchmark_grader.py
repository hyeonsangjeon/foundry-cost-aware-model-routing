"""Tests for the exec-signals grading bridge (BOLT-03 §9/§10, task 03D-1).

The measured sweep must turn each arm's *generated code* into a deterministic
pass/fail using the frozen ``benchmarks/original-coding`` harness, retain the raw
output privately (gitignored) while only a hash + verdict travel into the public
snapshot, and report grading coverage / quality without ever changing the
approved ``plan_hash``. Everything here is network-free: grading runs the local
harness in a subprocess and the sweep is driven by a scripted fake client.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from router.benchmark_grader import (
    ExecSignalsGrader,
    extract_code,
    output_hash,
)
from router.measure import (
    AttemptResult,
    MeasureCandidate,
    RetryPolicy,
    _grading_blocks,
    build_publish_bundle,
    load_prompt_workload,
    regrade_from_raw,
    replay_measure,
    run_measure,
)
from router.pricing import PricingTable
from router.run_plan import LocalRunConfig, execute_benchmark, resolve_run_plan

BENCH = Path("benchmarks/original-coding")
# 03D-2 re-run plan hash. Supersedes the void run's
# sha256:9474b9801e9cdf9edfb84ac8ac048eb2726d849ec42b840c5ff51f0db474acb6, whose
# rate card pinned grok-4-1-fast cached: null and used max_output_tokens=2048.
# The re-run pins Grok cached=input (0.2) and max_output_tokens=8192, and binds a
# new prereg (prereg-03d2-router-modes.md) — all three change the plan hash.
APPROVED_PLAN_HASH = "sha256:d640dc07a0a2dd62871b7fddba552f34c64c0c54affe7a7fcbe475ec91d2921e"


def _fixture(task_id: str, kind: str) -> str:
    return (BENCH / "fixtures" / task_id / f"{kind}.py").read_text(encoding="utf-8")


def _task_ids() -> list[str]:
    ids = []
    for line in (BENCH / "tasks.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            ids.append(str(row.get("id") or row.get("task_id")))
    return ids


# --------------------------------------------------------------------------- #
# Grader unit — the tamper-proof both-directions check over all 24 fixtures
# --------------------------------------------------------------------------- #


def test_every_fixture_reference_passes_and_wrong_fails():
    grader = ExecSignalsGrader(BENCH)
    ids = _task_ids()
    assert len(ids) == 24
    for task_id in ids:
        ref = grader(task_id, {"task_id": task_id}, "m", {}, _fixture(task_id, "reference"))
        wrong = grader(task_id, {"task_id": task_id}, "m", {}, _fixture(task_id, "wrong"))
        assert ref.passed is True, f"{task_id}: reference should PASS ({ref.detail})"
        assert wrong.passed is False, f"{task_id}: wrong should FAIL ({wrong.detail})"
        # A verdict always carries the output hash so the snapshot can prove which
        # bytes were graded, in both directions.
        assert ref.output_sha256 == output_hash(_fixture(task_id, "reference"))
        assert wrong.output_sha256 == output_hash(_fixture(task_id, "wrong"))


def test_fenced_code_block_is_extracted_and_graded():
    task_id = _task_ids()[0]
    ref = _fixture(task_id, "reference")
    reply = f"Sure — here is the module:\n\n```python\n{ref}\n```\n\nHope that helps!"
    assert extract_code(reply).strip() == ref.strip()
    grader = ExecSignalsGrader(BENCH)
    assert grader(task_id, {"task_id": task_id}, "m", {}, reply).passed is True


def test_longest_fenced_block_wins_over_a_shorter_example():
    task_id = _task_ids()[0]
    ref = _fixture(task_id, "reference")
    reply = f"example:\n```python\nx = 1\n```\nsolution:\n```python\n{ref}\n```"
    assert extract_code(reply).strip() == ref.strip()


def test_no_output_is_ungraded_not_a_failure():
    grader = ExecSignalsGrader(BENCH)
    task_id = _task_ids()[0]
    for empty in (None, "", "   \n\t"):
        verdict = grader(task_id, {"task_id": task_id}, "m", {}, empty)
        assert verdict.passed is None
        assert verdict.output_sha256 is None


def test_unknown_task_is_ungraded_infra_gap_not_penalty():
    # A harness that cannot load the task grader is an infrastructure gap: the
    # cell is ungraded (counts against coverage), never blamed on the candidate.
    grader = ExecSignalsGrader(BENCH)
    verdict = grader("no-such-task", {"task_id": "no-such-task"}, "m", {}, "print(1)\n")
    assert verdict.passed is None
    assert verdict.output_sha256 is not None  # output was still captured + hashed


def test_output_hash_is_stable_and_prefixed():
    assert output_hash("abc") == output_hash("abc")
    assert output_hash("abc").startswith("sha256:")
    assert output_hash("abc") != output_hash("abd")


# --------------------------------------------------------------------------- #
# Grading/quality block math (pure function of traces → replay-reproducible)
# --------------------------------------------------------------------------- #


def _graded_row(model, task_id, passed, *, ok=True, sha="sha256:deadbeef"):
    row = {
        "candidate_model": model,
        "task_id": task_id,
        "http_status": 200 if ok else 500,
        "fail_reason": None if ok else "http_500_exhausted",
        "pass": passed,
    }
    if sha is not None:
        row["output_sha256"] = sha
    return row


def test_grading_blocks_coverage_quality_and_cost_per_pass():
    rows = [
        _graded_row("A", "t1", True),
        _graded_row("A", "t2", True),
        _graded_row("B", "t1", False),
        _graded_row("B", "t2", None),  # captured but ungradable → grade error
    ]
    grading, quality = _grading_blocks(
        rows, candidate_models=["A", "B"], n=1, planned_cells=4,
        arm_known_cost={"A": 0.10, "B": 0.20},
    )
    assert grading == {
        "basis": "exec-signals",
        "planned_cells": 4,
        "content_graded": 4,
        "graded_cells": 3,   # the None cell is a grade error, excluded from graded
        "grade_errors": 1,
        "coverage": pytest.approx(0.75),  # 3 graded / 4 planned — error drags it down
    }
    a = quality["by_candidate"]["A"]
    b = quality["by_candidate"]["B"]
    assert a["tasks_planned"] == 2 and a["tasks_passed"] == 2
    assert a["pass_rate"] == pytest.approx(1.0)
    assert a["cost_per_pass_usd"] == pytest.approx(0.05)  # 0.10 / 2 passes
    assert b["tasks_passed"] == 0 and b["pass_rate"] == pytest.approx(0.0)
    assert b["cost_per_pass_usd"] is None  # no passes → withheld, never 0
    assert quality["quality_graded"] is True


def test_grading_blocks_majority_pass_of_n():
    rows = [
        _graded_row("A", "t1", True), _graded_row("A", "t1", True), _graded_row("A", "t1", False),
        _graded_row("A", "t2", True), _graded_row("A", "t2", False), _graded_row("A", "t2", False),
    ]
    _, quality = _grading_blocks(
        rows, candidate_models=["A"], n=3, planned_cells=6, arm_known_cost={"A": 0.0},
    )
    # t1 = 2/3 pass → majority pass; t2 = 1/3 → not a pass.
    assert quality["by_candidate"]["A"]["tasks_passed"] == 1


def test_grading_blocks_absent_without_content_graded_rows():
    rows = [_graded_row("A", "t1", True, sha=None)]  # a usage/bool grader sets no hash
    assert _grading_blocks(
        rows, candidate_models=["A"], n=1, planned_cells=1, arm_known_cost={}
    ) == (None, None)


# --------------------------------------------------------------------------- #
# End-to-end sweep with the real grader (network-free scripted client)
# --------------------------------------------------------------------------- #


class FixtureClient:
    """Fake: each deployment returns a fixed fixture's code as the response body."""

    def __init__(self, kind_by_deployment: dict[str, str]):
        self.kind_by_deployment = kind_by_deployment

    def attempt(self, *, deployment, provider, task):  # noqa: ANN001 - test seam
        kind = self.kind_by_deployment.get(deployment, "reference")
        content = None if kind == "none" else _fixture(task["task_id"], kind)
        return AttemptResult(
            http_status=200, model=deployment, usage={"input": 100, "output": 50},
            latency_ms=5.0, provenance="live", content=content,
        )


def _small_workload(n_tasks: int = 3) -> dict[str, dict]:
    full = load_prompt_workload(BENCH / "tasks.jsonl")
    keys = list(full)[:n_tasks]
    return {k: full[k] for k in keys}


def _graded_run(tmp_path, kind_by_deployment, *, n=1):
    workload = _small_workload()
    candidates = [MeasureCandidate(dep, dep) for dep in kind_by_deployment]
    return run_measure(
        workload, candidates,
        client=FixtureClient(kind_by_deployment),
        pricing=PricingTable.from_yaml("samples/pricing/foundry-5series.yaml"),
        exp_id="bench", run_dir=tmp_path / "RUN", run_id="RUN", n=n,
        retry=RetryPolicy(max_retries=1, base_backoff_ms=1.0),
        sleeper=lambda _s: None,
        clock=(lambda: "2026-08-06T00:00:00.000+00:00"),
        now=datetime(2026, 8, 6, tzinfo=UTC),
        grader=ExecSignalsGrader(BENCH),
    )


def test_sweep_grades_good_and_bad_arms(tmp_path):
    result = _graded_run(tmp_path, {"good": "reference", "bad": "wrong"})
    grading = result.summary["grading"]
    assert grading["basis"] == "exec-signals"
    assert grading["planned_cells"] == 6  # 3 tasks × 2 arms × n=1
    assert grading["coverage"] == pytest.approx(1.0)  # every cell graded
    quality = result.summary["quality"]["by_candidate"]
    assert quality["good"]["pass_rate"] == pytest.approx(1.0)
    assert quality["bad"]["pass_rate"] == pytest.approx(0.0)
    assert quality["good"]["cost_per_pass_usd"] is not None
    assert quality["bad"]["cost_per_pass_usd"] is None
    assert result.summary["labels"]["quality_graded"] is True
    assert result.manifest["labels"]["quality_graded"] is True


def test_raw_output_is_retained_gitignored_and_never_public(tmp_path):
    result = _graded_run(tmp_path, {"good": "reference"})
    raw_dir = result.run_dir / "raw_outputs"
    # Retained privately and hard-ignored so raw bytes can never be committed.
    assert (raw_dir / ".gitignore").read_text(encoding="utf-8") == "*\n"
    raw_lines = (raw_dir / "outputs.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 3
    assert "def " in "\n".join(raw_lines)  # the actual code is retained

    # The public trace/summary surface carries only the hash + verdict, no code.
    traces_text = (result.run_dir / "traces.jsonl").read_text(encoding="utf-8")
    assert '"output_sha256"' in traces_text
    assert '"content"' not in traces_text
    assert "def " not in traces_text

    bundle = json.dumps(build_publish_bundle(result.run_dir))
    assert '"content"' not in bundle
    assert "def " not in bundle
    assert "grading" in bundle and "quality" in bundle  # evidence travels, code does not


def test_grade_failure_and_timeout_counted_not_dropped(tmp_path):
    # Every "bad" cell grades to False — a penalty that stays inside coverage
    # (graded), it is not silently dropped to inflate the pass rate.
    result = _graded_run(tmp_path, {"bad": "wrong"})
    grading = result.summary["grading"]
    assert grading["planned_cells"] == 3
    assert grading["graded_cells"] == 3   # all three graded (as fails)
    assert grading["grade_errors"] == 0
    assert grading["coverage"] == pytest.approx(1.0)
    assert result.summary["quality"]["by_candidate"]["bad"]["tasks_passed"] == 0


def test_none_content_leaves_run_ungraded(tmp_path):
    result = _graded_run(tmp_path, {"silent": "none"})
    # No captured body anywhere → no grading block, no raw directory, byte-shape
    # identical to a pre-bridge ungraded run.
    assert "grading" not in result.summary
    assert "quality" not in result.summary
    assert not (result.run_dir / "raw_outputs").exists()


def test_graded_run_replays_byte_identical(tmp_path):
    result = _graded_run(tmp_path, {"good": "reference", "bad": "wrong"})
    report = replay_measure(result.run_dir)
    assert report.ok is True
    assert report.summary_matches is True


def test_tampered_pass_breaks_replay(tmp_path):
    result = _graded_run(tmp_path, {"good": "reference"})
    traces_path = result.run_dir / "traces.jsonl"
    rows = [json.loads(x) for x in traces_path.read_text().splitlines() if x.strip()]
    flipped = False
    for row in rows:
        if row.get("pass") is True:
            row["pass"] = False
            flipped = True
            break
    assert flipped
    traces_path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n")
    # Grading metrics derive purely from the sealed pass field, so any edit makes
    # the recomputed summary diverge — the tamper is detected on replay.
    assert replay_measure(result.run_dir).summary_matches is False


def test_regrade_from_raw_matches_sealed_verdicts(tmp_path):
    result = _graded_run(tmp_path, {"good": "reference", "bad": "wrong"})
    report = regrade_from_raw(result.run_dir, BENCH)
    assert report["available"] is True
    assert report["checked"] == 6
    assert report["ok"] is True
    assert report["mismatches"] == []


def test_regrade_from_raw_detects_a_forged_pass(tmp_path):
    result = _graded_run(tmp_path, {"bad": "wrong"})
    raw_path = result.run_dir / "raw_outputs" / "outputs.jsonl"
    rows = [json.loads(x) for x in raw_path.read_text().splitlines() if x.strip()]
    rows[0]["pass"] = True  # forge a pass that the code cannot actually earn
    raw_path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n")
    report = regrade_from_raw(result.run_dir, BENCH)
    assert report["ok"] is False
    assert report["mismatches"][0]["sealed"] is True
    assert report["mismatches"][0]["regraded"] is False


def test_regrade_from_raw_absent_when_no_raw(tmp_path):
    result = _graded_run(tmp_path, {"silent": "none"})
    report = regrade_from_raw(result.run_dir, BENCH)
    assert report == {"available": False, "checked": 0, "matches": 0, "mismatches": [], "ok": True}


# --------------------------------------------------------------------------- #
# plan_hash invariance — the bridge is a runner change, not a config change
# --------------------------------------------------------------------------- #

LOCAL_CONFIG = Path(".foundry.local.yaml")


@pytest.mark.skipif(
    not LOCAL_CONFIG.is_file(),
    reason="operator local config (.foundry.local.yaml is gitignored) — local-only guard",
)
def test_committed_plan_hash_unchanged_by_bridge():
    # Local-only operator guard: the approved hash binds the operator's local
    # config (with its prereg blob), which is gitignored, so this runs only where
    # that config exists (the operator's checkout), never in CI.
    cfg = LocalRunConfig.from_yaml(str(LOCAL_CONFIG))
    plan = resolve_run_plan(cfg, env={})
    assert plan.plan_hash == APPROVED_PLAN_HASH
    assert plan.planned_cells == 288


def _benchmark_config(base_dir: Path) -> dict[str, Any]:
    # A self-contained benchmark config built from tracked files (real workload +
    # committed v2 rate card), so the auto-grader wiring is exercised everywhere,
    # including CI where the operator's local config is absent. One direct arm,
    # n=1 → 24 graded cells.
    root = Path(__file__).resolve().parent.parent
    return {
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
            {"id": "direct-premium", "kind": "direct", "provider": "openai",
             "requested_model": "gpt-5.6-sol", "deployment": "gpt-5.6-sol"},
        ],
        "benchmark": {
            "workload": str(root / "benchmarks/original-coding/tasks.jsonl"),
            "rate_card": str(root / "samples/pricing/foundry-ext-router.yaml"),
            "smoke_authorization_ceiling_usd": None,
            "repetitions": 1,
            "max_output_tokens": 2048,
            "budget_usd": 20.0,
            "random_seed": 20260729,
            "estimand": {
                "analysis_unit": "task", "repeat_aggregation": "mean",
                "denominator_policy": "all-attempted", "failure_policy": "count-as-zero",
                "cost_per_pass_formula": "total_cost / passes", "paired_statistic": "wilcoxon",
            },
            "grader": {"kind": "exec-signals", "version": 1},
            "retry": {"max_retries": 4},
        },
        "privacy": {"retain_raw_prompts": True, "retain_raw_outputs": True},
        "artifacts": {"local_root": "results/local"},
        "display": {"locale": "en"},
    }


def test_execute_benchmark_autobuilds_grader_and_seals_plan_hash(tmp_path):
    cfg = LocalRunConfig.from_mapping(
        _benchmark_config(tmp_path), base_dir=tmp_path, source=str(tmp_path / "c.yaml")
    )
    plan = resolve_run_plan(cfg, env={})
    # Drive the real run_plan → execute_benchmark path with NO grader injected:
    # the benchmark run_mode + exec-signals kind + present harness must make
    # execute_benchmark auto-build the grader so the paid path grades.
    client = FixtureClient({c.deployment: "reference" for c in plan.candidates()})
    result = execute_benchmark(
        cfg, plan, client=client, run_dir=tmp_path / "RUN", exp_id="benchmark",
        now=datetime(2026, 8, 6, tzinfo=UTC),
        clock=(lambda: "2026-08-06T00:00:00.000+00:00"),
        sleeper=lambda _s: None,
    )
    # Whatever plan_hash resolves is sealed into the manifest unchanged (the
    # bridge never touches the plan), and the run graded (auto-wired grader).
    assert result.manifest["plan_hash"] == plan.plan_hash
    assert result.summary["grading"]["basis"] == "exec-signals"
    assert result.summary["grading"]["planned_cells"] == 24
    assert result.summary["labels"]["quality_graded"] is True


def test_execute_benchmark_streams_progress_without_touching_plan_hash(tmp_path):
    # The live CLI wires a progress callback (stdout + progress.json) so a
    # detached paid sweep is observable mid-run; execute_benchmark must forward
    # one event per finished cell and never let it perturb the sealed plan_hash.
    cfg = LocalRunConfig.from_mapping(
        _benchmark_config(tmp_path), base_dir=tmp_path, source=str(tmp_path / "c.yaml")
    )
    plan = resolve_run_plan(cfg, env={})
    client = FixtureClient({c.deployment: "reference" for c in plan.candidates()})
    events: list[dict[str, Any]] = []
    result = execute_benchmark(
        cfg, plan, client=client, run_dir=tmp_path / "RUN", exp_id="benchmark",
        now=datetime(2026, 8, 6, tzinfo=UTC),
        clock=(lambda: "2026-08-06T00:00:00.000+00:00"),
        sleeper=lambda _s: None,
        progress=events.append,
    )
    # One event per planned cell, cells_done monotone 1..N, plan_hash sealed intact.
    assert [e["cells_done"] for e in events] == list(range(1, 25))
    assert all(e["cells_total"] == 24 for e in events)
    assert result.manifest["plan_hash"] == plan.plan_hash
