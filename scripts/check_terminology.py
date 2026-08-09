#!/usr/bin/env python3
"""Terminology-collapse guard for the "coverage" vocabulary.

One Korean word — "커버리지" — used to name three different quantities across
the docs: a *task pass rate* (실험 03, 홈), a *grading coverage* (실험 12 / 03D),
and again a pass rate in the home definition. That made the 03D results page show
"통과율 95.8%" beside "커버리지 94.4%" while the home page defined the two as the
same thing — a contradiction a reader cannot resolve.

This checker freezes the reconciliation:

    통과율 (pass rate)        = 통과(해결)한 태스크의 비율   (tasks passed / attempted)
    채점 커버리지 (grading coverage) = 채점된 셀의 비율        (cells graded / planned)

They coincide offline (no timeouts) but diverge in measured runs, which is why
95.8% ≠ 94.4% on 03D. The single source of truth is ``docs/ko/manual/glossary.md``.

Rules enforced:

  A. The glossary exists and names *both* canonical terms (Korean + English).
  B. No docs line re-introduces the collapse by defining "커버리지" as a
     *task* pass ratio. A reconciliation line that also uses "통과율" (i.e. it
     is mapping 커버리지 → 통과율 on purpose) is allowed.
  C. Every measured page (03D, 실험 11, 실험 12) — where the grading figure is
     read next to the pass rate — must use the qualified "채점 커버리지" and must
     not carry a bare ``| 커버리지 |`` table column.

Run standalone::

    python scripts/check_terminology.py

Exits non-zero and prints every offending location when a rule is violated.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs" / "ko"
GLOSSARY = DOCS / "manual" / "glossary.md"

# Pages where a reader sees the grading figure next to the task pass rate. On
# these the grading metric must be spelled out as "채점 커버리지", never a bare
# "커버리지" that could be mistaken for the pass rate.
MEASURED_PAGES = (
    "manual/03d-results.md",
    "lab-notebook/11-router-modes-void.md",
    "lab-notebook/12-router-modes-measured.md",
)

# The glossary must name both canonical concepts, in Korean and English, so a
# reader has exactly one place to disambiguate the word.
REQUIRED_GLOSSARY_TERMS = (
    "통과율",
    "pass rate",
    "채점 커버리지",
    "grading coverage",
)

# The regression shape: "커버리지 … 통과/해결(한|된) … 태스크 … 비율" — i.e. the
# word "커버리지" being *defined* as a task pass ratio.
COLLAPSE_DEFINITION = re.compile(
    r"커버리지[^\n]{0,40}(?:통과|해결)[^\n]{0,8}(?:한|된)[^\n]{0,12}태스크[^\n]{0,12}비율"
)

# A bare "커버리지" table column (no "채점"/"집계" qualifier before it).
BARE_COVERAGE_COLUMN = re.compile(r"\|\s*커버리지\s*\|")


def _iter_doc_lines():
    """Yield (relpath, line_number, text) for every tracked docs Markdown line."""
    for path in sorted(DOCS.rglob("*.md")):
        rel = path.relative_to(DOCS).as_posix()
        for lineno, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            yield rel, lineno, text


def check_glossary() -> list[str]:
    """Rule A — the canonical glossary exists and names both terms."""
    if not GLOSSARY.exists():
        return [f"{GLOSSARY.relative_to(REPO_ROOT)} is missing (canonical glossary)"]
    text = GLOSSARY.read_text(encoding="utf-8")
    missing = [term for term in REQUIRED_GLOSSARY_TERMS if term not in text]
    if missing:
        return [
            "manual/glossary.md does not define required term(s): "
            + ", ".join(repr(term) for term in missing)
        ]
    return []


def check_no_collapse_definition() -> list[str]:
    """Rule B — no line re-defines 커버리지 as a task pass ratio.

    A reconciliation line that also uses "통과율" is intentionally mapping the
    two names together (커버리지 → 통과율) and is allowed.
    """
    failures: list[str] = []
    for rel, lineno, text in _iter_doc_lines():
        if COLLAPSE_DEFINITION.search(text) and "통과율" not in text:
            failures.append(
                f"{rel}:{lineno} defines '커버리지' as a task pass ratio without "
                f"using '통과율':\n    {text.strip()[:200]}"
            )
    return failures


def check_measured_pages_qualified() -> list[str]:
    """Rule C — measured pages use '채점 커버리지' and no bare coverage column."""
    failures: list[str] = []
    for rel in MEASURED_PAGES:
        path = DOCS / rel
        if not path.exists():
            failures.append(f"{rel} is missing (expected a measured-results page)")
            continue
        text = path.read_text(encoding="utf-8")
        if "채점 커버리지" not in text:
            failures.append(f"{rel} must use the qualified term '채점 커버리지'")
        for lineno, line in enumerate(text.splitlines(), 1):
            if BARE_COVERAGE_COLUMN.search(line):
                failures.append(
                    f"{rel}:{lineno} has a bare '| 커버리지 |' column — measured "
                    f"pages must qualify it as '채점 커버리지':\n    {line.strip()[:200]}"
                )
    return failures


def find_violations() -> list[str]:
    """Return every terminology violation across all rules."""
    return (
        check_glossary()
        + check_no_collapse_definition()
        + check_measured_pages_qualified()
    )


def main() -> int:
    violations = find_violations()
    if not violations:
        pages = sum(1 for _ in DOCS.rglob("*.md"))
        print(f"terminology: OK — glossary present, {pages} docs pages checked")
        return 0
    print(f"terminology: {len(violations)} violation(s):\n")
    for violation in violations:
        print(f"  {violation}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
