"""Every place that re-normalizes ``run_mode`` is pinned, and a fifth fails.

``run_mode`` is decided once. :func:`router.run_plan.resolve_run_plan` takes the
raw YAML value or the ``--run-mode`` override, lower-cases it, defaults it to
``smoke``, validates it against :data:`~router.run_plan.RUN_MODES` and writes the
result into ``plan.execution["run_mode"]`` — which is hashed into the plan hash and
read back by the ``plan.run_mode`` accessor. That is the normalizer of record.

Downstream, whether a run is a benchmark is asked through one predicate:
:func:`router.foundry_live.is_benchmark_run_mode`. It exists because a bare
``== "benchmark"`` in each caller is how ``run_mode`` came to have three readers in
``cli.py`` that never reached the client consulting it, leaving a fail-closed gate
evaluating every dispatch as a smoke.

Between those two there are four sites that spell the normalization out again
instead of calling the predicate. None of them is wrong today — the point of this
module is that they *agree*, proven below against an adversarial input table rather
than asserted — so this is a pin, not a repair. Nothing here changes behaviour.
What it buys is the fifth: a new hand-rolled ``str(run_mode or "").strip().lower()``
fails this file until somebody either routes it through the predicate or writes
down why it cannot.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from router.foundry_live import is_benchmark_run_mode
from router.run_plan import RUN_MODES

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

#: The four sites that re-derive the canonical form instead of calling the shared
#: predicate, each with the one-line reason it does so. A reason is required
#: because "it was easier to inline" and "this function is genuinely upstream of
#: the plan" are different situations, and only the second is permanent.
RE_DECIDERS: dict[str, str] = {
    "router/accounting.py::build_attempt_accounting": (
        "Takes ``run_mode`` as a plain string with no caller inside ``src/`` at all — "
        "it is driven from persisted attempt evidence — so nothing upstream of it "
        "could have canonicalised the value; it normalizes ``provider`` on the "
        "preceding line for the same reason."
    ),
    "router/preregistration.py::resolve_preregistration": (
        "Runs while the plan is still being *produced* — it is one of the steps whose "
        "output feeds the final plan hash — so there is no ResolvedRunPlan to read a "
        "canonical run_mode from yet; it sees raw YAML or a --run-mode override."
    ),
    "router/preregistration.py::prereg_dispatch_gate": (
        "A shared gate whose whole premise is that entry points cannot disagree "
        "about what counts as preregistered; its one shipped caller (``cli.py``'s "
        "``_resolve_prereg_gate``) hands it ``str(plan.execution.get('run_mode') or "
        "'')``, a stringify rather than a normalization, so the gate does its own."
    ),
    "router/cli.py::_print_preregistration_view": (
        "Defensive and, uniquely here, redundant: it reads the raw ``plan.execution`` "
        "mapping rather than the ``plan.run_mode`` accessor, and that mapping already "
        "holds the normalized value. Display-only code with no dispatch behind it, so "
        "it is pinned rather than touched — see the note below."
    ),
}

#: Where ``run_mode`` actually gets decided. Structurally different from the four
#: above: it is the only one that supplies a *default*, and the only one that
#: rejects a value outside RUN_MODES. Listed separately so that "there are four
#: re-deciders" stays a true statement about re-deciders.
NORMALIZER_OF_RECORD: dict[str, str] = {
    "router/run_plan.py::resolve_run_plan": (
        "Produces the canonical value: applies the override-then-YAML-then-``smoke`` "
        "precedence, validates against RUN_MODES, and seals it into "
        "``plan.execution['run_mode']`` where the plan hash covers it."
    ),
}

#: The one spelling every dispatch path is required to ask through.
CANONICAL_PREDICATE: dict[str, str] = {
    "router/foundry_live.py::is_benchmark_run_mode": (
        "The shared predicate itself. Its body *is* the normalization, so it appears "
        "in the sweep by construction; it is the definition, not a re-decision."
    ),
}

#: Inputs chosen to separate the spellings if they ever diverge: absent, blank,
#: whitespace- and case-mangled, a newline from a here-doc, and two near-misses
#: that must not be read as a benchmark.
PROBES: tuple[Any, ...] = (
    None, "", "   ", "benchmark", "BENCHMARK", " Benchmark ", "benchmark\n",
    "smoke", "Smoke", " SMOKE ", "bench", "benchmarking", "benchmark ",
)


class _Site:
    __slots__ = ("key", "lineno", "expr", "scope_source")

    def __init__(self, key: str, lineno: int, expr: str, scope_source: str) -> None:
        self.key = key
        self.lineno = lineno
        self.expr = expr
        self.scope_source = scope_source

    def __repr__(self) -> str:  # pragma: no cover - failure messages only
        return f"{self.key} (line {self.lineno}): {self.expr}"


def _scope(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> list[ast.AST]:
    chain: list[ast.AST] = []
    cur: ast.AST = node
    while cur in parents:
        cur = parents[cur]
        if isinstance(cur, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            chain.append(cur)
    return chain


def _normalization_sites() -> list[_Site]:
    """Every ``str(...).strip().lower()`` in ``src/`` whose subject is a run_mode.

    Matched on the idiom rather than on a variable name, because the failure this
    guards against is precisely someone writing the idiom out by hand in a new
    place. Reading the source is the only way to see that: the sites are spread
    across four modules and most are not reachable from one test.
    """

    sites: list[_Site] = []
    for path in sorted(SRC.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "lower"
            ):
                continue
            inner = node.func.value
            if not (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "strip"
            ):
                continue
            expr = ast.unparse(node)
            if "run_mode" not in expr:
                continue
            chain = _scope(node, parents)
            names = ".".join(n.name for n in reversed(chain))  # type: ignore[attr-defined]
            rel = path.relative_to(SRC).as_posix()
            scope_source = ast.unparse(chain[0]) if chain else source
            sites.append(_Site(f"{rel}::{names}", node.lineno, expr, scope_source))
    return sites


class _PlanStub:
    """Just enough of a ResolvedRunPlan for ``plan.execution.get('run_mode')``."""

    def __init__(self, run_mode: Any) -> None:
        self.execution = {"run_mode": run_mode}


def _evaluate(expr: str, probe: Any) -> str:
    """Run a site's own source text against one probe value.

    Evaluating the extracted expression, rather than a restatement of it, is what
    makes the equivalence below evidence instead of a second opinion: if someone
    edits the site, this test evaluates the edit.
    """

    namespace = {
        "run_mode": probe,
        "plan": _PlanStub(probe),
        "overrides": {},
        "data": {"run_mode": probe},
    }
    return eval(expr, {"__builtins__": {"str": str}}, namespace)  # noqa: S307


# --------------------------------------------------------------------------- #
# The pin
# --------------------------------------------------------------------------- #


def test_the_run_mode_normalization_sites_are_exactly_the_pinned_ones() -> None:
    """A fifth re-decider is a test failure until somebody classifies it.

    That is the whole ask: not to fix these four, but to make the next one visible
    at the moment it is written rather than the next time a fail-closed gate turns
    out to have been evaluating a smoke.
    """

    found = {site.key for site in _normalization_sites()}
    pinned = set(RE_DECIDERS) | set(NORMALIZER_OF_RECORD) | set(CANONICAL_PREDICATE)

    new = sorted(found - pinned)
    assert not new, (
        f"unpinned run_mode normalization site(s): {new}. Prefer calling "
        "router.foundry_live.is_benchmark_run_mode — it is the spelling the dispatch "
        "wiring and the provider scope-out gate share. If the site genuinely sits "
        "upstream of the resolved plan and cannot use the predicate, add it to "
        "RE_DECIDERS with the one-line reason."
    )

    gone = sorted(pinned - found)
    assert not gone, (
        f"pinned normalization site(s) that no longer exist: {gone}. Delete the "
        "entries; a stale pin is a false claim about the code."
    )


def test_every_pinned_site_carries_a_reason() -> None:
    """A pin with no reason cannot be reviewed, only obeyed."""

    for registry in (RE_DECIDERS, NORMALIZER_OF_RECORD, CANONICAL_PREDICATE):
        for key, reason in sorted(registry.items()):
            assert reason.strip(), f"{key} is pinned with no reason"


def test_there_are_exactly_four_re_deciders() -> None:
    """The count is load-bearing in the review record, so it is pinned as a count.

    The sweep finds six sites; two of them are not re-decisions — the predicate's
    own body and the resolver that produces the canonical value. Splitting them out
    is what makes "four" checkable rather than a matter of how you squint.
    """

    assert len(RE_DECIDERS) == 4, sorted(RE_DECIDERS)
    assert len(_normalization_sites()) == 6


# --------------------------------------------------------------------------- #
# Why pinning is enough: they already agree
# --------------------------------------------------------------------------- #


def test_every_re_decider_normalizes_identically_to_the_predicate() -> None:
    """The evidence behind "pin, do not fix".

    Each site's own expression is evaluated against the probe table and compared to
    the canonical predicate's. Equal normalized strings mean equal decisions, so
    leaving the four spellings in place costs nothing today — and the moment one of
    them is edited into disagreeing, this fails with the input that separates them.
    """

    sites = {site.key: site for site in _normalization_sites()}
    canonical = sites["router/foundry_live.py::is_benchmark_run_mode"]

    for key in sorted(RE_DECIDERS):
        site = sites[key]
        for probe in PROBES:
            expected = _evaluate(canonical.expr, probe)
            actual = _evaluate(site.expr, probe)
            assert actual == expected, (
                f"{site} disagrees with is_benchmark_run_mode on {probe!r}: "
                f"{actual!r} vs {expected!r}. Two spellings of the same question "
                "that answer differently is the exact defect this file exists to "
                "catch — route the site through the predicate."
            )


def test_the_predicate_reads_its_own_normalization_the_way_the_callers_do() -> None:
    """Ties the string comparison above back to the boolean callers actually use."""

    for probe in PROBES:
        normalized = _evaluate(
            "str(run_mode or '').strip().lower()", probe
        )
        assert is_benchmark_run_mode(probe) is (normalized == "benchmark")

    # And the near-misses really are misses, so the table has teeth.
    assert not is_benchmark_run_mode("bench")
    assert not is_benchmark_run_mode("benchmarking")
    assert not is_benchmark_run_mode(None)
    assert is_benchmark_run_mode(" Benchmark\n")


def test_only_the_normalizer_of_record_invents_a_mode() -> None:
    """A re-decider must report what it was given, not decide what was omitted.

    ``resolve_run_plan`` is allowed to turn an absent run_mode into ``smoke``: that
    is the declared default and the plan hash covers the result. A re-decider doing
    the same would be deciding a run's mode from a call site that has no standing to
    — and if it ever defaulted the other way, an unspecified plan would silently
    acquire a benchmark's authority to publish.
    """

    for key in sorted(RE_DECIDERS):
        site = {s.key: s for s in _normalization_sites()}[key]
        for probe in (None, ""):
            assert _evaluate(site.expr, probe) == "", (
                f"{site} turns an absent run_mode into {_evaluate(site.expr, probe)!r}. "
                "Only resolve_run_plan may supply a default."
            )

    producer = {s.key: s for s in _normalization_sites()}[
        "router/run_plan.py::resolve_run_plan"
    ]
    assert _evaluate(producer.expr, None) == "smoke"
    assert _evaluate(producer.expr, None) in RUN_MODES


def test_no_re_decider_compares_against_an_undeclared_mode_name() -> None:
    """Post-normalization, only the declared modes can ever match.

    A comparison against ``"Benchmark"`` or ``"bench"`` inside one of these scopes
    is unreachable code that reads as a live check — the most expensive kind of
    dead branch, because a reviewer counts it as protection.
    """

    allowed = set(RUN_MODES)
    sites = {s.key: s for s in _normalization_sites()}

    for key in sorted(RE_DECIDERS):
        site = sites[key]
        examined = 0
        for node in ast.walk(ast.parse(site.scope_source)):
            if not isinstance(node, ast.Compare):
                continue
            operands = [node.left, *node.comparators]
            literals = [
                n.value for n in operands
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            ]
            if not literals:
                continue
            # Either a normalized local (``mode``) or the inlined normalization
            # itself, which is how accounting.py spells the same comparison.
            texts = [ast.unparse(n) for n in operands]
            subject = any(
                text in {"mode", "run_mode", "benchmark_mode"} or "run_mode" in text
                for text in texts
            )
            if not subject:
                continue
            examined += 1
            for literal in literals:
                assert literal in allowed, (
                    f"{site.key} compares a normalized run_mode against {literal!r}, "
                    f"which is not in RUN_MODES {RUN_MODES}. After "
                    "str(...).strip().lower() that branch can never be taken."
                )

        assert examined, (
            f"{site.key} normalizes a run_mode and then compares it against no mode "
            "name at all — either the check above has gone vacuous for this site, or "
            "the normalization is now dead. Both are worth a look."
        )
