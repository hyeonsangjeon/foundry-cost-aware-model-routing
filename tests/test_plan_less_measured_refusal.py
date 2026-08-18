"""A measured dispatch with no approved plan behind it is refused.

What makes a dispatch *measured* here is not the ``--live`` flag and not whether a
fleet was used: it is whether the dispatch seals a snapshot under
``results/measured/``, because that snapshot is the artifact ``measure publish``
promotes into a cost claim. In this package the criterion is exact — sealing one
means calling :func:`router.measure.run_measure`.

Four call sites do. Two carry a :class:`~router.run_plan.ResolvedRunPlan`
(``benchmark run --live`` and the plan-bound cockpit) and are wired to forward it.
The other two never resolved a plan at all, so the retry budget, the transport
cutoffs, the request cap and the ``run_mode`` that the provider scope-out gate is
evaluated against all came from constructor defaults. ``benchmark_mode`` defaulting
to ``False`` is the one that mattered: it made
:func:`router.foundry_live.assert_provider_benchmark_safe` evaluate every dispatch
as a smoke, so the retiring ``azure-ai-inference`` surface could carry a measured
cost. Those two are refused rather than wired, because wiring them means resolving
a plan they have no way to obtain.

The other half of the contract is that this cost nothing that was not a paid
measured run. The five wiring/demo surfaces call ``run_measure`` from nowhere and
are untouched; ``measure run`` without ``--live`` still prints its estimate table
and exits 2; and every injected/fake client in the suite still runs, which is what
the last section here pins. A refusal that also broke the wiring checks would have
removed the one thing that tells an operator their credentials work.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from router import cli
from router.measure import (
    AttemptResult,
    AzureMeasureClient,
    MeasureCandidate,
    MeasuredDispatchWithoutPlanError,
    load_prompt_workload,
    plan_less_measured_refusal,
    run_measure,
    unsupported_measured_route_refusal,
)
from router.pricing import PricingTable
from router.server import RouterService

ROOT = Path(__file__).resolve().parents[1]
PRICING = ROOT / "samples" / "pricing" / "foundry-5series.yaml"
WORKLOAD = ROOT / "samples" / "telemetry" / "curated-arena-live.sample.jsonl"


def _sweep_args(run_dir: Path) -> dict[str, Any]:
    """The smallest real sweep this file can drive, minus the client."""

    return {
        "client": None,
        "pricing": PricingTable.from_yaml(PRICING),
        "exp_id": "curated",
        "run_dir": run_dir,
        "run_id": "RUN",
        "n": 1,
    }


# --------------------------------------------------------------------------- #
# `measure run --live` — state 1: a measured run with no plan behind it
# --------------------------------------------------------------------------- #


def test_measure_run_live_refuses_and_spends_nothing(capsys: Any) -> None:
    """The headline: the command that could seal a plan-less snapshot no longer can."""

    code = cli.main(
        [
            "measure", "run", "curated",
            "--candidates", "gpt-5.4-nano",
            "--budget-usd", "5",
            "--live", "--yes",
        ]
    )
    out = capsys.readouterr().out

    assert code == 1
    assert "refusing to dispatch" in out
    assert "needs a resolved plan" in out


def test_the_refusal_names_the_path_that_does_support_a_measured_run(capsys: Any) -> None:
    """A refusal that does not say what to run instead reads as 'give up'.

    This matters more than usual here: the operator reaching this message is
    following a documented procedure, so the message has to be the thing that
    redirects them.
    """

    cli.main(["measure", "run", "curated", "--candidates", "gpt-5.4-nano", "--live"])
    out = capsys.readouterr().out

    assert "benchmark run --live" in out
    assert "--config" in out


def test_the_refusal_does_not_blame_credentials_or_budget(capsys: Any) -> None:
    """Cause-distinguishing, in the shape PR #110 established.

    A run refused for spend and a run refused for having no plan are different
    states with different remedies. Naming the wrong one sends the operator to
    `az login` for a problem that has nothing to do with their identity — and this
    path refuses even when fully credentialed and under budget.
    """

    cli.main(
        [
            "measure", "run", "curated",
            "--candidates", "gpt-5.4-nano",
            "--budget-usd", "5",
            "--live", "--yes",
        ]
    )
    out = capsys.readouterr().out

    assert "not a credential, budget or preregistration failure" in out
    # Not "you are not logged in" — the remedy is a plan, not an identity.
    assert "az login" not in out


def test_the_refusal_is_reached_without_credentials_of_any_kind(
    capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-closed means the refusal does not depend on reaching Azure first.

    The old order asked for credentials before it asked whether the run was
    legitimate, so an uncredentialed clone got a *different* error and the real
    problem stayed hidden until someone finally had a key.
    """

    for var in ("AZURE_AI_FOUNDRY_ENDPOINT", "AZURE_AI_FOUNDRY_DEPLOYMENT",
                "AZURE_AI_FOUNDRY_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    code = cli.main(
        ["measure", "run", "curated", "--candidates", "gpt-5.4-nano", "--live", "--yes"]
    )
    assert code == 1
    assert "refusing to dispatch" in capsys.readouterr().out


