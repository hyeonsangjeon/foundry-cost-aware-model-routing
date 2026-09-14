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
import re
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
    ("스냅숏", "봉인된 스냅숏을 다시 읽습니다."),
    ("자격증명", "자격증명은 환경 변수로 전달합니다."),
    ("크리덴셜", "크리덴셜을 저장소에 넣지 않습니다."),
)

REINTRODUCTION_IDS = (
    "arm",
    "prereg",
    "pinned-rate",
    "exec-signals",
    "void-run",
    "scope-out",
    "snapshot",
    "credentials-spacing",
    "credentials-transliteration",
)

# Direction 2 — the keep list must pass. These are PR #132's 존치 10건 (code
# fence 1, 파일명 7, 스키마 키 2) plus the uppercase ``VOID`` status value and the
# ``무효(VOID)`` first-mention pattern: 12 sites that look like a retired term but
# are a name, a status value, or code. They are located by a stable token rather
# than a line number, so prose edits can move them without weakening the probe.
KEEP_SITES = (
    ("lab-notebook/11-router-modes-void.md", "파일명", "prereg-03d-router-modes.md"),
    ("lab-notebook/12-router-modes-measured.md", "파일명", "prereg-03d2-router-modes.md"),
    ("lab-notebook/13-router-modes-rate-card-gap.md", "파일명", "prereg-03d3-router-modes.md"),
    ("manual/measurement-protocol.md", "파일명", "prereg.md"),
    ("manual/measurement-protocol.md", "스키마 키", "`prereg`"),
    ("manual/measurement-protocol.md", "스키마 키", "benchmark.preregistration"),
    ("manual/prompt-cache-observed.md", "상태값 VOID", "(VOID)"),
    ("lab-notebook/11-router-modes-void.md", "무효(VOID) 최초 등장", "무효(VOID)"),
)

KEEP_SITE_IDS = tuple(f"{rel}:{token}" for rel, _, token in KEEP_SITES)


def _doc_token_lines(rel: str, token: str) -> list[tuple[int, str]]:
    lines = (REPO_ROOT / "docs" / "ko" / rel).read_text(encoding="utf-8").splitlines()
    return [(lineno, text) for lineno, text in enumerate(lines, 1) if token in text]


@pytest.mark.parametrize(("retired", "line"), REINTRODUCTIONS, ids=REINTRODUCTION_IDS)
def test_reintroducing_a_retired_term_is_flagged(retired: str, line: str):
    hits = [name for name, _ in terminology.retired_terms_in(line)]
    assert retired in hits, f"Rule D missed retired '{retired}' in: {line}"


@pytest.mark.parametrize(("retired", "line"), REINTRODUCTIONS, ids=REINTRODUCTION_IDS)
def test_the_failure_names_what_to_write_instead(retired: str, line: str):
    """A denylist that only says "no" leaves the next author guessing."""
    replacement = dict(terminology.retired_terms_in(line))[retired]
    assert replacement and retired not in replacement


@pytest.mark.parametrize(("rel", "reason", "token"), KEEP_SITES, ids=KEEP_SITE_IDS)
def test_keep_site_is_not_flagged(rel: str, reason: str, token: str):
    matches = _doc_token_lines(rel, token)
    assert matches, f"{rel} no longer holds the {reason} keep case {token!r}"
    violations = terminology.check_no_retired_terminology()
    for lineno, _ in matches:
        flagged = [v for v in violations if v.startswith(f"{rel}:{lineno} ")]
        assert flagged == [], (
            f"false positive on the {reason} keep case at {rel}:{lineno}:\n"
            + "\n".join(flagged)
        )


def test_rule_d_covers_exactly_the_six_retired_terms():
    assert [retired for _, retired, _ in terminology.RETIRED_TERMS] == [
        retired for retired, _ in REINTRODUCTIONS
    ]


