"""In-memory exec-signals grading bridge for the measured benchmark path.

The measured sweep (:mod:`router.measure`) captures each arm's *generated code*
alongside its usage; this module turns that code into a deterministic pass/fail
by running the frozen ``benchmarks/original-coding`` harness — the same grader,
sandbox, and per-task checks the offline ``harness/grade.py`` CLI uses. Grading
happens in a network-free subprocess with a wall-clock timeout, so a candidate's
code can never reach the network or hang the sweep (BOLT-03 §9: "pass the output
to the deterministic validator/grader in memory").

A :class:`GradeVerdict` is tri-state:

* ``passed=True``  — the code ran and satisfied every hidden check.
* ``passed=False`` — the code imported/ran but was wrong, timed out, or crashed
  (the model's fault: a *graded* failure that counts as a penalty, never dropped).
* ``passed=None``  — the cell could not be graded at all (no output was captured,
  or the harness itself could not load the task grader). Ungraded cells count
  against grading coverage; they are never silently dropped to inflate pass rate.

``output_sha256`` is the hash of the raw captured output. Only the hash and the
verdict travel into the public snapshot; the raw text is retained privately by
the runner (BOLT-03 §9: public bundles carry the output hash and grading
evidence only).
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

DEFAULT_GRADE_TIMEOUT_SECONDS = 15

# ``` fenced blocks, optionally tagged ```python / ```py. Non-greedy so the first
# complete block is matched; DOTALL so a block spans lines.
_FENCE_RE = re.compile(r"```[ \t]*(?:python|py)?[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class GradeVerdict:
    """One cell's grading outcome (see module docstring for the tri-state)."""

    passed: bool | None
    detail: str = ""
    output_sha256: str | None = None


def output_hash(content: str) -> str:
    """Stable ``sha256:`` digest of a captured output (matches snapshot hashing)."""

    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def extract_code(content: str) -> str:
    """Pull the Python module out of a model response.

    Prefers the longest fenced code block (the full solution when a reply also
    shows a shorter example); falls back to the whole response when the model
    returned a bare module, as the task's system prompt instructs.
    """

    blocks = [m.strip("\r\n") for m in _FENCE_RE.findall(content)]
    if blocks:
        return max(blocks, key=len)
    return content.strip()


class ExecSignalsGrader:
    """Grade captured output against a task's frozen exec-signals harness.

    ``benchmark_root`` is the workload directory (the parent of ``tasks.jsonl``),
    which holds ``harness/grade.py``. The harness driver is loaded once by file
    path — never onto ``sys.path`` — so importing this module has no side effects
    and grading a submission stays isolated in the harness's own subprocess.
    """

    def __init__(self, benchmark_root: Path | str, *, timeout: int = DEFAULT_GRADE_TIMEOUT_SECONDS):
        self.benchmark_root = Path(benchmark_root)
        self.timeout = int(timeout)
        self._run_grader: Callable[..., Any] | None = None

    # -- harness loading ---------------------------------------------------- #
    def _grade_driver(self) -> Callable[..., Any]:
        if self._run_grader is None:
            grade_py = self.benchmark_root / "harness" / "grade.py"
            if not grade_py.is_file():
                raise FileNotFoundError(
                    f"exec-signals harness not found at {grade_py}; the benchmark "
                    "workload must ship harness/grade.py"
                )
            module = _load_module_by_path(grade_py, name=f"_bench_grade_{abs(hash(grade_py))}")
            self._run_grader = module.run_grader
        return self._run_grader

    # -- grading ------------------------------------------------------------ #
    def __call__(
        self,
        task_id: str,
        task: Mapping[str, Any],
        model: str,
        usage: Mapping[str, float],
        content: str | None,
    ) -> GradeVerdict:
        if content is None or not str(content).strip():
            return GradeVerdict(passed=None, detail="no output captured", output_sha256=None)

        digest = output_hash(content)
        code = extract_code(content)
        run_grader = self._grade_driver()
        with tempfile.TemporaryDirectory(prefix="benchgrade-") as tmp:
            submission = Path(tmp) / f"{task_id}.py"
            submission.write_text(code, encoding="utf-8")
            result = run_grader(task_id, submission, timeout=self.timeout)

        detail = str(getattr(result, "detail", "") or "")
        passed = bool(getattr(result, "passed", False))
        # A harness-side inability to load the task grader is an infrastructure
        # gap, not a wrong answer: leave the cell ungraded (counts against
        # coverage) rather than blame the candidate for a missing grader.
        if not passed and detail.startswith("cannot load grader"):
            return GradeVerdict(passed=None, detail=detail, output_sha256=digest)
        return GradeVerdict(passed=passed, detail=detail, output_sha256=digest)


def _load_module_by_path(path: Path, *, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
