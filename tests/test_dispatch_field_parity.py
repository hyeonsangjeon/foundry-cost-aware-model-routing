"""Every paid-dispatch consumer must hand the live client the same plan fields.

Sibling of ``test_run_plan_field_readers.py``, and deliberately not a
replacement — the two catch different halves of the same failure.

``test_run_plan_field_readers.py`` sweeps *fields*: it asks, for each key under
``execution``, whether **any** reader exists anywhere. It fires only when a field
has **zero** readers. That is a real class of defect (a field that reads like a
control in the approval view while changing nothing), but it is blind to the
defect that has now shipped three times:

  * ``retry.*`` transport cutoffs had readers, and reached only ``benchmark run
    --live`` — every other dispatch path used constructor defaults (fixed in
    eafc1a1).
  * ``preregistration.blob`` had readers, and was not verified on the path that
    spends.
  * ``run_mode`` had three readers in ``cli.py``, and never reached the client
    that consults it, so :func:`router.foundry_live.assert_provider_benchmark_safe`
    — a fail-closed gate — evaluated every dispatch as a smoke.

In all three the field was wired *somewhere*, so the field-level sweep stayed
green. A field-shaped test cannot see a partially-wired field. This module is
consumer-shaped instead: it asks, for each path that can make a paid call,
*which* plan fields it forwards, and holds every such path to the same set. A
path that forwards less than its siblings fails here, which is exactly the state
the three defects above were in.

The sweep is static (``ast``) rather than behavioural because every one of these
sites is operator-gated live egress — they cannot be executed in CI at all, so
the only way to hold them to a contract is to read the source. That also gives
the property in the last test: a *new* dispatch path is a test failure until
somebody classifies it here.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
CLIENT = "AzureModelRouterClient"

#: Consumers that can turn a dispatch into a *published cost claim* — they write
#: a sealed snapshot under ``results/measured/`` that ``measure publish`` can
#: promote. These are the ones the scope-out gate exists for, so each must state
#: a ``benchmark_mode`` rather than inherit the fail-open default.
MEASURED_CONSUMERS: dict[str, str] = {
    "router/cli.py::_live_measure_client": (
        "`benchmark run --live` — the 03A resolver path. Takes the ResolvedRunPlan "
        "as a parameter; the reference implementation for the other three."
    ),
    "router/cockpit.py::_live_client_factory": (
        "The cockpit's live sweep. CockpitController._run_sweep owns the plan and "
        "hands it to this factory, so the client is built from the approved plan."
    ),
    "router/cli.py::_cmd_measure_run": (
        "`measure run --live` — writes results/measured/<exp>/<run_id>, the exact "
        "artifact `measure publish` promotes."
    ),
    "router/server.py::RouterService._cockpit_launch._worker": (
        "The plan-less cockpit run route. Writes results/measured/<exp>/<run_id> "
        "and answers `measured: true`."
    ),
}

#: Measured consumers that resolve **no plan at all**, so there is no ``run_mode``
#: to forward and nothing for the parity check above to compare. Pinned here with
#: the reason, because the alternative — leaving them out of the registry — is how
#: they stayed invisible in the first place.
#:
#: This is a record, not a schedule. Wiring these two is a design decision, not a
#: mechanical change: neither path has a ``ResolvedRunPlan`` in scope, so closing
#: the gap means either declaring a fail-closed default for a plan-less measured
#: run, or binding both paths to the resolver (a `--config` for `measure run`, and
#: retiring the legacy cockpit route). Delete the entry when one is chosen; the
#: test below will then demand the full field set from it like any other sibling.
PLAN_LESS_MEASURED_CONSUMERS: dict[str, str] = {
    "router/cli.py::_cmd_measure_run": (
        "Legacy pre-03A path: candidates come from --fleet/--candidates and the "
        "request cap from --max-output-tokens, never from a resolved plan. "
        "`samples/fleet/foundry-ext-full.fleet.yaml` declares seven "
        "`provider: foundry` models, so this path can still dispatch a scoped-out "
        "provider into a measured snapshot."
    ),
    "router/server.py::RouterService._cockpit_launch._worker": (
        "Only reached when no plan is bound (`self._cockpit_controller is None`); "
        "the plan-bound route goes through CockpitController instead. The "
        "surrounding `dashboard --live` without --config already prints a "
        "DEPRECATED warning."
    ),
}

#: Consumers that are wiring/demo/fixture surfaces. They never write a measured
#: snapshot, so a smoke evaluation is the correct one and the partner surface is
#: deliberately reachable from them — that opt-in check is what ``run_mode:
#: smoke`` is *for*. Registered so that "smoke" is a stated classification rather
#: than an accident of the default.
SMOKE_CONSUMERS: dict[str, str] = {
    "router/cli.py::_cmd_foundry_live": (
        "`foundry live --live` — single-call wiring demo, prints a table."
    ),
    "router/cli.py::_capture_recorded_snapshot": (
        "`foundry live --capture --live` — records a usage fixture for offline replay."
    ),
    "router/cli.py::_cmd_foundry_router": (
        "`foundry router --live` — router-choice demo, prints the backend mix."
    ),
    "router/cli.py::_capture_recorded_choices_snapshot": (
        "`foundry router --capture --live` — records a router-choice fixture."
    ),
    "router/foundry_arena.py::FoundryFleet.from_config": (
        "The arena fleet. `foundry arena --live` passes a slate's providers here, so "
        "this is the path that reaches the partner surface on purpose — under smoke."
    ),
}


class _Site:
    __slots__ = ("key", "path", "lineno", "kwargs")

    def __init__(self, key: str, path: Path, lineno: int, kwargs: dict[str, str]) -> None:
        self.key = key
        self.path = path
        self.lineno = lineno
        self.kwargs = kwargs

    def __repr__(self) -> str:  # pragma: no cover - failure messages only
        rel = self.path.relative_to(ROOT)
        return f"{rel}:{self.lineno} ({self.key})"


def _dotted_scope(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    names: list[str] = []
    cur: ast.AST = node
    while cur in parents:
        cur = parents[cur]
        if isinstance(cur, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.append(cur.name)
    return ".".join(reversed(names))


def _client_sites() -> list[_Site]:
    """Every ``AzureModelRouterClient(...)`` construction in the shipped package.

    Scoped to ``src/`` on purpose: that is what ``pyproject``'s ``where = ["src"]``
    packages. A stale ``build/lib/`` mirror is not shipped and is gitignored.
    """

    sites: list[_Site] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Name) and func.id == CLIENT):
                continue
            kwargs = {
                kw.arg: ast.unparse(kw.value) for kw in node.keywords if kw.arg is not None
            }
            rel = path.relative_to(SRC).as_posix()
            key = f"{rel}::{_dotted_scope(node, parents)}"
            sites.append(_Site(key, path, node.lineno, kwargs))
    return sites


def _by_key() -> dict[str, _Site]:
    sites = _client_sites()
    keys = [s.key for s in sites]
    assert len(keys) == len(set(keys)), f"ambiguous site keys: {sorted(keys)}"
    return {s.key: s for s in sites}


def _plan_bound_measured() -> dict[str, _Site]:
    sites = _by_key()
    return {
        key: sites[key]
        for key in MEASURED_CONSUMERS
        if key not in PLAN_LESS_MEASURED_CONSUMERS
    }


# --------------------------------------------------------------------------- #
# The registry must cover reality
# --------------------------------------------------------------------------- #


def test_every_client_construction_site_is_classified() -> None:
    """A new paid-dispatch path fails until somebody says what it is.

    This is the property the field-level sweep cannot provide: it enumerates plan
    fields, so a brand-new consumer that forwards none of them looks like nothing
    at all. Here a new consumer is a new row, and a new row is a failure.
    """

    found = {s.key for s in _client_sites()}
    classified = set(MEASURED_CONSUMERS) | set(SMOKE_CONSUMERS)

    unclassified = sorted(found - classified)
    assert not unclassified, (
        "new AzureModelRouterClient construction site(s) with no classification: "
        f"{unclassified}. Add each to MEASURED_CONSUMERS (it can produce a published "
        "cost claim) or SMOKE_CONSUMERS (it cannot), with the reason."
    )

    stale = sorted(classified - found)
    assert not stale, (
        f"classified sites that no longer exist: {stale}. Delete the entries — a "
        "stale entry is a false claim about the code."
    )


def test_the_plan_less_gap_list_stays_a_subset_of_the_measured_ones() -> None:
    """Every pinned gap must still be a real, still-measured consumer."""

    orphans = sorted(set(PLAN_LESS_MEASURED_CONSUMERS) - set(MEASURED_CONSUMERS))
    assert not orphans, f"gap entries that are not measured consumers: {orphans}"


# --------------------------------------------------------------------------- #
# Parity — no consumer may forward less than its siblings
# --------------------------------------------------------------------------- #


def test_plan_bound_consumers_all_forward_the_same_fields() -> None:
    """The parity rule: one path forwarding a field obliges the others to.

    The reference set is the *union* of what the plan-bound consumers forward
    rather than a hard-coded list, so this tightens by itself: wire a new plan
    field into one dispatch path and every sibling goes red until it matches. A
    hard-coded list would have to be remembered, and the whole reason this file
    exists is that it was not.
    """

    sites = _plan_bound_measured()
    assert len(sites) >= 2, "parity needs at least two plan-bound consumers to compare"

    reference: set[str] = set()
    for site in sites.values():
        reference |= set(site.kwargs)

    for _key, site in sorted(sites.items()):
        missing = sorted(reference - set(site.kwargs))
        assert not missing, (
            f"{site} forwards less than its siblings: missing {missing}. Every "
            "plan-bound dispatch path must hand the client the same plan fields; a "
            "field that reaches one path and not another is how run_mode, the "
            "transport timeouts, and preregistration.blob each shipped fail-open."
        )


def test_the_fields_that_matter_are_actually_in_the_reference_set() -> None:
    """Parity alone is satisfiable by every consumer forwarding nothing.

    So the floor is pinned separately: these four are the constructor arguments
    whose defaults are silently wrong for a measured run — 512 output tokens, the
    committed rather than the pinned cutoffs, and a ``benchmark_mode`` of False
    that turns the scope-out gate into a no-op.
    """

    sites = _plan_bound_measured()
    reference: set[str] = set()
    for site in sites.values():
        reference |= set(site.kwargs)

    for field in ("config", "max_output_tokens", "timeouts", "benchmark_mode"):
        assert field in reference, (
            f"no plan-bound dispatch path forwards {field!r} any more — the parity "
            "test above would still pass with every path equally unwired."
        )


# --------------------------------------------------------------------------- #
# The values, not just the keyword names
# --------------------------------------------------------------------------- #


def test_plan_bound_consumers_derive_benchmark_mode_from_the_plan() -> None:
    """``benchmark_mode`` must come from the shared predicate, not a re-spelling.

    A path that writes ``run_mode == "benchmark"`` inline satisfies every check
    above while being free to disagree with the gate about what "benchmark" means
    — normalisation, whitespace, ``None``. One predicate, one spelling, and this
    test is what keeps it that way.
    """

    for _key, site in sorted(_plan_bound_measured().items()):
        expr = site.kwargs.get("benchmark_mode", "")
        assert "is_benchmark_run_mode(" in expr, (
            f"{site} sets benchmark_mode from {expr!r}. Use "
            "router.foundry_live.is_benchmark_run_mode so the wiring and the gate "
            "cannot drift apart."
        )
        assert "run_mode" in expr, (
            f"{site} does not feed the plan's run_mode into the predicate: {expr!r}"
        )


def test_plan_bound_consumers_derive_transport_cutoffs_from_the_plan() -> None:
    for _key, site in sorted(_plan_bound_measured().items()):
        expr = site.kwargs.get("timeouts", "")
        assert "TransportTimeouts.from_retry(" in expr, (
            f"{site} sets timeouts from {expr!r}; build them from the plan's retry "
            "block so a plan that pinned its own cutoffs actually gets them."
        )


def test_plan_bound_consumers_take_the_request_cap_from_the_plan() -> None:
    for _key, site in sorted(_plan_bound_measured().items()):
        expr = site.kwargs.get("max_output_tokens", "")
        assert "max_output_tokens" in expr and ("execution" in expr or "plan" in expr), (
            f"{site} sets max_output_tokens from {expr!r}, which is not the plan's "
            "request cap. The constructor default is 512; a plan asking for more "
            "would have every completion truncated and still scored."
        )


def test_smoke_consumers_do_not_claim_to_be_benchmarks() -> None:
    """A wiring surface must never assert the measured posture.

    The scope-out gate blocks the partner SDK under benchmark and permits it under
    smoke, on purpose: the opt-in wiring check is the one thing that surface is
    for. A demo path that declared ``benchmark_mode=True`` would break that check
    rather than protect anything.
    """

    sites = _by_key()
    for key in sorted(SMOKE_CONSUMERS):
        site = sites[key]
        expr = site.kwargs.get("benchmark_mode")
        assert expr in (None, "False"), (
            f"{site} is registered as a smoke surface but sets benchmark_mode="
            f"{expr!r}. Reclassify it into MEASURED_CONSUMERS or drop the argument."
        )
