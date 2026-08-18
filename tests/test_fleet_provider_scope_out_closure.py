"""The fleet's ``provider: foundry`` models cannot carry a measured cost.

``samples/fleet/foundry-ext-full.fleet.yaml`` declares seven models on the
``azure-ai-inference`` surface, which
:data:`~router.foundry_live.AZURE_AI_INFERENCE_SCOPE_OUT_REASON` scopes out of
benchmark and publishable measurement. Two defences stand between them and a
sealed snapshot, and they cover different routes:

1. **Refusal at the plan-less dispatch paths.** A fleet slate becomes
   ``MeasureCandidate.provider`` in exactly two places — ``cli._measure_candidates``
   and ``RouterService._cockpit_candidates``. Neither can reach
   :func:`~router.measure.run_measure` any more: the commands that used to carry
   them there now refuse, and what is left of both is preview-only. That is pinned
   here by enumerating every caller.

2. **The scope-out gate at dispatch.** A fleet is not the only way a
   ``provider: foundry`` arm can appear — someone can write one into a run config
   by hand, and that plan *does* resolve and *does* reach the client. It is stopped
   at the socket instead, by :func:`~router.foundry_live.assert_provider_benchmark_safe`,
   which now sees the plan's real ``run_mode`` rather than a defaulted smoke.

Which defence catches which route matters: the first is a closed door, the second
is a guard that has to fire. Both are checked below against the seven models the
sample actually declares, so this file goes red rather than vacuous if the sample
changes.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
import yaml

from router.foundry_live import (
    AZURE_AI_INFERENCE_SCOPE_OUT_REASON,
    ProviderScopedOutError,
    assert_provider_benchmark_safe,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FLEET = ROOT / "samples" / "fleet" / "foundry-ext-full.fleet.yaml"

#: The two functions that turn a fleet slate into candidates carrying a provider.
#: Everything reachable from them inherits the fleet's provider labels.
FLEET_CANDIDATE_BUILDERS: tuple[str, ...] = (
    "_measure_candidates",
    "_cockpit_candidates",
)

#: Every function allowed to call one of the builders above, with what it does.
#: A measured consumer must never appear here — that is the property being pinned.
ALLOWED_CALLERS: dict[str, str] = {
    "router/cli.py::_cmd_measure_catalog": (
        "`measure catalog` — prints a cost preview table and returns. Constructs no "
        "client and calls no dispatcher; its own closing line says 'preview only'."
    ),
    "router/cli.py::_cmd_measure_run": (
        "`measure run`. Without --live it prints the dry-run estimate and exits 2; "
        "with --live it now refuses, so the candidates are used for the estimate and "
        "nothing else."
    ),
    "router/server.py::RouterService.cockpit_catalog": (
        "The cockpit's catalog panel — build_catalog only, the read-only counterpart "
        "of `measure catalog`."
    ),
}


def _foundry_models() -> list[str]:
    """The sample's scoped-out models, read from the file rather than restated."""

    data = yaml.safe_load(FLEET.read_text(encoding="utf-8"))
    models: list[str] = []
    for section in data.values():
        if not isinstance(section, list):
            continue
        for entry in section:
            if isinstance(entry, dict) and entry.get("provider") == "foundry":
                models.append(str(entry.get("name") or entry.get("deployment")))
    return models


def _scope_of(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    names: list[str] = []
    cur: ast.AST = node
    while cur in parents:
        cur = parents[cur]
        if isinstance(cur, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.append(cur.name)
    return ".".join(reversed(names))


def _callers_of(targets: tuple[str, ...]) -> dict[str, list[str]]:
    """Every scope in ``src/`` that calls one of ``targets``, keyed by target."""

    found: dict[str, list[str]] = {name: [] for name in targets}
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute)
                else None
            )
            if name not in found:
                continue
            rel = path.relative_to(SRC).as_posix()
            found[name].append(f"{rel}::{_scope_of(node, parents)}")
    return found


# --------------------------------------------------------------------------- #
# The sample still contains what this file is about
# --------------------------------------------------------------------------- #


