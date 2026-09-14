"""Locale purity of the *dynamic* demo surfaces.

The static template is covered by :mod:`tests.test_demo_i18n`. This module locks
the other half: everything the browser builds at render time from a payload —
the compare ("one problem, four strategies") panel, the model catalog, the
experiment contract checks and every sentence assembled in JavaScript.

Two invariants:

* ``/ko/demo/`` must not render English prose. Identifiers are exempt by
  construction: task ids, model names, task classes in the routing trace, routing
  modes, escalation reasons and the raw contract keys are code, and the demo's own
  legend spells them out.
* ``/demo/`` must not render Korean, and neither locale may reintroduce the
  wording the reader-facing surfaces retired (``fan-out tax``, ``naive``,
  ``premium-grade`` and friends).

The Korean check runs against the *rendered* output, not just the payload: a
small Node harness executes the exported page's own script over the exported
JSON with a stub DOM and reports every string the page wrote.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from router import demo_i18n as di  # noqa: E402
from router.server import RouterService  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import build_static_site as bss  # noqa: E402

HANGUL = re.compile(r"[\uac00-\ud7a3]")
TAG = re.compile(r"<[^>]+>")

# Wording retired from every reader-facing surface. ``coverage`` is deliberately
# absent: it survives only as a raw contract key rendered inside <code>, which is
# asserted separately below.
RETIRED = (
    "fan-out tax",
    "ensemble tax",
    "Cost-aware router",
    "highest coverage",
    "premium-grade",
    "cheap but wrong",
    "the naive ceiling",
    "naive",
    "나이브",
    "Ensemble (fan-out)",
    "%p",
    "5-minute",
    "커버리지",
)


@pytest.fixture(scope="module")
def compare_payload() -> dict:
    return RouterService().dispatch("GET", "/compare").payload


def test_english_compare_localization_is_a_no_op(compare_payload: dict) -> None:
    # The English side is rebuilt from the same structured fields router.arena
    # used, so a reworded strategy in arena.py shows up here as a diff rather
    # than as a silently stale Korean translation.
    original = json.loads(json.dumps(compare_payload, ensure_ascii=False))
    rebuilt = di.localize_compare(
        json.loads(json.dumps(compare_payload, ensure_ascii=False)), "en"
    )
    assert rebuilt == original


def test_korean_compare_payload_has_no_english_prose(compare_payload: dict) -> None:
    ko = di.localize_compare(
        json.loads(json.dumps(compare_payload, ensure_ascii=False)), "ko"
    )
    assert not bss._english_prose_leaks(ko)
    # Every authored problem, both list and detail view, is actually Korean.
    for entry in ko["tasks"]:
        assert HANGUL.search(entry["title"]), entry["task_id"]
        assert HANGUL.search(entry["teaches"]), entry["task_id"]
        assert HANGUL.search(entry["class"]) and HANGUL.search(entry["difficulty"])
    for arena in ko["arenas"].values():
        problem = arena.get("problem") or {}
        for field in ("title", "prompt", "acceptance"):
            assert HANGUL.search(problem[field]), (arena["task_id"], field)
        for approach in arena["approaches"]:
            assert HANGUL.search(approach["label"]), approach["approach"]
            assert HANGUL.search(approach["detail"]), approach["approach"]


def test_compare_localization_keeps_identifiers_and_numbers(compare_payload: dict) -> None:
    source = json.loads(json.dumps(compare_payload, ensure_ascii=False))
    ko = di.localize_compare(
        json.loads(json.dumps(compare_payload, ensure_ascii=False)), "ko"
    )
    assert ko["default"] == source["default"]
    for tid, arena in ko["arenas"].items():
        src = source["arenas"][tid]
        assert arena["task_id"] == src["task_id"]
        assert arena["candidates"] == src["candidates"]
        assert arena["tokens"] == src["tokens"]
        assert arena["winners"] == src["winners"]
        assert arena["labels"] == src["labels"]
        for new, old in zip(arena["approaches"], src["approaches"], strict=True):
            assert new["models"] == old["models"]
            assert new["chosen_model"] == old["chosen_model"]
            assert new["cost_usd"] == old["cost_usd"]
            assert new["latency_ms"] == old["latency_ms"]
            assert new["passed"] == old["passed"]
            # A strategy that names its model in English still names it in Korean.
            # The fan-out detail counts candidates instead of listing them.
            if old["approach"] != "ensemble":
                for model in old["models"]:
                    assert model in new["detail"]


def test_unknown_task_or_approach_fails_closed() -> None:
    payload = {
        "tasks": [],
        "arenas": {
            "t-9999": {
                "task_id": "t-9999",
                "class": "generate",
                "difficulty": "easy",
                "problem": {"title": "x", "prompt": "y", "acceptance": "z"},
                "approaches": [],
            }
        },
    }
    with pytest.raises(AssertionError):
        di.localize_compare(payload, "ko")


def test_korean_policy_catalog_has_no_english_prose() -> None:
    policy = RouterService().dispatch("GET", "/policy").payload
    ko = di.localize_policy(json.loads(json.dumps(policy, ensure_ascii=False)), "ko")
    assert not bss._english_prose_leaks(ko)
    for entry in ko["catalog"]:
        assert HANGUL.search(entry["tier"]) and HANGUL.search(entry["role"])
        assert HANGUL.search(entry["reasoning"])
    # Model ids are identifiers and stay exactly as they were.
    assert [e["model"] for e in ko["catalog"]] == [e["model"] for e in policy["catalog"]]


def test_korean_prose_guard_catches_two_word_and_hyphenated_leaks() -> None:
    payload = {
        "detail": (
            "observe-then-escalate 100.0% − single-call 52.0% "
            "= +48.0 percentage points"
        )
    }
    assert bss._english_prose_leaks(payload)


def test_contract_check_keys_have_a_label_in_both_locales() -> None:
    service = RouterService()
    names = {
        check["name"]
        for experiment in service.dispatch("GET", "/experiments").payload["experiments"]
        for check in experiment.get("checks") or []
    }
    assert names, "the experiments payload must carry contract checks"
    for locale in ("en", "ko"):
        labels = di.dynamic_payload(locale)["checkLabels"]
        missing = sorted(n for n in names if n not in labels)
        assert not missing, f"{locale} has no label for contract check(s): {missing}"


def test_dynamic_table_is_single_language() -> None:
    en = di.dynamic_payload("en")
    ko = di.dynamic_payload("ko")
    assert set(en) == set(ko)
    assert not HANGUL.search(json.dumps(en, ensure_ascii=False))
    # Every Korean entry that carries prose is actually Korean. Entries that are
    # pure markup, placeholders or shared code tokens are exempt.
    exempt = {"checkTerms", "checkLabels", "journeyMeta", "aUnitMs"}
    for key, value in ko.items():
        if key in exempt or not isinstance(value, str):
            continue
        stripped = TAG.sub("", value)
        stripped = re.sub(r"\{\w+\}", "", stripped)
        if re.search(r"[A-Za-z]{4,}", stripped):
            assert HANGUL.search(stripped), f"ko.{key} looks untranslated: {value!r}"


@pytest.mark.parametrize("locale", ["en", "ko"])
def test_rendered_demo_is_single_language_and_free_of_retired_wording(
    locale: str, tmp_path: Path
) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    out = tmp_path / locale
    bss.build(out, locale)
    harness = REPO_ROOT / "tests" / "data" / "render_demo.js"
    proc = subprocess.run(
        [node, str(harness), str(out)], capture_output=True, text=True, timeout=180
    )
    assert proc.returncode == 0, proc.stderr
    written = json.loads(proc.stdout)
    assert len(written) > 50, "the harness rendered almost nothing — check the stub DOM"
    text = TAG.sub(" ", " ".join(written))

    hits = [term for term in RETIRED if term in text]
    assert not hits, f"{locale} demo renders retired wording: {hits}"

    if locale == "en":
        assert not HANGUL.search(text), "the English demo renders Korean"
        return

    assert "percentage points" not in text
    assert "퍼센트포인트" in text

    # The Korean demo may still render identifiers. Everything that is not one
    # must carry Korean.
    identifiers = _identifier_vocabulary()
    for chunk in written:
        plain = re.sub(r"\s+", " ", TAG.sub(" ", chunk)).strip()
        if not plain or HANGUL.search(plain):
            continue
        # Task ids (``t-0078``) are identifiers; drop them before matching.
        plain_words = re.sub(r"\bt-\d{4}\b", " ", plain)
        words = {w for w in re.findall(r"[A-Za-z][\w.-]{2,}", plain_words)}
        unexpected = sorted(words - identifiers)
        assert not unexpected, f"ko demo renders English word(s) {unexpected} in: {plain[:120]!r}"


def _identifier_vocabulary() -> set[str]:
    """Code tokens the Korean demo is allowed to render verbatim."""
    service = RouterService()
    policy = service.dispatch("GET", "/policy").payload
    vocabulary = {c["model"] for c in policy["catalog"]}
    vocabulary |= set(policy["classes"])              # task classes in the trace
    vocabulary |= {"ordered", "compare"}              # routing modes
    vocabulary |= {"clean-first", "escalated", "compared", "tie-broken"}
    vocabulary |= {                                    # experiment ids (tab labels)
        e["name"] for e in service.dispatch("GET", "/experiments").payload["experiments"]
    }
    vocabulary |= set(di.dynamic_payload("en")["checkLabels"])  # raw contract keys
    vocabulary |= {"measured", "false", "true"}        # honesty label values
    return vocabulary