def test_a_fleet_of_scoped_out_models_cannot_reach_a_measured_snapshot(
    capsys: Any, tmp_path: Path
) -> None:
    """The concrete exposure this closes.

    ``samples/fleet/foundry-ext-full.fleet.yaml`` declares seven ``provider:
    foundry`` models. Through this command they became MeasureCandidates carrying
    ``provider="foundry"``, dispatched against a client whose ``benchmark_mode`` was
    False, so ``assert_provider_benchmark_safe`` saw a smoke and let them seal a
    snapshot that ``measure publish`` could promote.
    """

    fleet = ROOT / "samples" / "fleet" / "foundry-ext-full.fleet.yaml"
    assert "provider: foundry" in fleet.read_text(encoding="utf-8")

    code = cli.main(
        [
            "measure", "run", "ext-full",
            "--fleet", str(fleet),
            "--out-root", str(tmp_path),
            "--budget-usd", "5",
            "--live", "--yes",
        ]
    )
    out = capsys.readouterr().out

    assert code == 1
    assert "refusing to dispatch" in out
    # Nothing was sealed: no snapshot directory exists to promote.
    assert not list(tmp_path.rglob("manifest.json"))


# --------------------------------------------------------------------------- #
# The cockpit legacy route — state 2: a route that does not support measured runs
# --------------------------------------------------------------------------- #


def test_the_plan_less_cockpit_route_refuses_as_unsupported() -> None:
    """Distinct from state 1: this route was superseded, not left unwired."""

    service = RouterService(cockpit_token="t")
    response = service._cockpit_launch(
        {}, experiment="cockpit", budget=1.0, config=object()
    )

    assert response.status == 200
    assert response.payload["ran"] is False
    assert response.payload["measured"] is False
    assert "does not support measured runs" in response.payload["reason"]


def test_the_two_refusals_do_not_borrow_each_others_diagnosis() -> None:
    """The whole point of two messages is that each rules the other out.

    "No plan was resolved" and "this route will never take a plan" lead to
    different actions — supply a config, versus stop using this route. A shared
    message would send half the readers to the wrong remedy.
    """

    without_plan = plan_less_measured_refusal("x", writes="results/measured/e/r")
    unsupported = unsupported_measured_route_refusal("y", successor="the bound cockpit")

    assert "needs a resolved plan" in without_plan
    assert "needs a resolved plan" not in unsupported

    assert "does not support measured runs" in unsupported
    assert "does not support measured runs" not in without_plan

    # State 2 says supplying the missing thing will not help, so it must not
    # inherit state 1's "bring a plan" remedy.
    assert "benchmark run --live" in without_plan
    assert "benchmark run --live" not in unsupported


def test_the_read_only_cockpit_panels_survive_the_refusal() -> None:
    """Closing the paid leaf must not take the observation surface with it."""

    service = RouterService(cockpit_token="t")
    assert service.cockpit_status().status == 200
    assert service.cockpit_progress("/cockpit/progress?run=none").status == 200


# --------------------------------------------------------------------------- #
# The backstop: a *future* plan-less path fails closed rather than being reviewed
# --------------------------------------------------------------------------- #


