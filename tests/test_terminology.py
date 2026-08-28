"""Terminology-collapse regression guard.

The word "커버리지" (coverage) used to name three different quantities, which put
"통과율 95.8%" next to "커버리지 94.4%" on the 03D page while the home page defined
the two as identical. These tests freeze the reconciliation into two distinct
terms — 통과율 (pass rate) vs 채점 커버리지 (grading coverage) — anchored by the
canonical glossary at ``docs/ko/manual/glossary.md``.

The Rule D block at the bottom guards a second regression: wording BOLT-06 (#129)
retired from Korean prose drifting back in. Every retired term is probed in both
directions — reintroducing it must fail, and the keep forms recorded in PR #132
must pass — because a denylist checked in one direction only can be a rule that
catches nothing and still reports OK.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

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


# --- Rule D — retired-terminology denylist (BOLT-07 / #130) -----------------
#
# Direction 1 — reintroduction must fail. Each line is the wording that actually
# stood in the docs before PR #132 replaced it, so these are the exact sentences
# a future edit would drift back to. If one of them stops being flagged, the
# denylist has gone blind for that term.
REINTRODUCTIONS = (
    ("아암", "카탈로그를 보고 각 아암에 어떤 모델을 넣을지 고릅니다."),
    ("prereg", "prereg 커밋이 실행보다 앞섬(D8 게이트)."),
    ("pinned 요율", "unpriced 0%로, 모든 셀이 pinned 요율로 가격화됐다."),
    ("exec-signals", "| pass rate 95.8–100% | 결정론적 exec-signals 채점기를 통과함 |"),
    ("void 런", "결과는 직전 void 런과 이번 publishable 런에서 두 번 재현됐다."),
    ("scope-out", "이 scope-out은 **코드로 강제**됩니다: 벤치마크 모드에서 막습니다."),
)

REINTRODUCTION_IDS = ("arm", "prereg", "pinned-rate", "exec-signals", "void-run", "scope-out")

# Direction 2 — the keep list must pass. These are PR #132's 존치 10건 (code
# fence 1, 파일명 7, 스키마 키 2) plus the uppercase ``VOID`` status value and the
# ``무효(VOID)`` first-mention pattern: 12 sites that look like a retired term but
# are a name, a status value, or code. They are addressed by (file, line) and read
# from the tree rather than transcribed, so the probe tests the real text — and
# fails loudly if the line moves instead of silently checking a blank.
KEEP_SITES = (
    ("manual/fleet.md", 101, "코드 펜스", "아암마다"),
    ("lab-notebook/11-router-modes-void.md", 35, "파일명", "prereg-03d-router-modes.md"),
    ("lab-notebook/11-router-modes-void.md", 133, "파일명", "prereg-03d-router-modes.md"),
    ("lab-notebook/12-router-modes-measured.md", 34, "파일명", "prereg-03d2-router-modes.md"),
    ("lab-notebook/12-router-modes-measured.md", 143, "파일명", "prereg-03d2-router-modes.md"),
    ("lab-notebook/13-router-modes-rate-card-gap.md", 205, "파일명", "prereg-03d3-router-modes.md"),
    ("manual/measurement-protocol.md", 66, "파일명", "prereg.md"),
    ("manual/measurement-protocol.md", 92, "파일명", "`prereg.md`"),
    ("manual/measurement-protocol.md", 77, "스키마 키", "`prereg`"),
    ("manual/measurement-protocol.md", 227, "스키마 키", "benchmark.preregistration"),
    ("manual/prompt-cache-observed.md", 97, "상태값 VOID", "(VOID)"),
    ("lab-notebook/11-router-modes-void.md", 7, "무효(VOID) 최초 등장", "무효(VOID)"),
)

KEEP_SITE_IDS = tuple(f"{rel}:{lineno}" for rel, lineno, _, _ in KEEP_SITES)


def _doc_line(rel: str, lineno: int) -> str:
    lines = (REPO_ROOT / "docs" / "ko" / rel).read_text(encoding="utf-8").splitlines()
    assert lineno <= len(lines), f"{rel} has no line {lineno}"
    return lines[lineno - 1]


@pytest.mark.parametrize(("retired", "line"), REINTRODUCTIONS, ids=REINTRODUCTION_IDS)
def test_reintroducing_a_retired_term_is_flagged(retired: str, line: str):
    hits = [name for name, _ in terminology.retired_terms_in(line)]
    assert retired in hits, f"Rule D missed retired '{retired}' in: {line}"


@pytest.mark.parametrize(("retired", "line"), REINTRODUCTIONS, ids=REINTRODUCTION_IDS)
def test_the_failure_names_what_to_write_instead(retired: str, line: str):
    """A denylist that only says "no" leaves the next author guessing."""
    replacement = dict(terminology.retired_terms_in(line))[retired]
    assert replacement and retired not in replacement


@pytest.mark.parametrize(("rel", "lineno", "reason", "token"), KEEP_SITES, ids=KEEP_SITE_IDS)
def test_keep_site_is_not_flagged(rel: str, lineno: int, reason: str, token: str):
    text = _doc_line(rel, lineno)
    assert token in text, f"{rel}:{lineno} no longer holds the {reason} keep case"
    flagged = [
        v for v in terminology.check_no_retired_terminology() if v.startswith(f"{rel}:{lineno} ")
    ]
    assert flagged == [], f"false positive on the {reason} keep case:\n" + "\n".join(flagged)


def test_rule_d_covers_exactly_the_six_retired_terms():
    assert [retired for _, retired, _ in terminology.RETIRED_TERMS] == [
        retired for retired, _ in REINTRODUCTIONS
    ]


def test_the_fence_is_what_saves_the_models_select_comment():
    """fleet.md:101 passes because of the fence, not a weak pattern.

    Both directions in one probe: read as bare prose the comment *would* be
    flagged, so the keep case is genuinely load-bearing on fence detection.
    """
    rel, lineno = "manual/fleet.md", 101
    lines = (REPO_ROOT / "docs" / "ko" / rel).read_text(encoding="utf-8").splitlines()
    assert terminology.retired_terms_in(lines[lineno - 1]), "would be flagged as prose"
    assert lineno in terminology.fenced_line_numbers(lines)
    assert (rel, lineno) not in {(r, n) for r, n, _ in terminology._iter_rule_d_lines()}


def test_masking_does_not_hide_prose_beside_a_code_span():
    """Code surfaces are blanked, not deleted — the sentence around them survives."""
    assert terminology.retired_terms_in("`plan_hash`는 prereg 커밋보다 뒤에 온다")
    assert terminology.retired_terms_in("[문서](../a.md)에서 이 scope-out은 강제된다")


def test_masking_blanks_a_code_span_rather_than_deleting_it():
    """Deleting a span would splice its neighbours into a term nobody wrote.

    Synthetic line: no page reads like this today. It pins the equal-length
    substitution so a shortening mask cannot manufacture a false positive.
    """
    spliced = "scope-`arm`out은 낱말이 아니다"
    assert terminology.strip_code_surfaces(spliced) == "scope-     out은 낱말이 아니다"
    assert terminology.retired_terms_in(spliced) == []


def test_uppercase_void_run_is_caught_but_a_bare_status_value_is_not():
    assert terminology.retired_terms_in("지난 VOID 런에서 quality 게이트가 떨어졌다")
    assert terminology.retired_terms_in("| 런 상태 | VOID | 채점 커버리지 79.2% |") == []


def test_rule_d_skips_the_devlog_while_rules_abc_still_read_it():
    devlog = "lab-notebook/devlog.md"
    assert devlog in terminology.RULE_D_EXCLUDED
    assert devlog not in {rel for rel, _, _ in terminology._iter_rule_d_lines()}
    assert devlog in {rel for rel, _, _ in terminology._iter_doc_lines()}


def test_rule_d_is_wired_into_find_violations(tmp_path, monkeypatch):
    """Rule D has to reach the exit code, not just be importable."""
    page = tmp_path / "manual"
    page.mkdir()
    (page / "cli.md").write_text("각 아암에 어떤 모델을 넣을지 고릅니다.\n", encoding="utf-8")
    monkeypatch.setattr(terminology, "DOCS", tmp_path)
    assert any("retired '아암'" in v for v in terminology.find_violations())


def test_rule_d_is_clean_on_the_repository():
    violations = terminology.check_no_retired_terminology()
    assert violations == [], "\n".join(violations)


# --- Rule E — retired first-screen jargon (BOLT-10 / #137) ------------------
#
# Direction 1 — reintroduction must fail. Each line is the shape of the coinage
# the confirmed wording replaced on README / docs/en/index.md / docs/ko/index.md,
# so these are what a future edit would drift back to. If one stops being flagged,
# Rule E has gone blind for that term. Order matches RETIRED_FIRST_SCREEN_TERMS.
FIRST_SCREEN_REINTRODUCTIONS = (
    ("cockpit", "The local cockpit runs the same screen live against your Foundry."),
    ("콕핏", "로컬 콕핏은 같은 화면을 실시간으로 실행합니다."),
    ("ensemble tax", "It totals the extra candidate-call cost (**ensemble tax**)."),
    ("앙상블 세금", "선택하지 않은 후보까지 포함한 호출 비용(**앙상블 세금**)을 합산합니다."),
    ("cost governor", "It stops at the approved spending limit (**cost governor**)."),
    ("비용 거버너", "승인한 지출 한도에서 멈춥니다(**비용 거버너**)."),
    ("wiring", "Read it as a five-prompt wiring proof, not a benchmark."),
    ("배선", "아직 최신 측정 배선이 반영되지 않았습니다."),
    ("human gate", "Nothing runs until a person chooses approve and run (the human gate)."),
    ("사람 게이트", "**승인하고 실행**(사람 게이트)을 선택하기 전에는 실행하지 않습니다."),
    ("flagship", "The flagship experiment runs in one shot."),
    ("플래그십", "플래그십 실험을 한 번에 실행합니다."),
)

FIRST_SCREEN_IDS = (
    "cockpit-en", "cockpit-ko", "ensemble-tax-en", "ensemble-tax-ko",
    "cost-governor-en", "cost-governor-ko", "wiring-en", "wiring-ko",
    "human-gate-en", "human-gate-ko", "flagship-en", "flagship-ko",
)


@pytest.mark.parametrize(("retired", "line"), FIRST_SCREEN_REINTRODUCTIONS, ids=FIRST_SCREEN_IDS)
def test_reintroducing_a_first_screen_term_is_flagged(retired: str, line: str):
    hits = [name for name, _ in terminology.retired_first_screen_terms_in(line)]
    assert retired in hits, f"Rule E missed retired '{retired}' in: {line}"


@pytest.mark.parametrize(("retired", "line"), FIRST_SCREEN_REINTRODUCTIONS, ids=FIRST_SCREEN_IDS)
def test_the_first_screen_failure_names_what_to_write_instead(retired: str, line: str):
    """A denylist that only says "no" leaves the next author guessing."""
    replacement = dict(terminology.retired_first_screen_terms_in(line))[retired]
    assert replacement and retired not in replacement


def test_rule_e_covers_the_expected_terms():
    """Every gated term has a reintroduction probe, and vice versa."""
    assert [retired for _, retired, _ in terminology.RETIRED_FIRST_SCREEN_TERMS] == [
        retired for retired, _ in FIRST_SCREEN_REINTRODUCTIONS
    ]


def test_rule_e_masks_the_cockpit_path_token():
    """`results/cockpit/<run-id>` in a code span is a path, not prose.

    Both directions in one probe: unfenced, the same word is caught — so the mask
    is genuinely load-bearing, not a rule that would pass either way.
    """
    masked = "then shows live progress and replays the `results/cockpit/<run-id>` snapshot."
    assert terminology.retired_first_screen_terms_in(masked) == []
    assert [t for t, _ in terminology.retired_first_screen_terms_in("the cockpit run path")] == [
        "cockpit"
    ]


def test_rule_e_keeps_the_cockpit_path_token_in_the_real_docs():
    """The `results/cockpit/<run-id>` keep case lives in both index files today.

    Read from the tree (not transcribed) so the probe fails loudly if the token
    moves out of code into prose instead of silently checking nothing.
    """
    seen = 0
    for rel in terminology.FIRST_SCREEN_SURFACES:
        for line in (REPO_ROOT / rel).read_text(encoding="utf-8").splitlines():
            if "results/cockpit/<run-id>" in line:
                seen += 1
                assert terminology.retired_first_screen_terms_in(line) == [], (
                    f"{rel}: cockpit path token read as prose:\n    {line.strip()}"
                )
    assert seen >= 2, "the cockpit-path keep case vanished from the home surfaces"


def test_rule_e_skips_fenced_cli_comments(tmp_path, monkeypatch):
    """A retired word in a ```bash comment is code, not prose — Rule E skips it."""
    body = "```bash\ncost-router hero   # run the flagship experiment\n```\n"
    (tmp_path / "home.md").write_text(body, encoding="utf-8")
    monkeypatch.setattr(terminology, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(terminology, "FIRST_SCREEN_SURFACES", ("home.md",))
    assert terminology.check_no_retired_first_screen_terms() == []
    # break-the-rule: the same comment as bare prose is caught, so the skip matters.
    assert terminology.retired_first_screen_terms_in("run the flagship experiment")


def test_rule_e_is_wired_into_find_violations(tmp_path, monkeypatch):
    """Rule E has to reach the exit code, not just be importable."""
    (tmp_path / "home.md").write_text("The local cockpit runs the screen.\n", encoding="utf-8")
    monkeypatch.setattr(terminology, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(terminology, "FIRST_SCREEN_SURFACES", ("home.md",))
    assert any("retired 'cockpit'" in v for v in terminology.find_violations())


def test_rule_e_is_clean_on_the_repository():
    violations = terminology.check_no_retired_first_screen_terms()
    assert violations == [], "\n".join(violations)