def test_rule_d_skips_fenced_blocks(tmp_path, monkeypatch):
    """A retired word in a command example is code, but the same prose is not."""
    page = tmp_path / "manual"
    page.mkdir()
    (page / "fleet.md").write_text(
        "```text\n각 아암마다 번호를 입력합니다.\n```\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(terminology, "DOCS", tmp_path)
    assert terminology.check_no_retired_terminology() == []
    assert terminology.retired_terms_in("각 아암마다 번호를 입력합니다.")


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


def test_rule_d_scans_the_devlog_with_the_other_korean_pages():
    devlog = "lab-notebook/devlog.md"
    assert devlog not in terminology.RULE_D_EXCLUDED
    assert devlog in {rel for rel, _, _ in terminology._iter_rule_d_lines()}
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
# the confirmed wording replaced; since BOLT-12 Rule E scans the whole docs tree
# (README + every docs page), so these are what a future edit anywhere in docs
# would drift back to. If one stops being flagged, Rule E has gone blind for that
# term. Order matches RETIRED_FIRST_SCREEN_TERMS.
FIRST_SCREEN_REINTRODUCTIONS = (
    ("cockpit", "The local cockpit runs the same screen live against your Foundry."),
    ("콕핏", "로컬 콕핏은 같은 화면을 실시간으로 실행합니다."),
    ("ensemble tax", "It totals the extra candidate-call cost (**ensemble tax**)."),
    ("fan-out tax", "The fan-out tax counts the calls whose outputs are discarded."),
    ("앙상블 세금", "선택하지 않은 후보까지 포함한 호출 비용(**앙상블 세금**)을 합산합니다."),
    ("팬아웃 세금", "선택하지 않은 후보가 만든 팬아웃 세금을 합산합니다."),
    ("naive", "The naive baseline sends every task to the premium model."),
    ("나이브", "나이브 기준선은 모든 과제에 프리미엄 모델을 씁니다."),
    ("cost-aware mix", "The cost-aware mix escalates after a failed check."),
    ("비용 인지", "비용 인지 라우팅은 실패한 과제만 상위 모델로 보냅니다."),
    ("governor", "The governor stops additional calls at the spending limit."),
    ("거버너", "비용 거버너가 추가 호출을 막습니다."),
    ("폴백", "실패하면 폴백 모델을 호출합니다."),
    ("cost governor", "It stops at the approved spending limit (**cost governor**)."),
    ("비용 거버너", "승인한 지출 한도에서 멈춥니다(**비용 거버너**)."),
    ("wiring", "Read it as a five-prompt wiring proof, not a benchmark."),
    ("배선", "아직 최신 측정 배선이 반영되지 않았습니다."),
    ("human gate", "Nothing runs until a person chooses approve and run (the human gate)."),
    ("사람 게이트", "**승인하고 실행**(사람 게이트)을 선택하기 전에는 실행하지 않습니다."),
    ("flagship", "The flagship experiment runs in one shot."),
    ("플래그십", "플래그십 실험을 한 번에 실행합니다."),
    # BOLT-17 (#150) — hero prose retired to the default-experiment standard.
    ("hero workload", "The synthetic hero workload runs first."),
    ("hero baseline", "The hero baseline sets the price to beat."),
    ("hero loop", "The animated hero loop plays on the home page."),
    ("hero 루프", "홈에서 hero 루프 애니메이션이 재생됩니다."),
    ("hero border", "The winning card draws a hero border."),
    ("hero's hidden price", "The panel reveals the hero's hidden price."),
    ("Hero autorun", 'A tip titled "Hero autorun" explains the demo.'),
    ("01 / exp01 Hero label", "Run exp01 hero to reproduce it."),
    ("히어로", "이것은 히어로 데모 화면입니다."),
)

FIRST_SCREEN_IDS = (
    "cockpit-en", "cockpit-ko", "ensemble-tax-en", "fanout-tax-en",
    "ensemble-tax-ko", "fanout-tax-ko",
    "naive-en", "naive-ko", "cost-aware-mix-en", "cost-aware-mix-ko",
    "governor-en", "governor-ko", "fallback-ko",
    "cost-governor-en", "cost-governor-ko", "wiring-en", "wiring-ko",
    "human-gate-en", "human-gate-ko", "flagship-en", "flagship-ko",
    "hero-workload-en", "hero-baseline-en", "hero-loop-en", "hero-loop-ko",
    "hero-border-en", "hero-hidden-price-en", "hero-autorun-en",
    "exp01-hero-label", "hero-ko",
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


def test_rule_e_catches_a_retired_phrase_split_across_a_soft_wrap(tmp_path, monkeypatch):
    page = tmp_path / "home.md"
    page.write_text(
        "Nothing runs until a person chooses approve and run (the human\n"
        "gate).\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(terminology, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(terminology, "FIRST_SCREEN_SURFACES", ("home.md",))
    monkeypatch.setattr(terminology, "REPOSITORY_PROSE_SURFACES", ())
    monkeypatch.setattr(terminology, "INNER_PAGE_LOCALES", ())
    violations = terminology.check_no_retired_first_screen_terms()
    assert len(violations) == 1, violations
    assert "human gate" in violations[0] and ":1-2" in violations[0]


def test_rule_e_scans_inner_pages_and_their_h1_titles(tmp_path, monkeypatch):
    """BOLT-12 widened Rule E from the first screen to every docs page: a BOLT-10
    coinage on an inner manual page must fail now, where before it was out of
    scope. The H1 is reader-visible and is checked with the body."""
    page = tmp_path / "docs" / "en" / "manual" / "concept.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "# The flagship experiment\n\nThe flagship experiment runs in one shot.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(terminology, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(terminology, "FIRST_SCREEN_SURFACES", ())  # inner page only
    monkeypatch.setattr(terminology, "INNER_PAGE_LOCALES", ("docs/en",))
    monkeypatch.setattr(terminology, "INNER_PAGE_DIRS", ("manual",))
    monkeypatch.setattr(terminology, "INNER_PAGE_EXTRA", ())
    violations = terminology.check_no_retired_first_screen_terms()
    assert len(violations) == 2, violations
    assert {re.search(r":(\d+) reintroduces", v).group(1) for v in violations} == {
        "1",
        "3",
    }


def test_wiring_moved_from_rule_f_to_rule_e():
    """Dedupe: wiring / 배선 is now owned by Rule E (tree-wide), so Rule F must no
    longer gate it, while Rule E still catches the same line — no double-gating."""
    for line in ("For wiring details, see the section below.", "측정 배선이 빠졌습니다."):
        assert terminology.retired_inner_page_terms_in(line) == [], line
    assert [t for t, _ in terminology.retired_first_screen_terms_in(
        "For wiring details, see the section below.")] == ["wiring"]
    assert [t for t, _ in terminology.retired_first_screen_terms_in(
        "측정 배선이 빠졌습니다.")] == ["배선"]


# --- Rule F — retired inner-page jargon (BOLT-11 / #138) --------------------
#
# The BOLT-11 sibling of Rule E: the same denylist mechanism, on the inner
# manual / lab-notebook / honesty pages this wave cleaned. Direction 1 —
# reintroduction must fail. Each line is the shape the confirmed wording
# replaced; order matches RETIRED_INNER_PAGE_TERMS so the coverage assertion
# below can pair them one-to-one.
INNER_PAGE_REINTRODUCTIONS = (
    ("measured/measurement bridge", "The router's decision plugs in through the measured bridge."),
    ("측정/실측 브리지/브릿지", "실제 라우터의 결정을 실측 브릿지로 끼워 넣습니다."),
    ("spotlight", "The experiment spotlight shows the representative task."),
    ("스포트라이트", "실험 스포트라이트는 대표 태스크를 보여줍니다."),
    ("coverage cliff", "The coverage cliff shows the tasks a cheap-only router loses."),
    ("커버리지 절벽", "커버리지 절벽은 값싼 모델만 쓸 때 잃는 태스크를 보여줍니다."),
    ("slate", "Choose the models from the slate up front."),
    ("슬레이트", "미리 슬레이트에서 모델을 고릅니다."),
    ("fan-out dial", "Turn the fan-out dial to raise coverage."),
    ("팬아웃 다이얼", "팬아웃 다이얼을 돌려 커버리지를 올립니다."),
    ("arena (prose)", "The arena runs a four-way comparison across models."),
    ("아레나", "아레나는 네 가지 방식을 한 화면에서 비교합니다."),
    ("5-minute wow", "Try the 5-minute wow demo first."),
    ("5분 wow", "먼저 5분 wow 데모를 해보세요."),
    ("centerpiece", "This is the repo's centerpiece experiment."),
    ("센터피스", "이 저장소의 센터피스 실험입니다."),
    ("reproducibility contract", "The gain is pinned in the reproducibility contract."),
    ("재현성 계약", "이 이득은 재현성 계약으로 고정됩니다."),
    ("authority label", "Each claim keeps an authority label."),
    ("권한 라벨", "각 주장은 권한 라벨을 유지합니다."),
)

INNER_PAGE_IDS = (
    "bridge-en", "bridge-ko",
    "spotlight-en", "spotlight-ko", "coverage-cliff-en", "coverage-cliff-ko",
    "slate-en", "slate-ko", "fanout-dial-en", "fanout-dial-ko",
    "arena-en", "arena-ko", "wow-en", "wow-ko", "centerpiece-en", "centerpiece-ko",
    "reproducibility-contract-en", "reproducibility-contract-ko",
    "authority-label-en", "authority-label-ko",
)


@pytest.mark.parametrize(("retired", "line"), INNER_PAGE_REINTRODUCTIONS, ids=INNER_PAGE_IDS)
def test_reintroducing_an_inner_page_term_is_flagged(retired: str, line: str):
    hits = [name for name, _ in terminology.retired_inner_page_terms_in(line)]
    assert retired in hits, f"Rule F missed retired '{retired}' in: {line}"


@pytest.mark.parametrize(("retired", "line"), INNER_PAGE_REINTRODUCTIONS, ids=INNER_PAGE_IDS)
def test_the_inner_page_failure_names_what_to_write_instead(retired: str, line: str):
    replacement = dict(terminology.retired_inner_page_terms_in(line))[retired]
    assert replacement and retired not in replacement


def test_rule_f_covers_the_expected_terms():
    """Every gated inner-page term has a reintroduction probe, and vice versa."""
    assert [retired for _, retired, _ in terminology.RETIRED_INNER_PAGE_TERMS] == [
        retired for retired, _ in INNER_PAGE_REINTRODUCTIONS
    ]


def test_rule_f_masks_cli_and_config_tokens():
    """The CLI `arena`, config `slate` / `compare_min_value` in code spans are
    names, not prose — masked. Bare in prose, the same words are caught, so the
    mask is load-bearing (both directions in one probe)."""
    for keep in ("Run the `arena` command.", "Set `slate` in the config.",
                 "`compare_min_value` controls the fan-out threshold."):
        assert terminology.retired_inner_page_terms_in(keep) == [], keep
    assert [t for t, _ in terminology.retired_inner_page_terms_in("run the arena comparison")] == [
        "arena (prose)"
    ]
    slate_hits = [t for t, _ in terminology.retired_inner_page_terms_in("choose from the slate")]
    assert slate_hits == ["slate"]


def test_rule_f_masks_the_spotlight_card_ui_label():
    """"Spotlight card" is a dashboard label cited beside the plain term; masked.
    The bare concept word is still caught."""
    assert terminology.retired_inner_page_terms_in("the representative task (Spotlight card)") == []
    bare = [t for t, _ in terminology.retired_inner_page_terms_in("the experiment spotlight")]
    assert bare == ["spotlight"]


def test_rule_f_scans_the_h1_page_title(tmp_path, monkeypatch):
    """Page titles and body prose use the same reader-facing vocabulary."""
    page = tmp_path / "docs" / "en" / "manual" / "foundry-live.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "# The live measured bridge — a gated adapter\n\nThe measured bridge plugs in.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(terminology, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(terminology, "INNER_PAGE_LOCALES", ("docs/en",))
    monkeypatch.setattr(terminology, "INNER_PAGE_DIRS", ("manual",))
    monkeypatch.setattr(terminology, "INNER_PAGE_EXTRA", ())
    violations = terminology.check_no_retired_inner_page_terms()
    assert len(violations) == 2, violations
    assert {re.search(r":(\d+) reintroduces", v).group(1) for v in violations} == {
        "1",
        "3",
    }


def test_rule_f_skips_fenced_blocks(tmp_path, monkeypatch):
    """A retired word in a ```text sample block is CLI output, not prose."""
    page = tmp_path / "docs" / "en" / "manual" / "page.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("# Title\n\n```text\nspotlight  t-0078 · validate\n```\n", encoding="utf-8")
    monkeypatch.setattr(terminology, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(terminology, "INNER_PAGE_LOCALES", ("docs/en",))
    monkeypatch.setattr(terminology, "INNER_PAGE_DIRS", ("manual",))
    monkeypatch.setattr(terminology, "INNER_PAGE_EXTRA", ())
    assert terminology.check_no_retired_inner_page_terms() == []
    # break-the-rule: the same line as bare prose is caught, so the skip matters.
    assert terminology.retired_inner_page_terms_in("the spotlight task")


def test_rule_f_masks_inline_code_across_line_wraps(tmp_path, monkeypatch):
    """A signature or path can wrap a backtick span across a line break — the
    token inside is code, not prose. The same word bare in prose below is still
    caught, so the cross-line mask is load-bearing."""
    page = tmp_path / "docs" / "en" / "manual" / "page.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "# Title\n\n"
        "The strategies are pure functions:\n"
        "`cheapest_arm/router_arm(fleet, task, slate, pricing) ->\n"
        "ArmResult`. They inject a fake client.\n\n"
        "Then you branch the slate conditionally.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(terminology, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(terminology, "INNER_PAGE_LOCALES", ("docs/en",))
    monkeypatch.setattr(terminology, "INNER_PAGE_DIRS", ("manual",))
    monkeypatch.setattr(terminology, "INNER_PAGE_EXTRA", ())
    violations = terminology.check_no_retired_inner_page_terms()
    assert len(violations) == 1, violations       # the bare-prose line only
    assert ":7" in violations[0] and "slate" in violations[0]


@pytest.mark.parametrize(
    "footer",
    [
        "## Related documents\n\n- [Live measured bridge](foundry-live.md) — the page.\n",
        "**Related docs:** [Live measured bridge](foundry-live.md) ·\n(the offline comparison)\n",
        "**관련 문서:** [라이브 실측 브릿지](foundry-live.md) · [x](y.md)\n",
        "Related documents: [Live measured bridge](foundry-live.md) ·\n[Audit ledger](ledger.md)\n",
    ],
    ids=["heading", "bold-inline", "korean", "plain-inline"],
)
def test_rule_f_scans_the_related_documents_footer(tmp_path, monkeypatch, footer):
    """Navigation labels are reader-visible and follow the same vocabulary."""
    page = tmp_path / "docs" / "en" / "manual" / "page.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "# Title\n\nThe body mentions the coverage cliff plainly.\n\n" + footer,
        encoding="utf-8",
    )
    monkeypatch.setattr(terminology, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(terminology, "INNER_PAGE_LOCALES", ("docs/en",))
    monkeypatch.setattr(terminology, "INNER_PAGE_DIRS", ("manual",))
    monkeypatch.setattr(terminology, "INNER_PAGE_EXTRA", ())
    violations = terminology.check_no_retired_inner_page_terms()
    assert len(violations) == 2, violations
    assert any("coverage cliff" in violation for violation in violations)
    assert any(
        "measured/measurement bridge" in violation
        or "측정/실측 브리지/브릿지" in violation
        for violation in violations
    )


def test_rule_f_is_wired_into_find_violations(tmp_path, monkeypatch):
    """Rule F has to reach the exit code, not just be importable."""
    page = tmp_path / "docs" / "en" / "manual" / "page.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("# Title\n\nThe coverage cliff shows lost tasks.\n", encoding="utf-8")
    monkeypatch.setattr(terminology, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(terminology, "FIRST_SCREEN_SURFACES", ())  # keep Rule E off the temp tree
    monkeypatch.setattr(terminology, "INNER_PAGE_LOCALES", ("docs/en",))
    monkeypatch.setattr(terminology, "INNER_PAGE_DIRS", ("manual",))
    monkeypatch.setattr(terminology, "INNER_PAGE_EXTRA", ())
    assert any("retired 'coverage cliff'" in v for v in terminology.find_violations())


def test_rule_f_scans_the_devlog(tmp_path, monkeypatch):
    """Historical chronology does not exempt reader-facing terminology."""
    devlog = tmp_path / "docs" / "ko" / "lab-notebook" / "devlog.md"
    devlog.parent.mkdir(parents=True, exist_ok=True)
    devlog.write_text("# devlog\n\n측정 브리지로 연결했습니다.\n", encoding="utf-8")
    monkeypatch.setattr(terminology, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(terminology, "REPOSITORY_PROSE_SURFACES", ())
    monkeypatch.setattr(terminology, "INNER_PAGE_LOCALES", ("docs/ko",))
    monkeypatch.setattr(terminology, "INNER_PAGE_DIRS", ("lab-notebook",))
    monkeypatch.setattr(terminology, "INNER_PAGE_EXTRA", ())
    violations = terminology.check_no_retired_inner_page_terms()
    assert len(violations) == 1, violations
    assert "측정/실측 브리지/브릿지" in violations[0]


def test_rule_f_is_clean_on_the_repository():
    violations = terminology.check_no_retired_inner_page_terms()
    assert violations == [], "\n".join(violations)


def test_rule_f_catches_a_retired_phrase_split_across_a_soft_wrap(tmp_path, monkeypatch):
    page = tmp_path / "docs" / "en" / "manual" / "page.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "# Title\n\nTurn the fan-out\n"
        "dial only after measuring the extra calls.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(terminology, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(terminology, "REPOSITORY_PROSE_SURFACES", ())
    monkeypatch.setattr(terminology, "INNER_PAGE_LOCALES", ("docs/en",))
    monkeypatch.setattr(terminology, "INNER_PAGE_DIRS", ("manual",))
    monkeypatch.setattr(terminology, "INNER_PAGE_EXTRA", ())
    violations = terminology.check_no_retired_inner_page_terms()
    assert len(violations) == 1, violations
    assert "fan-out dial" in violations[0] and ":3-4" in violations[0]


# --- Rule G — Korean "replay" prose left untranslated (BOLT-17 / #150) -------
#
# "replay" is a live CLI verb (``measure replay``, ``ledger replay``), so unlike
# the retired coinages the rule is Korean-only and masks every surface BOLT-17
# keeps: inline code, the ``## replay —`` command heading and the "재생(replay)"
# first-mention gloss. What is left flagged is bare English "replay" in Korean
# prose, which should read 재생 (or 재현 for reproduction).
def test_rule_g_flags_bare_replay_in_korean_prose(tmp_path, monkeypatch):
    page = tmp_path / "manual"
    page.mkdir()
    (page / "run-plan.md").write_text(
        "이 실행은 replay 없이 진행됩니다.\n", encoding="utf-8"
    )
    monkeypatch.setattr(terminology, "DOCS", tmp_path)
    hits = terminology.check_no_untranslated_replay()
    assert any("leaves English 'replay'" in v for v in hits), hits


def test_rule_g_keeps_the_replay_code_surfaces(tmp_path, monkeypatch):
    """The CLI verb, its command heading and the first-mention gloss stay."""
    page = tmp_path / "manual"
    page.mkdir()
    (page / "cli.md").write_text(
        "## replay — 워크로드 재생\n\n"
        "`measure replay`로 봉인 기록을 재생합니다.\n\n"
        "이 단계는 재생(replay)으로 재현합니다.\n\n"
        "```bash\ncost-router measure replay\n```\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(terminology, "DOCS", tmp_path)
    assert terminology.check_no_untranslated_replay() == []


def test_rule_g_is_korean_only():
    """The rule reads docs/ko only — English pages keep 'replay' by design."""
    assert terminology.DOCS.name == "ko"
    assert terminology.DOCS.parent.name == "docs"


def test_rule_g_scans_the_devlog(tmp_path, monkeypatch):
    """The dated journal keeps chronology, not outdated reader terminology."""
    devlog = tmp_path / "lab-notebook" / "devlog.md"
    devlog.parent.mkdir(parents=True, exist_ok=True)
    devlog.write_text("측정은 replay 없이 진행했습니다.\n", encoding="utf-8")
    monkeypatch.setattr(terminology, "DOCS", tmp_path)
    assert "lab-notebook/devlog.md" not in terminology.RULE_D_EXCLUDED
    violations = terminology.check_no_untranslated_replay()
    assert len(violations) == 1, violations
    assert "leaves English 'replay'" in violations[0]


def test_rule_g_is_wired_into_find_violations(tmp_path, monkeypatch):
    """Rule G has to reach the exit code, not just be importable."""
    page = tmp_path / "manual"
    page.mkdir()
    (page / "run-plan.md").write_text(
        "이 실행은 replay 없이 진행됩니다.\n", encoding="utf-8"
    )
    monkeypatch.setattr(terminology, "DOCS", tmp_path)
    assert any("leaves English 'replay'" in v for v in terminology.find_violations())


def test_rule_g_is_clean_on_the_repository():
    violations = terminology.check_no_untranslated_replay()
    assert violations == [], "\n".join(violations)
