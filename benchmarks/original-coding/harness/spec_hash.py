"""Canonical spec hashing for benchmark tasks.

``spec_hash`` pins the *normative* content of a task — its type, difficulty, and
the three prompt fields — so any later edit to what a model is actually asked to
do is detectable, while bookkeeping fields (ids, token estimates, timestamps) can
change freely. Reviewers (and CI) recompute the hash from ``tasks.jsonl`` and
compare, catching silent drift between the published tasks and their hashes.

Run ``python harness/spec_hash.py`` to verify every row in ``tasks.jsonl``.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS_PATH = ROOT / "tasks.jsonl"

SPEC_FIELDS = ("type", "difficulty", "system_prompt", "user_prompt", "pass_criteria")


def canonical_spec(task: dict) -> str:
    """Return the canonical JSON string of a task's normative fields."""

    payload = {field: task[field] for field in SPEC_FIELDS}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_spec_hash(task: dict) -> str:
    return hashlib.sha256(canonical_spec(task).encode("utf-8")).hexdigest()


def load_tasks(path: Path = TASKS_PATH) -> list[dict]:
    tasks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            tasks.append(json.loads(line))
    return tasks


def main(argv: list[str] | None = None) -> int:
    path = Path(argv[0]) if argv else TASKS_PATH
    tasks = load_tasks(path)
    mismatches = []
    for task in tasks:
        expected = compute_spec_hash(task)
        if task.get("spec_hash") != expected:
            mismatches.append((task.get("id", "<no id>"), task.get("spec_hash"), expected))

    for task_id, stored, expected in mismatches:
        print(f"spec_hash mismatch for {task_id}: stored={stored} expected={expected}")

    if mismatches:
        print(f"\n{len(mismatches)} of {len(tasks)} tasks have a stale spec_hash")
        return 1
    print(f"all {len(tasks)} spec hashes verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
