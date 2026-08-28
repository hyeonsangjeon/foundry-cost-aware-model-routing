#!/usr/bin/env python3
"""Terminology guards for the Korean docs.

Two concerns live here. Rules A–C freeze the "커버리지" reconciliation described
below; Rule D keeps the wording retired by BOLT-06 (#129) from drifting back in,
and its BOLT-10 (#137) sibling (Rule E) does the same for the plain-language home
surfaces (README + the two ``index.md``).

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
  C. Every measured page (03D, 실험 11, 실험 12, 실험 13) — where the grading figure
     is read next to the pass rate — must use the qualified "채점 커버리지" and must
     not carry a bare ``| 커버리지 |`` table column.
  D. No Korean prose line reintroduces wording retired by BOLT-06 (#129):
     아암, prereg, pinned 요율, exec-signals, void 런, scope-out.
  E. No first-screen prose (README, docs/en/index.md, docs/ko/index.md)
     reintroduces the jargon BOLT-10 (#137) retired: cockpit, ensemble tax,
     cost governor, wiring, human gate, flagship — and the Korean counterparts
     콕핏, 앙상블 세금, 비용 거버너, 배선, 사람 게이트, 플래그십.

Rule D — what it does and does not look at
------------------------------------------

The audit BOLT-06 answered was not "the docs use English technical words". It
was a *regression*: a page settled on good Korean wording and another page drifted
back to the raw English. Rule D exists so the drift cannot happen silently again.

Rule D reports the retired string only. It deliberately does **not** propose a
per-site rewrite, because one of the six does not have a single correct form —
``scope-out`` landed as three different shapes in ``manual/fleet.md`` depending on
the grammar of the sentence it sits in (PR #132)::

    :83  warning 명사구   `provider: foundry`는 벤치마크 범위에서 제외 (…)
    :85  동사             …마이그레이션하지 않고 벤치마크 범위에서 제외했습니다
    :88  명사 주어         이 범위 제외는 코드로 강제됩니다

Those three are recorded here for reference; the denylist matches the retired
string and leaves the wording to the author.

A failing line is prose. Before matching, Rule D drops every code surface, in
this order, because each is a name rather than something a reader reads as a
sentence — a false positive here would read as a rule defect to the next person:

  1. whole fenced code blocks (``` … ```), e.g. the ``아암마다`` comment inside the
     ``cost-router models select`` block in ``manual/fleet.md``
  2. inline code spans, e.g. ``prereg``(commit_hash/committed_at/bypassed/note)
     and `` `prereg.md` `` — the schema key and the filename
  3. markdown link targets ``](…)`` and bare URLs — the four preregistration
     filenames appear inside GitHub blob links
  4. the preregistration filenames and the ``preregistration`` schema key by
     name, so they survive even unbackticked

Uppercase ``VOID`` is a status value, not prose, and is never matched: the
denylist entry is ``void 런`` specifically, so both a bare ``VOID`` column and the
first-mention pattern ``무효(VOID)`` pass untouched.

``lab-notebook/devlog.md`` is excluded. It is a dated Korean journal, so it is not
edited retroactively — BOLT-06 left it alone and Rule D must not fail on it.
Rules A–C keep scanning it, unchanged.

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
    "lab-notebook/13-router-modes-rate-card-gap.md",
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

# Rule D — wording retired by BOLT-06 (#129), as (pattern, 퇴역어, 정답). The
# 정답 column is what the docs settled on in PR #132; for scope-out it is the
# shared root, since that one took three sentence-shaped forms (see module docs).
RETIRED_TERMS = (
    (re.compile(r"아암"), "아암", "비교 전략 (페이지 최초 등장만 '비교 전략(arm)')"),
    (re.compile(r"prereg", re.IGNORECASE), "prereg", "사전등록"),
    (re.compile(r"pinned\s+요율", re.IGNORECASE), "pinned 요율", "고정 요율"),
    (re.compile(r"exec-signals", re.IGNORECASE), "exec-signals", "실행 신호"),
    (re.compile(r"void\s+런", re.IGNORECASE), "void 런", "무효 처리된 실행"),
    # scope-out has no single correct form — see the module docstring for the three.
    (re.compile(r"scope-out", re.IGNORECASE), "scope-out", "범위 제외 (자리별 형태는 위 참고)"),
)

# A dated Korean journal: written at a point in time, never edited retroactively.
# BOLT-06 skipped it, so Rule D must too. Rules A–C still read it.
RULE_D_EXCLUDED = ("lab-notebook/devlog.md",)

# Rule E — jargon BOLT-10 (#137) retired from the plain-language home surfaces,
# as (pattern, retired, replacement). These three files are the reader's first
# screen in each language; the confirmed wording replaced the coinages in place.
#
# Scope is deliberately the three cleaned files, not a tree-wide sweep. The same
# words legitimately still stand on lab-notebook page titles (BOLT-11) and the
# 03B/03D code surfaces (BOLT-12) that later waves own — gating the whole tree
# now would fail on out-of-scope lines and pre-empt those waves. Code surfaces
# (the CLI ``hero`` identifier, the ``results/cockpit/<run-id>`` path token) are
# masked before matching, exactly as Rule D masks them, so an identifier is never
# read as prose.
FIRST_SCREEN_SURFACES = (
    "README.md",
    "docs/en/index.md",
    "docs/ko/index.md",
)

RETIRED_FIRST_SCREEN_TERMS = (
    (re.compile(r"cockpit", re.IGNORECASE), "cockpit",
     "the browser run screen (first mention: the local browser run screen)"),
    (re.compile(r"콕핏"), "콕핏",
     "브라우저 실행 화면 (최초 등장: 로컬 브라우저 실행 화면)"),
    (re.compile(r"ensemble\s+tax", re.IGNORECASE), "ensemble tax",
     "drop the coinage — 'extra candidate-call cost'"),
    (re.compile(r"앙상블\s*세금"), "앙상블 세금",
     "조어 삭제 — '후보 호출 비용'"),
    (re.compile(r"cost\s+governor", re.IGNORECASE), "cost governor",
     "drop the coinage — 'spending limit'"),
    (re.compile(r"비용\s*거버너"), "비용 거버너",
     "조어 삭제 — '지출 한도'"),
    (re.compile(r"\bwiring\b", re.IGNORECASE), "wiring",
     "end-to-end call-path check / measurement path"),
    (re.compile(r"배선"), "배선",
     "측정 경로 / 측정 반영"),
    (re.compile(r"human\s+gate", re.IGNORECASE), "human gate",
     "drop the coinage — 'approve and run'"),
    (re.compile(r"사람\s*게이트"), "사람 게이트",
     "조어 삭제 — '승인하고 실행'"),
    (re.compile(r"flagship", re.IGNORECASE), "flagship",
     "the default cost-and-coverage experiment"),
    (re.compile(r"플래그십"), "플래그십",
     "기본 비용·통과율 실험"),
)

# Code surfaces stripped before Rule D matches. A term surviving all four is
# being read as prose. Order matters — code spans may themselves contain URLs.
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"`[^`]*`")
_LINK_TARGET = re.compile(r"\]\([^)]*\)")
_URL = re.compile(r"<?https?://[^\s>)]+>?")
_PREREG_FILENAME = re.compile(r"prereg(?:-03d[23]?-router-modes)?\.md")
_PREREG_SCHEMA_KEY = re.compile(r"preregistration")

_CODE_SURFACES = (
    _CODE_SPAN,
    _LINK_TARGET,
    _URL,
    _PREREG_FILENAME,
    _PREREG_SCHEMA_KEY,
)


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


def fenced_line_numbers(lines: list[str]) -> set[int]:
    """Return the 1-indexed line numbers inside fenced code blocks, fences included."""
    inside, opener, fenced = False, "", set()
    for lineno, text in enumerate(lines, 1):
        match = _FENCE.match(text)
        if match:
            token = match.group(1)[0]
            if not inside:
                inside, opener = True, token
                fenced.add(lineno)
                continue
            if token == opener:
                inside = False
                fenced.add(lineno)
                continue
        if inside:
            fenced.add(lineno)
    return fenced


def strip_code_surfaces(text: str) -> str:
    """Blank out the code surfaces Rule D must not read as prose.

    Replaces each match with spaces rather than deleting it, so a term is never
    formed by splicing the two sides of a removed span together.
    """
    for pattern in _CODE_SURFACES:
        text = pattern.sub(lambda match: " " * len(match.group(0)), text)
    return text


def retired_terms_in(text: str) -> list[tuple[str, str]]:
    """Return (퇴역어, 정답) for every retired term left after the keep-list mask."""
    prose = strip_code_surfaces(text)
    return [
        (retired, replacement)
        for pattern, retired, replacement in RETIRED_TERMS
        if pattern.search(prose)
    ]


def _iter_rule_d_lines():
    """Yield (relpath, line_number, text) for the prose lines Rule D judges.

    Skips the devlog and every line inside a fenced code block. Rules A–C keep
    using ``_iter_doc_lines`` and are unaffected.
    """
    for path in sorted(DOCS.rglob("*.md")):
        rel = path.relative_to(DOCS).as_posix()
        if rel in RULE_D_EXCLUDED:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        fenced = fenced_line_numbers(lines)
        for lineno, text in enumerate(lines, 1):
            if lineno not in fenced:
                yield rel, lineno, text


def check_no_retired_terminology() -> list[str]:
    """Rule D — no prose line reintroduces wording retired by BOLT-06."""
    failures: list[str] = []
    for rel, lineno, text in _iter_rule_d_lines():
        for retired, replacement in retired_terms_in(text):
            failures.append(
                f"{rel}:{lineno} reintroduces retired '{retired}' — "
                f"use '{replacement}':\n    {text.strip()[:200]}"
            )
    return failures


def _iter_first_screen_lines():
    """Yield (relpath, line_number, text) for the BOLT-10 first-screen prose lines.

    Fenced code blocks are skipped and, per line, inline code / links / URLs are
    masked by ``retired_first_screen_terms_in`` — so ``cost-router hero`` and the
    ``results/cockpit/<run-id>`` path never register as prose.
    """
    for rel in FIRST_SCREEN_SURFACES:
        lines = (REPO_ROOT / rel).read_text(encoding="utf-8").splitlines()
        fenced = fenced_line_numbers(lines)
        for lineno, text in enumerate(lines, 1):
            if lineno not in fenced:
                yield rel, lineno, text


def retired_first_screen_terms_in(text: str) -> list[tuple[str, str]]:
    """Return (retired, replacement) for BOLT-10 terms left after the code mask."""
    prose = strip_code_surfaces(text)
    return [
        (retired, replacement)
        for pattern, retired, replacement in RETIRED_FIRST_SCREEN_TERMS
        if pattern.search(prose)
    ]


def check_no_retired_first_screen_terms() -> list[str]:
    """Rule E — no first-screen prose reintroduces jargon retired by BOLT-10."""
    failures: list[str] = []
    for rel, lineno, text in _iter_first_screen_lines():
        for retired, replacement in retired_first_screen_terms_in(text):
            failures.append(
                f"{rel}:{lineno} reintroduces retired '{retired}' — "
                f"use '{replacement}':\n    {text.strip()[:200]}"
            )
    return failures


def find_violations() -> list[str]:
    """Return every terminology violation across all rules."""
    return (
        check_glossary()
        + check_no_collapse_definition()
        + check_measured_pages_qualified()
        + check_no_retired_terminology()
        + check_no_retired_first_screen_terms()
    )


def main() -> int:
    violations = find_violations()
    if not violations:
        pages = sum(1 for _ in DOCS.rglob("*.md"))
        print(
            f"terminology: OK — glossary present, {pages} docs pages checked, "
            f"{len(RETIRED_TERMS)} retired terms gated, "
            f"{len(RETIRED_FIRST_SCREEN_TERMS)} first-screen terms gated"
        )
        return 0
    print(f"terminology: {len(violations)} violation(s):\n")
    for violation in violations:
        print(f"  {violation}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
