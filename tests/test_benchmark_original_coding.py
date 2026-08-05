"""Regression guard for the original-coding benchmark.

Keeps the published task set honest inside the repo's normal ``pytest`` run:
the graders must still discriminate (bidirectional verification), the spec
hashes must still match, and the task manifest must keep its shape and
provenance. The benchmark harness is exercised out-of-process so it stays
isolated from the repo's own imports.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent / "benchmarks" / "original-coding"
TASKS = BENCH / "tasks.jsonl"

REQUIRED_FIELDS = {
    "id",
    "difficulty",
    "type",
    "system_prompt",
    "user_prompt",
    "pass_criteria",
    "source",
    "license",
    "contamination_risk",
    "expected_output_tokens",
    "spec_hash",
    "created_at",
}
TASK_TYPES = {"implementation", "edge-case", "bug-fix", "refactor", "test-writing"}


def _run(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BENCH / "harness" / script)],
        cwd=str(BENCH),
        capture_output=True,
        text=True,
        check=False,
    )


def _load_tasks() -> list[dict]:
    lines = TASKS.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_bidirectional_verification_passes() -> None:
    result = _run("verify.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "24/24 tasks passed" in result.stdout


def test_spec_hashes_match() -> None:
    result = _run("spec_hash.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_task_count_and_difficulty_distribution() -> None:
    difficulty = Counter(task["difficulty"] for task in _load_tasks())
    assert dict(difficulty) == {"easy": 8, "medium": 10, "hard": 6}


def test_task_schema_and_provenance() -> None:
    ids: set[str] = set()
    for task in _load_tasks():
        assert REQUIRED_FIELDS <= set(task), f"{task.get('id')} missing fields"
        assert task["type"] in TASK_TYPES
        assert task["source"] == "original"
        assert task["license"] == "MIT"
        assert task["contamination_risk"] == "low"
        assert task["id"] not in ids, f"duplicate id {task['id']}"
        ids.add(task["id"])


def test_every_task_has_grader_and_fixtures() -> None:
    for task in _load_tasks():
        task_id = task["id"]
        module = task_id.replace("-", "_")
        assert (BENCH / "graders" / f"{module}.py").is_file()
        assert (BENCH / "fixtures" / task_id / "reference.py").is_file()
        assert (BENCH / "fixtures" / task_id / "wrong.py").is_file()
