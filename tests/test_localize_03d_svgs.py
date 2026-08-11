"""Unit tests for :mod:`scripts.localize_03d_svgs`.

The three 03D charts are committed once with Korean labels (the ko pages embed
them). #91 adds English ``.en.svg`` siblings so the English pages stop pointing
at Korean assets. These tests lock two invariants: the label map covers every
Korean string in the committed charts (no half-translated English asset can be
emitted), and the committed ``.en.svg`` files are exactly what the script
produces from the ko source (regeneratable, no manual drift).
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = REPO_ROOT / "scripts" / "localize_03d_svgs.py"
_ASSET_DIR = REPO_ROOT / "docs" / "assets" / "03d"

_spec = importlib.util.spec_from_file_location("localize_03d_svgs", _MODULE_PATH)
assert _spec and _spec.loader
loc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = loc
_spec.loader.exec_module(loc)

HANGUL = re.compile(r"[\uac00-\ud7a3]")


@pytest.mark.parametrize("name", loc.CHARTS)
def test_localize_leaves_no_hangul(name: str) -> None:
    src = _ASSET_DIR / f"{name}.svg"
    english = loc.localize(src.read_text(encoding="utf-8"))
    assert not HANGUL.search(english), f"{name}.svg still has Korean after localize"


@pytest.mark.parametrize("name", loc.CHARTS)
def test_committed_en_svg_matches_generator(name: str) -> None:
    # The committed English asset must equal a fresh localize() of the ko source
    # so it can always be regenerated and never drifts by hand.
    src = _ASSET_DIR / f"{name}.svg"
    en = _ASSET_DIR / f"{name}.en.svg"
    assert en.is_file(), f"missing generated {name}.en.svg"
    assert en.read_text(encoding="utf-8") == loc.localize(src.read_text(encoding="utf-8"))


def test_source_ko_svgs_unchanged_have_hangul() -> None:
    # Guard the premise: the ko sources are still Korean (we never touch them).
    for name in loc.CHARTS:
        src = _ASSET_DIR / f"{name}.svg"
        assert HANGUL.search(src.read_text(encoding="utf-8")), f"{name}.svg lost its Korean"


def test_unmapped_korean_raises() -> None:
    with pytest.raises(SystemExit):
        loc.localize('<text>알 수 없는 라벨</text>')


def test_every_label_key_is_used() -> None:
    # A key absent from all charts is dead weight that can rot out of sync.
    corpus = "".join(
        (_ASSET_DIR / f"{name}.svg").read_text(encoding="utf-8") for name in loc.CHARTS
    )
    unused = [ko for ko in loc.LABELS if ko not in corpus]
    assert not unused, f"LABELS keys not found in any chart: {unused}"
