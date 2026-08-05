"""Bidirectional verification: prove every grader actually discriminates.

For each task with a grader in ``graders/`` and fixtures in
``fixtures/<task_id>/``, this runs the grader twice:

* ``reference.py`` — the correct solution, which **must PASS**;
* ``wrong.py`` — a deliberately incorrect solution, which **must FAIL**.

A grader that passes everything (or fails everything) is worthless, so any task
whose fixtures don't split PASS/FAIL exactly is reported and the process exits
nonzero. This is the single most important gate in the benchmark: run it after
authoring every task and in CI.

CLI::

    python harness/verify.py            # verify all tasks
    python harness/verify.py --task ID  # verify one task
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.grade import GRADERS_DIR, run_grader  # noqa: E402

FIXTURES_DIR = ROOT / "fixtures"


@dataclass(frozen=True)
class TaskVerdict:
    task_id: str
    reference_ok: bool
    wrong_ok: bool
    reference_detail: str
    wrong_detail: str

    @property
    def ok(self) -> bool:
        return self.reference_ok and self.wrong_ok


def _task_ids() -> list[str]:
    return sorted(
        p.stem.replace("_", "-")
        for p in GRADERS_DIR.glob("*.py")
        if p.stem != "__init__"
    )


def verify_task(task_id: str, *, timeout: int = 15) -> TaskVerdict:
    fixture_dir = FIXTURES_DIR / task_id
    reference = fixture_dir / "reference.py"
    wrong = fixture_dir / "wrong.py"

    if not reference.is_file():
        return TaskVerdict(task_id, False, False, "missing reference.py", "n/a")
    if not wrong.is_file():
        return TaskVerdict(task_id, False, False, "n/a", "missing wrong.py")

    ref_result = run_grader(task_id, reference, timeout=timeout)
    wrong_result = run_grader(task_id, wrong, timeout=timeout)

    # reference must PASS; wrong must FAIL.
    reference_ok = ref_result.passed
    wrong_ok = not wrong_result.passed
    return TaskVerdict(
        task_id,
        reference_ok,
        wrong_ok,
        "PASS" if reference_ok else f"expected PASS, got FAIL: {ref_result.detail}",
        "FAIL (as required)" if wrong_ok else "expected FAIL, but it PASSED",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bidirectional grader verification.")
    parser.add_argument("--task", help="verify a single task id")
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args(argv)

    task_ids = [args.task] if args.task else _task_ids()
    if not task_ids:
        print("no graders found to verify")
        return 1

    failures = 0
    for task_id in task_ids:
        verdict = verify_task(task_id, timeout=args.timeout)
        mark = "ok" if verdict.ok else "BROKEN"
        print(
            f"[{mark}] {task_id}\n"
            f"        reference -> {verdict.reference_detail}\n"
            f"        wrong     -> {verdict.wrong_detail}"
        )
        if not verdict.ok:
            failures += 1

    total = len(task_ids)
    print(f"\n{total - failures}/{total} tasks passed bidirectional verification")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
