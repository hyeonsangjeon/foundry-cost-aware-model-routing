"""Terminology-collapse regression guard.

The word "커버리지" (coverage) used to name three different quantities, which put
"통과율 95.8%" next to "커버리지 94.4%" on the 03D page while the home page defined
the two as identical. These tests freeze the reconciliation into two distinct
terms — 통과율 (pass rate) vs 채점 커버리지 (grading coverage) — anchored by the
canonical glossary at ``docs/ko/manual/glossary.md``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = REPO_ROOT / "scripts" / "check_terminology.py"

_spec = importlib.util.spec_from_file_location("check_terminology", _MODULE_PATH)
assert _spec and _spec.loader
terminology = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = terminology
_spec.loader.exec_module(terminology)


def test_repository_terminology_is_consistent():
    violations = terminology.find_violations()
    assert violations == [], "\n".join(violations)


def test_glossary_defines_both_canonical_terms():
    assert terminology.check_glossary() == []
    text = (REPO_ROOT / "docs" / "ko" / "manual" / "glossary.md").read_text(encoding="utf-8")
    for term in terminology.REQUIRED_GLOSSARY_TERMS:
        assert term in text


def test_collapse_definition_pattern_flags_the_old_home_definition():
    """The pre-fix home wording defined 커버리지 as a task pass ratio."""
    old = "여기서 커버리지는 끝까지 통과(해결)한 태스크의 비율을 뜻합니다."
    assert terminology.COLLAPSE_DEFINITION.search(old)
    assert "통과율" not in old


def test_reconciliation_line_using_passrate_is_allowed():
    """A line mapping 커버리지 → 통과율 on purpose must not be flagged."""
    note = "이 실험에서 커버리지는 통과율(pass rate), 곧 통과(해결)한 태스크의 비율을 뜻합니다"
    assert terminology.COLLAPSE_DEFINITION.search(note)
    assert "통과율" in note  # the guard clause that exempts it


def test_bare_coverage_column_is_detected():
    assert terminology.BARE_COVERAGE_COLUMN.search("| 커버리지 | 100.0% |")
    assert not terminology.BARE_COVERAGE_COLUMN.search("| 채점 커버리지 | 96.18% |")


def test_measured_pages_use_qualified_grading_coverage():
    assert terminology.check_measured_pages_qualified() == []
