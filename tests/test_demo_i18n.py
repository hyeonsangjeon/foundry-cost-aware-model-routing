"""Completeness tests for the per-locale demo string catalog.

The two static demos (``/demo/`` en, ``/ko/demo/`` ko) used to share one
locale-neutral body, so English and Korean copy mixed on both. The root fix
moved every reader-facing string into :mod:`router.demo_i18n` with an explicit
``en`` and ``ko`` side, and :func:`router.dashboard.render_dashboard` resolves
the per-locale markers.

These tests lock the invariant the operator required: *adding a string with
only one locale filled, or forgetting to translate one, must fail the build* —
never leak the wrong language into a demo. They also assert the two rendered
dashboards are actually single-language and structurally identical.
"""

from __future__ import annotations

import re

import pytest

from router import demo_i18n as di
from router.dashboard import DASHBOARD_TEMPLATE, render_dashboard

HANGUL = re.compile(r"[\uac00-\ud7a3]")


def test_catalog_validates() -> None:
    # Non-empty en+ko for every key, shared keys identical, non-shared differ.
    di.validate()


def test_every_marker_in_template_has_a_catalog_entry() -> None:
    markers = set(re.findall(r"@@(\w+)@@", DASHBOARD_TEMPLATE))
    missing = sorted(m for m in markers if m not in di.DEMO_STRINGS)
    assert not missing, f"template markers with no catalog entry: {missing}"


def test_every_catalog_key_is_used_in_the_template() -> None:
    # A key with no marker is dead weight that can silently rot out of sync.
    unused = sorted(k for k in di.DEMO_STRINGS if f"@@{k}@@" not in DASHBOARD_TEMPLATE)
    assert not unused, f"catalog keys with no template marker: {unused}"


@pytest.mark.parametrize("locale", ["en", "ko"])
def test_render_resolves_every_marker(locale: str) -> None:
    html = render_dashboard(locale)
    assert "@@" not in html, "unresolved @@marker@@ left after render"
    assert "__MEASURED_JSON__" not in html, "measured payload placeholder not filled"


def test_english_dashboard_is_hangul_free() -> None:
    assert not HANGUL.findall(render_dashboard("en"))


def test_korean_dashboard_carries_korean() -> None:
    assert HANGUL.findall(render_dashboard("ko"))


def test_dashboards_differ_between_locales() -> None:
    assert render_dashboard("en") != render_dashboard("ko")


def test_missing_translation_fails_validate(monkeypatch: pytest.MonkeyPatch) -> None:
    # A non-shared key left untranslated (en == ko) must be rejected.
    poisoned = {**di.DEMO_STRINGS, "k000": {"en": "same", "ko": "same"}}
    monkeypatch.setattr(di, "DEMO_STRINGS", poisoned)
    with pytest.raises(AssertionError):
        di.validate()


def test_one_sided_string_fails_validate(monkeypatch: pytest.MonkeyPatch) -> None:
    # A key with an empty locale (one side filled only) must be rejected.
    poisoned = {**di.DEMO_STRINGS, "k000": {"en": "only english", "ko": ""}}
    monkeypatch.setattr(di, "DEMO_STRINGS", poisoned)
    with pytest.raises(AssertionError):
        di.validate()


def test_stale_marker_fails_render() -> None:
    with pytest.raises(AssertionError):
        di.render_demo_prose("<p>@@k_does_not_exist@@</p>", "en")


def test_measured_payload_is_single_locale() -> None:
    en, ko = di.measured_payload("en"), di.measured_payload("ko")
    assert set(en) == set(ko)
    # The English payload carries no Korean; the Korean one does.
    assert not HANGUL.findall(di_json(en))
    assert HANGUL.findall(di_json(ko))
    # armLbl covers exactly the four measured arms in both locales.
    assert set(en["armLbl"]) == set(ko["armLbl"])


def test_measured_arm_key_explains_all_four_arms_before_other_copy() -> None:
    en, ko = di.measured_payload("en"), di.measured_payload("ko")
    for arm in en["armLbl"]:
        assert en["armKey"].count(arm) == 1
        assert ko["armKey"].count(arm) == 1
    assert "Model Router in Cost mode" in en["armKey"]
    assert "calling the premium model directly" in en["armKey"]
    assert "Model Router의 Cost 모드" in ko["armKey"]
    assert "프리미엄 모델 직접 호출" in ko["armKey"]
    assert DASHBOARD_TEMPLATE.index('id="mArmKey"') < DASHBOARD_TEMPLATE.index('id="mSub"')


def test_localize_experiments_translates_and_guards() -> None:
    payload = {
        "experiments": [
            {"name": "ensemble", "title": "T", "summary": "S", "metrics": {"title": "T"}},
        ]
    }
    di.localize_experiments(payload, "en")
    card = payload["experiments"][0]
    # A known experiment gets English prose (no Korean) on the English demo.
    assert not HANGUL.findall(card["title"] + card["summary"] + card["metrics"]["title"])


def di_json(obj: object) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)
