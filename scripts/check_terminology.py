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
  F. No inner-page prose (docs/en·docs/ko manual, lab-notebook, honesty — the
     ko devlog excluded, and each page's H1 title deferred to BOLT-12) reintroduces
     the jargon BOLT-11 (#138) retired: measured/measurement bridge, wiring proof,
     spotlight, coverage cliff, slate, fan-out dial, arena (as prose), 5-minute wow,
     centerpiece, reproducibility contract, authority label — and the Korean
     counterparts 측정 브리지/브릿지, 배선, 스포트라이트, 커버리지 절벽, 슬레이트,
     팬아웃 다이얼, 아레나, 5분 wow, 센터피스, 재현성 계약, 권한 라벨.

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
    "manual/routing-measured-results.md",
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

# Rule E — jargon BOLT-10 (#137) retired, as (pattern, retired, replacement). The
# confirmed wording replaced these coinages in place, first on the reader's first
# screen in each language (README + the two index pages named below).
#
# BOLT-12 (#139) widened the scan from those three files to the whole docs tree
# (README + every docs page in both locales, the ko devlog aside) once its item ④
# sweep had cleared the same coinages from the inner manual / lab-notebook pages —
# so that sweep cannot silently regress on an inner page. The masking is shared
# with Rule F: fenced blocks, each page's H1 title and the Related-documents
# footer are skipped, and code surfaces (the CLI ``hero`` identifier, the
# ``results/cockpit/<run-id>`` path token) are blanked, so an identifier is never
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

# Rule F — jargon BOLT-11 (#138) retired from the inner bilingual pages (manual,
# lab-notebook, honesty under docs/en and docs/ko), as (pattern, retired,
# replacement). It stays a *separate* rule from Rule E on purpose:
#
#   * provenance — these are the BOLT-11 coinages (spotlight, coverage cliff,
#     slate, arena, …); Rule E carries the BOLT-10 family and, since BOLT-12,
#     scans these same inner pages tree-wide. The one overlap, wiring / 배선, is
#     therefore owned by Rule E alone and dropped here, so a wiring line is never
#     gated twice.
#   * H1 titles — a page's H1 is nav surface and some are kept by design (e.g.
#     08-arena.md keeps "arena" in its title), so this rule skips each page's H1
#     line while still reading the body prose beneath it.
#
# Retained boundaries are masked exactly as Rule D/E mask them (fenced blocks
# skipped; inline code / links / URLs / anchor-fragments blanked), plus the
# HTML ``<a name="…">`` anchor and the dashboard UI label "Spotlight card" —
# the label is cited verbatim beside the plain term, so it must not read as the
# retired concept. The CLI ``arena``, config keys ``slate`` / ``compare_min_value``,
# and fixture filenames all live inside those masked code surfaces.
INNER_PAGE_LOCALES = ("docs/en", "docs/ko")
INNER_PAGE_DIRS = ("manual", "lab-notebook")
INNER_PAGE_EXTRA = ("honesty.md",)
INNER_PAGE_EXCLUDED = ("lab-notebook/devlog.md",)

RETIRED_INNER_PAGE_TERMS = (
    # item 1 — measurement seam (grading stays "grading integration", from BOLT-10)
    (re.compile(r"measure(?:d|ment)\s+bridge", re.IGNORECASE), "measured/measurement bridge",
     "the live measurement adapter (later: the measurement adapter)"),
    (re.compile(r"측정\s*브(?:릿|리)지"), "측정 브리지/브릿지",
     "라이브 실측 어댑터 (이후: 실측 어댑터)"),
    # item 2 — wiring / 배선 is a BOLT-10 term owned by Rule E (gated tree-wide
    # since BOLT-12); it is not repeated here so no line is gated twice, and
    # "wiring proof" is still caught by Rule E's \bwiring\b.
    # item 3 — spotlight (ko transliteration + en concept; "Spotlight card" UI label masked)
    (re.compile(r"\bspotlight\b", re.IGNORECASE), "spotlight",
     "the representative task"),
    (re.compile(r"스포트라이트"), "스포트라이트",
     "대표 태스크"),
    # item 4 — coverage cliff
    (re.compile(r"coverage\s+cliff", re.IGNORECASE), "coverage cliff",
     "the pass-rate cliff"),
    (re.compile(r"커버리지\s*절벽"), "커버리지 절벽",
     "통과율 절벽"),
    # item 5 — slate (config key `slate` masked as code)
    (re.compile(r"\bslate\b", re.IGNORECASE), "slate",
     "the candidate set (fan-out) / role assignment (fleet)"),
    (re.compile(r"슬레이트"), "슬레이트",
     "후보 모델 세트 / 역할 배정"),
    # item 6 — fan-out dial (config key `compare_min_value` masked as code)
    (re.compile(r"fan-?out\s+dial", re.IGNORECASE), "fan-out dial",
     "the fan-out threshold"),
    (re.compile(r"팬아웃\s*다이얼"), "팬아웃 다이얼",
     "팬아웃 임계값"),
    # item 7 — arena as prose (CLI `arena` + fixtures masked as code)
    (re.compile(r"\barena\b", re.IGNORECASE), "arena (prose)",
     "the four-way comparison (first mention: the `arena` command)"),
    (re.compile(r"아레나"), "아레나",
     "네 방식 비교"),
    # item 8 — 5-minute wow / centerpiece (the UI label "both-win" is kept, not gated)
    (re.compile(r"\d+-?\s*minute\s+wow", re.IGNORECASE), "5-minute wow",
     "delete the phrase"),
    (re.compile(r"\d+\s*분\s*wow", re.IGNORECASE), "5분 wow",
     "삭제"),
    (re.compile(r"centerpiece", re.IGNORECASE), "centerpiece",
     "Primary comparison"),
    (re.compile(r"센터피스"), "센터피스",
     "핵심 비교"),
    # item 9 — reproducibility contract (generic "contract"/"계약" is kept)
    (re.compile(r"reproducibility\s+contract", re.IGNORECASE), "reproducibility contract",
     "the reproducibility criteria"),
    (re.compile(r"재현성\s*계약"), "재현성 계약",
     "재현성 통과 기준"),
    # item 10 — authority label
    (re.compile(r"authority\s+label", re.IGNORECASE), "authority label",
     "claim-source label"),
    (re.compile(r"권한\s*라벨"), "권한 라벨",
     "주장 근거 라벨"),
)

# UI labels and HTML anchors masked before Rule F matches, on top of the shared
# code-surface mask. "Spotlight card" is a dashboard label cited beside the plain
# term ("the representative task (Spotlight card)"); the anchor name is a URL id.
_HTML_ANCHOR = re.compile(r'<a\s+name="[^"]*">')
_INNER_UI_LABELS = (
    re.compile(r"Spotlight\s+card", re.IGNORECASE),
)

# The "Related documents" / "관련 문서" footer links between pages — navigation,
# which is BOLT-12's surface — so Rule F does not scan it (e.g. a footer link to
# foundry-live.md keeps that page's retired title until BOLT-12 renames both). In
# every inner page the footer is the final block, so once its marker line is seen
# the rest of the file is skipped. The marker is a heading (`## Related
# documents`) or an inline label carrying a link on the same line.
_NAV_FOOTER = re.compile(
    r"^\s*(?:#{1,6}\s+|\*\*)?(?:Related documents|Related docs|관련 문서)\s*:?",
    re.IGNORECASE,
)

# Code surfaces stripped before Rule D matches. A term surviving all four is
# being read as prose. Order matters — code spans may themselves contain URLs.
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"`[^`]*`")
# Same span, but allowed to cross line wraps — a signature or path can open its
# backtick on one line and close it on the next (see _mask_inner_document).
_CODE_SPAN_MULTILINE = re.compile(r"`[^`]*`", re.DOTALL)
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


def _tree_wide_prose_files() -> list[Path]:
    """Rule E surfaces after BOLT-12: README plus every docs prose page — the
    ``FIRST_SCREEN_SURFACES`` first screen unioned with the Rule F inner pages
    (manual, lab-notebook, honesty, both locales; the ko devlog excluded). This is
    the whole tree the BOLT-10 family is now gated across, so the item ④ sweep
    cannot regress on an inner page.
    """
    files = [REPO_ROOT / rel for rel in FIRST_SCREEN_SURFACES]
    files.extend(_inner_page_files())
    return files


def retired_first_screen_terms_in(text: str) -> list[tuple[str, str]]:
    """Return (retired, replacement) for BOLT-10 terms left after the mask.

    Uses the same ``strip_inner_surfaces`` mask as Rule F (code surfaces plus the
    HTML anchor and UI labels), since BOLT-12 runs Rule E across the inner pages
    too, where those surfaces occur.
    """
    prose = strip_inner_surfaces(text)
    return [
        (retired, replacement)
        for pattern, retired, replacement in RETIRED_FIRST_SCREEN_TERMS
        if pattern.search(prose)
    ]


def check_no_retired_first_screen_terms() -> list[str]:
    """Rule E — no docs prose reintroduces jargon retired by BOLT-10.

    BOLT-12 widened this from the three first-screen files to the whole docs tree
    (``_tree_wide_prose_files``), reusing Rule F's line masking so retained code /
    path tokens and skipped H1 titles / footers behave identically.
    """
    failures: list[str] = []
    for rel, lineno, text, masked in _iter_prose_lines(_tree_wide_prose_files()):
        for retired, replacement in retired_first_screen_terms_in(masked):
            failures.append(
                f"{rel}:{lineno} reintroduces retired '{retired}' — "
                f"use '{replacement}':\n    {text.strip()[:200]}"
            )
    return failures


def _inner_page_files() -> list[Path]:
    """Return the Rule F surfaces: manual + lab-notebook + honesty, both locales.

    The ko-only ``lab-notebook/devlog.md`` is excluded (a dated journal, like Rule
    D). docs/en has no devlog; the suffix match covers whichever locale carries it.
    """
    files: list[Path] = []
    for locale in INNER_PAGE_LOCALES:
        base = REPO_ROOT / locale
        for sub in INNER_PAGE_DIRS:
            directory = base / sub
            if directory.is_dir():
                files.extend(sorted(directory.rglob("*.md")))
        for extra in INNER_PAGE_EXTRA:
            path = base / extra
            if path.exists():
                files.append(path)
    return [
        path
        for path in files
        if not any(
            path.as_posix().endswith(excluded) for excluded in INNER_PAGE_EXCLUDED
        )
    ]


def _nav_footer_start(lines: list[str]) -> int | None:
    """1-indexed line where the page's Related-documents footer nav begins, if any.

    The footer is either a ``## Related documents`` heading or an inline
    ``**Related docs:** [link]…`` paragraph; in every inner page it is the final
    block, so Rule F skips from here to EOF (nav is BOLT-12's surface).
    """
    for lineno, text in enumerate(lines, 1):
        if _NAV_FOOTER.match(text) and (re.match(r"\s*#{1,6}\s", text) or "](" in text):
            return lineno
    return None


def _mask_inner_document(lines: list[str], fenced: set[int]) -> list[str]:
    """Blank inline code spans across the whole page, including spans that wrap
    across a line break (e.g. a function signature or a path split for width), so
    Rule F never reads a code token as prose. Fenced lines are blanked first so
    their backticks cannot pair with inline ones; newlines and length are kept so
    line numbers stay aligned with the raw text.
    """
    prepped = [
        (" " * len(text)) if lineno in fenced else text
        for lineno, text in enumerate(lines, 1)
    ]
    masked = _CODE_SPAN_MULTILINE.sub(
        lambda match: re.sub(r"[^\n]", " ", match.group(0)), "\n".join(prepped)
    )
    return masked.split("\n")


def _iter_prose_lines(files: list[Path]):
    """Yield (relpath, line_number, raw, masked) prose lines for ``files``.

    Shared by Rule E (tree-wide) and Rule F (inner pages). Skips every line inside
    a fenced code block, each page's H1 title line (``# …`` — page titles are nav
    surface, some kept by design) and the Related-documents footer nav. ``masked``
    has inline code spans blanked across line wraps; the raw line is kept for the
    failure message.
    """
    for path in files:
        rel = path.relative_to(REPO_ROOT).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        fenced = fenced_line_numbers(lines)
        masked = _mask_inner_document(lines, fenced)
        footer = _nav_footer_start(lines)
        for lineno, text in enumerate(lines, 1):
            if lineno in fenced:
                continue
            if re.match(r"#\s", text):  # H1 page title — nav surface
                continue
            if footer is not None and lineno >= footer:  # nav footer
                continue
            yield rel, lineno, text, masked[lineno - 1]


def _iter_inner_page_lines():
    """Yield the Rule F prose lines — the inner manual / lab-notebook / honesty
    pages, masked by ``_iter_prose_lines``."""
    yield from _iter_prose_lines(_inner_page_files())


def strip_inner_surfaces(text: str) -> str:
    """Blank the code surfaces plus the HTML anchor and UI labels Rule F keeps."""
    text = strip_code_surfaces(text)
    text = _HTML_ANCHOR.sub(lambda match: " " * len(match.group(0)), text)
    for pattern in _INNER_UI_LABELS:
        text = pattern.sub(lambda match: " " * len(match.group(0)), text)
    return text


def retired_inner_page_terms_in(text: str) -> list[tuple[str, str]]:
    """Return (retired, replacement) for BOLT-11 terms left after the mask."""
    prose = strip_inner_surfaces(text)
    return [
        (retired, replacement)
        for pattern, retired, replacement in RETIRED_INNER_PAGE_TERMS
        if pattern.search(prose)
    ]


def check_no_retired_inner_page_terms() -> list[str]:
    """Rule F — no inner-page prose reintroduces jargon retired by BOLT-11."""
    failures: list[str] = []
    for rel, lineno, text, masked in _iter_inner_page_lines():
        for retired, replacement in retired_inner_page_terms_in(masked):
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
        + check_no_retired_inner_page_terms()
    )


def main() -> int:
    violations = find_violations()
    if not violations:
        pages = sum(1 for _ in DOCS.rglob("*.md"))
        print(
            f"terminology: OK — glossary present, {pages} docs pages checked, "
            f"{len(RETIRED_TERMS)} retired terms gated, "
            f"{len(RETIRED_FIRST_SCREEN_TERMS)} BOLT-10 terms gated tree-wide, "
            f"{len(RETIRED_INNER_PAGE_TERMS)} inner-page terms gated"
        )
        return 0
    print(f"terminology: {len(violations)} violation(s):\n")
    for violation in violations:
        print(f"  {violation}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