def test_run_measure_refuses_a_live_client_with_no_plan_hash(tmp_path: Path) -> None:
    """The two call sites were fixed; this is what stops a third from appearing.

    A static registry catches a new dispatch path only if someone reads the failure
    and thinks about it. This raises regardless, at the writer, before the run
    directory exists.
    """

    client = AzureMeasureClient(client=object())
    with pytest.raises(MeasuredDispatchWithoutPlanError) as excinfo:
        run_measure(
            load_prompt_workload(WORKLOAD),
            [MeasureCandidate("gpt-5.4-nano", "gpt-5.4-nano")],
            **{**_sweep_args(tmp_path / "run"), "client": client},
        )

    assert "refusing to dispatch" in str(excinfo.value)
    # Fail-closed *before* any artifact exists, so there is nothing half-sealed.
    assert not (tmp_path / "run").exists()


def test_the_backstop_leaves_every_injected_client_alone(tmp_path: Path) -> None:
    """The seam the whole suite runs on must not be caught by the guard.

    ``run_measure`` is driven by fake clients across this suite, none of which pass
    a plan_hash. Keying the backstop on the live adapter rather than on "plan_hash
    is None" is what keeps this a guard on paid egress instead of a guard on
    testing.
    """

    class _Fake:
        def attempt(self, *, deployment: str, provider: str, task: Any) -> AttemptResult:
            return AttemptResult(
                http_status=200,
                model=deployment,
                usage={"input": 1000, "cached": 0, "output": 500, "reasoning": 0},
                latency_ms=12.3,
                provenance="fake",
            )

    result = run_measure(
        load_prompt_workload(WORKLOAD),
        [MeasureCandidate("gpt-5.4-nano", "gpt-5.4-nano")],
        **{**_sweep_args(tmp_path / "run"), "client": _Fake()},
    )

    manifest = json.loads((tmp_path / "run" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["plan_hash"] is None
    assert result.summary["calls"] > 0


# --------------------------------------------------------------------------- #
# The boundary: everything that is not a paid measured run still works
# --------------------------------------------------------------------------- #


def test_measure_run_without_live_is_completely_unchanged(capsys: Any) -> None:
    """The estimate surface is how an operator sizes a spend before approving it.

    Pinned verbatim — exit 2 and both strings — because this is the half of the
    command that must survive the refusal, and the documented contract says so.
    """

    code = cli.main(
        ["measure", "run", "curated", "--candidates", "gpt-5.4-nano,gpt-5.4",
         "--n", "3", "--budget-usd", "5"]
    )
    out = capsys.readouterr().out

    assert code == 2
    assert "dry-run cost estimate" in out
    assert "no live calls were made" in out
    # The refusal belongs to --live only; it must not leak into the estimate.
    assert "refusing to dispatch" not in out


def test_the_wiring_smoke_surfaces_construct_no_measured_snapshot() -> None:
    """The smoke/demo paths are outside the criterion, and stay outside it.

    ``foundry live``/``foundry router`` (and their --capture variants) and the arena
    fleet reach the partner surface on purpose, under smoke, which is exactly what
    the scope-out gate permits. None of them calls ``run_measure``, so none of them
    is touched by anything in this module — pinned here so a later refactor cannot
    quietly route a demo through the sealed-snapshot writer.
    """

    import ast

    src = ROOT / "src" / "router"
    callers: set[str] = set()
    for path in sorted(src.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "run_measure":
                continue
            cur: Any = node
            names: list[str] = []
            while cur in parents:
                cur = parents[cur]
                if isinstance(cur, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                    names.append(cur.name)
            callers.add(f"router/{path.name}::{'.'.join(reversed(names))}")

    assert callers == {
        "router/cockpit.py::CockpitController._run_sweep",
        "router/run_plan.py::execute_benchmark",
    }, (
        f"the set of sealed-snapshot writers changed: {sorted(callers)}. Every caller "
        "of run_measure is by definition a measured consumer and must carry a "
        "resolved plan; a demo/smoke surface must never appear in this set."
    )