def test_the_sample_fleet_still_declares_seven_scoped_out_models() -> None:
    """Guards against the quietest possible failure: this file testing nothing.

    If the sample is edited to drop ``provider: foundry`` the risk really is gone —
    but so is the evidence that the closures below hold, and a green file would
    then be reporting the wrong thing.
    """

    models = _foundry_models()
    assert len(models) == 7, f"expected 7 scoped-out models, found {models}"


# --------------------------------------------------------------------------- #
# Defence 1 — the fleet cannot reach a dispatcher
# --------------------------------------------------------------------------- #


def test_the_fleet_candidate_builders_are_only_called_by_preview_surfaces() -> None:
    """A fleet slate can no longer be carried into a paid sweep.

    Enumerated rather than reasoned about: every call site of both builders is
    listed, and a new one — or an old one growing a dispatch — fails here. This is
    the check that would have caught the original defect, where ``_measure_candidates``
    fed ``_cmd_measure_run``'s live block straight into ``run_measure``.
    """

    callers = _callers_of(FLEET_CANDIDATE_BUILDERS)

    for target, sites in sorted(callers.items()):
        # The definition itself is not a call; every builder must still be used, or
        # the pin is describing dead code.
        assert sites, f"{target} has no callers left — is it dead? Update this file."
        for site in sites:
            assert site in ALLOWED_CALLERS, (
                f"{target} is now called from {site}, which is not a registered "
                "preview surface. A fleet slate carries `provider: foundry` labels "
                "from samples/fleet/foundry-ext-full.fleet.yaml; if this caller can "
                "reach run_measure, those models can seal a measured snapshot. "
                "Either keep it preview-only and register it, or bind it to a "
                "resolved plan so the scope-out gate is evaluated against a real "
                "run_mode."
            )

    reached = {site for sites in callers.values() for site in sites}
    stale = sorted(set(ALLOWED_CALLERS) - reached)
    assert not stale, f"registered callers that no longer call a builder: {stale}"


def test_measure_catalog_is_a_preview_and_stays_one(capsys: Any) -> None:
    """The surviving fleet consumer, exercised end to end with the real sample.

    Runs the whole command against the seven scoped-out models: it must produce a
    table and say so, without a client, a credential or a snapshot.
    """

    from router import cli

    code = cli.main(["measure", "catalog", "ext-full", "--fleet", str(FLEET), "--n", "1"])
    out = capsys.readouterr().out

    assert code == 0
    assert "preview only — no live calls" in out
    for model in _foundry_models():
        assert model in out, f"{model} vanished from the catalog preview"


# --------------------------------------------------------------------------- #
# Defence 2 — the route a refusal cannot close
# --------------------------------------------------------------------------- #


def test_a_hand_written_benchmark_arm_is_stopped_at_the_gate() -> None:
    """The honest remainder: a plan *can* name these models, and is caught later.

    Closing the plan-less paths does not make ``provider: foundry`` unreachable —
    nothing stops someone writing one into a run config's arms, and that plan
    resolves normally. What stops it is the scope-out gate, and only because the
    plan-bound client now forwards the real run_mode; while ``benchmark_mode``
    defaulted to False this same call returned quietly.
    """

    for model in _foundry_models():
        with pytest.raises(ProviderScopedOutError) as excinfo:
            assert_provider_benchmark_safe("foundry", run_mode="benchmark")
        assert AZURE_AI_INFERENCE_SCOPE_OUT_REASON in str(excinfo.value), model

        # Publishable is gated independently of run_mode, so a smoke cannot be
        # promoted into a claim either.
        with pytest.raises(ProviderScopedOutError):
            assert_provider_benchmark_safe("foundry", publishable=True)


def test_the_gate_still_permits_the_wiring_smoke_it_exists_to_allow() -> None:
    """Closing the measured route must not close the opt-in connectivity check.

    Reaching the partner surface under smoke is the one thing it is still for; if
    this went red the fleet would be untestable rather than merely unpublishable.
    """

    assert_provider_benchmark_safe("foundry", run_mode="smoke")
    assert_provider_benchmark_safe("foundry", run_mode=None)
