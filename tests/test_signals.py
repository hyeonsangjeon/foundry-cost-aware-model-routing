"""Pin the signal-source seam (``router.signals``): the injectable provenance
boundary that decides where routing gets its per-model check outcomes.

The two offline built-ins stay deterministic, a bundle always carries the
``kind`` that rides to the ledger, and the honesty guard bars measured/live
signals from the strict offline audit — so a measured run can never quietly
score as an offline projection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from policy import load_default_policy
from router.offline import load_signal_fixture, load_workload
from router.pipeline import resolve_paths, run_bundled_replay
from router.signals import (
    OFFLINE_SIGNAL_KINDS,
    SignalBundle,
    SignalSource,
    assert_offline_ledger_kind,
    fixture_signal_source,
    resolve_signal_source,
    synth_signal_source,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)


@pytest.fixture
def curated():
    """The bundled curated workload + policy used by the offline frontier."""

    policy = load_default_policy()
    paths = resolve_paths(root=None)
    workload = load_workload(paths["workload"])
    return workload, policy, paths


# -- the two offline built-ins ----------------------------------------------


def test_synth_source_is_deterministic_and_tagged(curated) -> None:
    workload, policy, _ = curated
    source = synth_signal_source()
    first = source(workload, policy)
    second = source(workload, policy)
    assert first.kind == "synth"
    assert first.is_offline
    assert first.signals == second.signals  # no I/O, identical every run
    assert set(first.signals) == set(workload)


def test_fixture_source_replays_the_snapshot(curated) -> None:
    workload, policy, paths = curated
    bundle = fixture_signal_source(paths["signals"])(workload, policy)
    assert bundle.kind == "fixture"
    assert bundle.is_offline
    assert bundle.signals == load_signal_fixture(paths["signals"])


def test_resolve_signal_source_picks_the_offline_default(curated) -> None:
    workload, policy, paths = curated
    synth = resolve_signal_source(synth=True, signals_path=None)(workload, policy)
    fixture = resolve_signal_source(synth=False, signals_path=paths["signals"])(workload, policy)
    assert synth.kind == "synth"
    assert fixture.kind == "fixture"


def test_resolve_signal_source_requires_a_path_when_not_synth() -> None:
    with pytest.raises(ValueError, match="signals_path is required"):
        resolve_signal_source(synth=False, signals_path=None)


# -- the bundle + protocol --------------------------------------------------


def test_is_offline_reflects_the_kind() -> None:
    assert SignalBundle(signals={}, kind="synth").is_offline
    assert SignalBundle(signals={}, kind="fixture").is_offline
    assert not SignalBundle(signals={}, kind="measured").is_offline
    assert not SignalBundle(signals={}, kind="live").is_offline


def test_offline_kinds_are_exactly_synth_and_fixture() -> None:
    assert OFFLINE_SIGNAL_KINDS == frozenset({"synth", "fixture"})


def test_builtins_satisfy_the_runtime_checkable_protocol() -> None:
    assert isinstance(synth_signal_source(), SignalSource)
    assert isinstance(fixture_signal_source("x"), SignalSource)
    assert not isinstance(object(), SignalSource)  # not callable → not a source


# -- the honesty guard ------------------------------------------------------


def test_assert_offline_ledger_kind_allows_offline_kinds() -> None:
    assert_offline_ledger_kind("synth")
    assert_offline_ledger_kind("fixture")  # both return None without raising


@pytest.mark.parametrize("kind", ["measured", "live", "anything-else"])
def test_assert_offline_ledger_kind_bars_non_offline(kind: str) -> None:
    with pytest.raises(ValueError, match="offline ledger"):
        assert_offline_ledger_kind(kind)


# -- injection into a real flow ---------------------------------------------


def test_injected_source_overrides_the_default(curated) -> None:
    workload, policy, _ = curated
    first_id = sorted(workload)[0]

    def one_task_source(wl, pol) -> SignalBundle:
        full = synth_signal_source()(wl, pol)
        return SignalBundle(signals={first_id: full.signals[first_id]}, kind="synth")

    report = run_bundled_replay(signal_source=one_task_source)
    assert report.summary["tasks"] == 1  # the injected source restricted the run


def test_measured_source_is_barred_from_the_offline_ledger(
    curated, tmp_path: Path
) -> None:
    workload, policy, _ = curated

    def measured_source(wl, pol) -> SignalBundle:
        return SignalBundle(signals=synth_signal_source()(wl, pol).signals, kind="measured")

    with pytest.raises(ValueError, match="offline ledger"):
        run_bundled_replay(signal_source=measured_source, ledger_path=tmp_path / "l.jsonl")
    assert not (tmp_path / "l.jsonl").exists()  # nothing written before the guard


def test_measured_source_runs_when_no_ledger_is_requested(curated) -> None:
    workload, policy, _ = curated

    def measured_source(wl, pol) -> SignalBundle:
        return SignalBundle(signals=synth_signal_source()(wl, pol).signals, kind="measured")

    report = run_bundled_replay(signal_source=measured_source)
    assert report.summary["tasks"] >= 1  # the seam scores it as an offline projection
