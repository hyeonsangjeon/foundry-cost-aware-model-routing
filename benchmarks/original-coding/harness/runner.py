"""Subprocess entry point that grades one submission against one task.

Invoked by :mod:`harness.grade` as::

    python -B harness/runner.py <task_id> <submission_path>

It activates the sandbox, loads the task grader, compiles the candidate source
into an isolated module, and calls ``grade(module, source)``. It prints exactly
one line — ``PASS`` or ``FAIL: <reason>`` — and exits 0 on pass, 1 on fail. The
parent owns the wall-clock timeout and the frozen environment.
"""

from __future__ import annotations

import importlib
import sys
import traceback
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import sandbox  # noqa: E402
from harness.checks import GradeError  # noqa: E402

PASS = "PASS"


def _load_submission(path: Path) -> tuple[types.ModuleType, str]:
    source = path.read_text(encoding="utf-8")
    module = types.ModuleType("submission")
    module.__dict__["__name__"] = "submission"
    exec(compile(source, "<submission>", "exec"), module.__dict__)  # noqa: S102 - sandboxed
    return module, source


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("FAIL: runner expects <task_id> <submission_path>")
        return 1
    task_id, submission_path = argv

    sandbox.activate()

    try:
        grader = importlib.import_module(f"graders.{task_id.replace('-', '_')}")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: cannot load grader for {task_id!r}: {type(exc).__name__}: {exc}")
        return 1

    try:
        module, source = _load_submission(Path(submission_path))
    except Exception as exc:  # noqa: BLE001 - submission failed to import/compile
        print(f"FAIL: submission did not import: {type(exc).__name__}: {exc}")
        return 1

    try:
        grader.grade(module, source)
    except GradeError as exc:
        print(f"FAIL: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 - unexpected grader/submission error
        detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        print(f"FAIL: unexpected error: {detail}")
        return 1

    print(PASS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
