"""The signal-source seam — where routing gets its per-model check outcomes.

Every offline flow scores routing decisions against a map of
``task_id -> model -> {applies, compiles, tests_pass, lint_pass}``. Those
signals can come from different provenances, and this module makes the choice a
single, explicit, **injectable object** instead of a scatter of ``synth`` /
``signals_path`` booleans threaded through every entry point:

* **synth**   — deterministically derived from the workload + policy (no I/O).
* **fixture** — a checked-in JSON snapshot (deterministic replay).
* **measured** / **live** — real per-model outcomes from actually running the
  candidates. This repo ships no such provider (running code and tests is out
  of scope for an offline demo), but the seam is here so one can be injected
  into any flow *without touching the flow* — and its provenance rides along in
  :attr:`SignalBundle.kind` all the way to the audit ledger, so measured rows
  can never quietly masquerade as offline ones.

A :class:`SignalSource` is simply a callable ``(workload, policy) ->
SignalBundle``. The two offline built-ins below satisfy it; a measured provider
only has to match the same shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from policy import PolicyTable

from .offline import load_signal_fixture, synthesize_signals
from .select import SignalMap

#: Provenances the strict offline ledger will accept. Anything outside this set
#: (``measured`` / ``live``) is barred from the offline audit on purpose — see
#: :func:`assert_offline_ledger_kind`.
OFFLINE_SIGNAL_KINDS = frozenset({"synth", "fixture"})


@dataclass(frozen=True, slots=True)
class SignalBundle:
    """Per-task check signals plus the provenance that produced them.

    Bundling the data with its ``kind`` keeps the two from drifting apart: the
    label that decides whether a run may enter the offline ledger always
    travels with the signals it describes.
    """

    signals: dict[str, SignalMap]
    kind: str

    @property
    def is_offline(self) -> bool:
        """True when these signals are eligible for the strict offline ledger."""

        return self.kind in OFFLINE_SIGNAL_KINDS


@runtime_checkable
class SignalSource(Protocol):
    """Produces a :class:`SignalBundle` for a workload under a policy.

    Any callable of this shape is a source. The built-in factories below cover
    the two offline provenances; a measured/live provider just has to match the
    same call signature to drop into every flow.
    """

    def __call__(
        self, workload: Mapping[str, Mapping[str, Any]], policy: PolicyTable
    ) -> SignalBundle: ...


def synth_signal_source() -> SignalSource:
    """A source that derives deterministic synth signals from workload + policy."""

    def _source(
        workload: Mapping[str, Mapping[str, Any]], policy: PolicyTable
    ) -> SignalBundle:
        return SignalBundle(signals=synthesize_signals(workload, policy), kind="synth")

    return _source


def fixture_signal_source(path: Path | str) -> SignalSource:
    """A source that replays a checked-in signal fixture (deterministic)."""

    def _source(
        workload: Mapping[str, Mapping[str, Any]], policy: PolicyTable
    ) -> SignalBundle:
        return SignalBundle(signals=dict(load_signal_fixture(path)), kind="fixture")

    return _source


def resolve_signal_source(
    *, synth: bool, signals_path: Path | str | None
) -> SignalSource:
    """Pick the default offline source from the classic synth/path switch.

    This is the single place that maps the historical ``synth`` /
    ``signals_path`` inputs onto a concrete source, so callers can keep passing
    those flags while any of them may instead inject a bespoke
    :class:`SignalSource`.
    """

    if synth:
        return synth_signal_source()
    if signals_path is None:
        raise ValueError("signals_path is required when synth is False")
    return fixture_signal_source(signals_path)


def assert_offline_ledger_kind(kind: str) -> None:
    """Guard the honesty boundary of the strict, hash-chained offline ledger.

    The offline ledger is an audit of *offline projections* only. Measured or
    live signals carry real spend and must not be written into it; they belong
    in the measured audit path instead. Raising here — before a record is ever
    built — gives a boundary-specific message rather than a deep schema error.
    """

    if kind not in OFFLINE_SIGNAL_KINDS:
        allowed = ", ".join(sorted(OFFLINE_SIGNAL_KINDS))
        raise ValueError(
            f"signal kind {kind!r} cannot enter the offline ledger "
            f"(offline kinds: {allowed}); measured/live runs use the measured "
            "audit path so offline projections stay pristine"
        )
