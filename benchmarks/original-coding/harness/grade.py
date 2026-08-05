"""Offline grading driver: run a task grader against a candidate submission.

Each grade runs in a **separate subprocess** with a fixed wall-clock timeout and
a frozen environment (``PYTHONHASHSEED=0``, ``TZ=UTC``, ``LC_ALL=C``/``LANG=C``,
no bytecode, no inherited ``PYTHONPATH``). Combined with :mod:`harness.sandbox`
inside the child, this makes a grade deterministic and network-free regardless
of what the candidate code does.

CLI::

    python harness/grade.py --task <id> --submission out.py
    python harness/grade.py --all --submissions-dir model_outputs/   # <id>.py each
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "harness" / "runner.py"
GRADERS_DIR = ROOT / "graders"
DEFAULT_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class GradeResult:
    task_id: str
    passed: bool
    detail: str

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"


def _frozen_env() -> dict[str, str]:
    import os

    # Deliberately minimal: keep PATH so the interpreter runs, drop everything
    # else (including any inherited PYTHONPATH/proxy vars) and pin determinism.
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TZ": "UTC",
        "LC_ALL": "C",
        "LANG": "C",
        "SOURCE_DATE_EPOCH": "1700000000",
    }


def run_grader(
    task_id: str, submission_path: Path, *, timeout: int = DEFAULT_TIMEOUT_SECONDS
) -> GradeResult:
    """Grade ``submission_path`` for ``task_id`` in an isolated subprocess."""

    try:
        completed = subprocess.run(
            [sys.executable, "-B", str(RUNNER), task_id, str(submission_path)],
            env=_frozen_env(),
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return GradeResult(task_id, False, f"timeout after {timeout}s")

    out = (completed.stdout or "").strip().splitlines()
    line = out[-1] if out else ""
    if completed.returncode == 0 and line == "PASS":
        return GradeResult(task_id, True, "PASS")
    if line.startswith("FAIL:"):
        return GradeResult(task_id, False, line[len("FAIL:"):].strip())
    stderr = (completed.stderr or "").strip()
    return GradeResult(task_id, False, stderr or line or f"exit {completed.returncode}")


def _known_task_ids() -> list[str]:
    return sorted(
        p.stem.replace("_", "-")
        for p in GRADERS_DIR.glob("*.py")
        if p.stem != "__init__"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Grade coding-benchmark submissions offline.")
    parser.add_argument("--task", help="task id to grade")
    parser.add_argument("--submission", type=Path, help="path to the candidate .py file")
    parser.add_argument("--all", action="store_true", help="grade every task")
    parser.add_argument(
        "--submissions-dir", type=Path,
        help="directory holding <task_id>.py submissions (used with --all)",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.all:
        if not args.submissions_dir:
            print("--all requires --submissions-dir")
            return 2
        failures = 0
        for task_id in _known_task_ids():
            submission = args.submissions_dir / f"{task_id}.py"
            if not submission.is_file():
                print(f"{task_id}: FAIL: no submission at {submission}")
                failures += 1
                continue
            result = run_grader(task_id, submission, timeout=args.timeout)
            print(f"{task_id}: {result.status}: {result.detail}")
            failures += 0 if result.passed else 1
        print(f"\n{failures} failing of {len(_known_task_ids())}")
        return 1 if failures else 0

    if not args.task or not args.submission:
        print("provide --task and --submission (or --all --submissions-dir)")
        return 2
    result = run_grader(args.task, args.submission, timeout=args.timeout)
    print(f"{result.task_id}: {result.status}: {result.detail}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
