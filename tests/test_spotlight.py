"""Unit tests for spotlight selection (the single most dramatic routed win)."""

from __future__ import annotations

import pytest

from router.pipeline import load_default_pricing, run_bundled_replay
from router.spotlight import Spotlight, select_spotlight, spotlight_for


@pytest.fixture(scope="module")
def synth_traces() -> list[dict]:
    return list(run_bundled_replay(synth=True).traces)


@pytest.fixture(scope="module")
def pricing():
    return load_default_pricing()


def test_auto_picks_widest_accepted_ratio(synth_traces, pricing) -> None:
    spot = select_spotlight(synth_traces, pricing, "auto")
    assert isinstance(spot, Spotlight)
    assert spot.task_id == "t-0078"
    assert spot.accepted is True
    assert spot.chosen_model == "mini-fast"
    assert spot.naive_model == "deep-reasoner"
    assert spot.ratio == pytest.approx(24.09, abs=0.1)
    # nothing else beats it.
    best = max(
        (
            s
            for t in synth_traces
            if (s := spotlight_for(t, pricing, require_accepted=True)) is not None
        ),
        key=lambda s: s.ratio,
    )
    assert best.ratio == spot.ratio


@pytest.mark.parametrize("spec", ["none", "off", "false", "no", "  NONE  "])
def test_off_specs_return_none(synth_traces, pricing, spec) -> None:
    assert select_spotlight(synth_traces, pricing, spec) is None


def test_empty_spec_defaults_to_auto(synth_traces, pricing) -> None:
    # An unset/empty spotlight means "use the default auto pick", not "off".
    assert select_spotlight(synth_traces, pricing, "") == select_spotlight(
        synth_traces, pricing, "auto"
    )


def test_explicit_task_id_selects_that_task(synth_traces, pricing) -> None:
    spot = select_spotlight(synth_traces, pricing, "t-0003")
    assert spot is not None
    assert spot.task_id == "t-0003"


def test_unknown_task_id_raises(synth_traces, pricing) -> None:
    with pytest.raises(ValueError, match="t-9999"):
        select_spotlight(synth_traces, pricing, "t-9999")


def test_ratio_reconciles_with_costs(synth_traces, pricing) -> None:
    spot = select_spotlight(synth_traces, pricing, "auto")
    assert spot is not None
    assert spot.ratio == pytest.approx(spot.naive_usd / spot.routed_usd, abs=0.01)
    assert spot.to_dict()["task_id"] == spot.task_id


def test_spotlight_for_skips_trace_without_candidates(pricing) -> None:
    empty = {"task_id": "t-x", "class": "generate", "candidates": [], "cost_usd": 0.01}
    assert spotlight_for(empty, pricing, require_accepted=False) is None


def test_auto_requires_accepted(synth_traces, pricing) -> None:
    spot = select_spotlight(synth_traces, pricing, "auto")
    assert spot is not None and spot.accepted is True
