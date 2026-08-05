"""Reusable grading primitives shared by every task grader.

A grader is a small module in ``graders/<task_id>.py`` exposing a single
``grade(module, source)`` function. It receives the candidate's imported module
and its raw source text, and raises :class:`GradeError` (a subclass of
``AssertionError``) on any failure. These helpers keep each grader to a handful
of declarative lines while centralising the four grading disciplines:

* **implementation / edge-case** — hidden input/output cases plus exception-type
  checks (:func:`check_cases`, :func:`check_raises`);
* **bug-fix** — a bug-reproduction test and a regression suite that must *both*
  pass on the corrected code (:func:`grade_bugfix`);
* **refactor** — behaviour preservation plus AST structural constraints
  (:func:`grade_refactor`, the ``ast_*`` helpers);
* **test-writing** — the candidate's tests must pass a reference implementation
  and kill a fixed number of mutants (:func:`mutation_kills`).

No helper performs I/O, timing, or network access; determinism and isolation are
provided by :mod:`harness.sandbox` and the per-run subprocess.
"""

from __future__ import annotations

import ast
import types
from collections.abc import Callable, Iterable, Sequence
from typing import Any


class GradeError(AssertionError):
    """A candidate submission failed a grading check."""


def expect(condition: object, message: str) -> None:
    if not condition:
        raise GradeError(message)


def require(module: types.ModuleType, name: str) -> Any:
    """Return ``module.name`` or fail with a clear message."""

    if not hasattr(module, name):
        raise GradeError(f"submission must define {name!r}")
    return getattr(module, name)


# --------------------------------------------------------------------------- #
# implementation / edge-case
# --------------------------------------------------------------------------- #


def check_cases(fn: Callable[..., Any], cases: Iterable[tuple[tuple[Any, ...], Any]]) -> None:
    """Assert ``fn(*args) == expected`` for every ``(args, expected)`` case."""

    for args, expected in cases:
        got = fn(*args)
        if got != expected:
            raise GradeError(f"{fn.__name__}{args!r} == {got!r}, expected {expected!r}")


def check_predicate(
    fn: Callable[..., Any],
    cases: Iterable[tuple[tuple[Any, ...], Callable[[Any], bool]]],
) -> None:
    """Assert ``predicate(fn(*args))`` for every ``(args, predicate)`` case."""

    for args, predicate in cases:
        got = fn(*args)
        if not predicate(got):
            raise GradeError(f"{fn.__name__}{args!r} == {got!r} failed its predicate")


def check_raises(
    fn: Callable[..., Any], args: tuple[Any, ...], exc_type: type[BaseException]
) -> None:
    """Assert ``fn(*args)`` raises exactly ``exc_type`` (or a subclass)."""

    try:
        fn(*args)
    except exc_type:
        return
    except BaseException as exc:  # noqa: BLE001 - we report the wrong type
        raise GradeError(
            f"{fn.__name__}{args!r} raised {type(exc).__name__}, expected {exc_type.__name__}"
        ) from None
    raise GradeError(f"{fn.__name__}{args!r} did not raise; expected {exc_type.__name__}")


# --------------------------------------------------------------------------- #
# bug-fix
# --------------------------------------------------------------------------- #


def grade_bugfix(
    module: types.ModuleType,
    *,
    reproduction: Callable[[types.ModuleType], None],
    regression: Sequence[Callable[[types.ModuleType], None]],
) -> None:
    """A fixed submission must pass the bug-reproduction test *and* every
    regression test. The reproduction test is written to fail on the original
    buggy behaviour, so passing it proves the specific defect is gone; the
    regression suite proves nothing else broke."""

    reproduction(module)
    for test in regression:
        test(module)


# --------------------------------------------------------------------------- #
# refactor — behaviour + AST structure
# --------------------------------------------------------------------------- #


def grade_refactor(
    module: types.ModuleType,
    source: str,
    *,
    behavior: Sequence[Callable[[types.ModuleType], None]],
    structure: Sequence[Callable[[ast.AST], None]],
) -> None:
    """Behaviour must be preserved *and* the AST must satisfy every structural
    constraint (e.g. duplication removed, a loop replaced by a comprehension)."""

    for test in behavior:
        test(module)
    tree = ast.parse(source)
    for constraint in structure:
        constraint(tree)


def ast_max_functions(limit: int) -> Callable[[ast.AST], None]:
    def _check(tree: ast.AST) -> None:
        defs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]
        expect(
            len(defs) <= limit,
            f"expected at most {limit} function definitions, found {len(defs)}",
        )
    return _check


def ast_forbids_call(*names: str) -> Callable[[ast.AST], None]:
    wanted = set(names)

    def _check(tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                called = _call_name(node.func)
                if called in wanted:
                    raise GradeError(f"refactor must not call {called!r}")
    return _check


def ast_requires_node(
    node_type: type[ast.AST], *, at_least: int = 1, label: str | None = None
) -> Callable[[ast.AST], None]:
    name = label or node_type.__name__

    def _check(tree: ast.AST) -> None:
        count = sum(1 for n in ast.walk(tree) if isinstance(n, node_type))
        expect(count >= at_least, f"expected at least {at_least} {name} node(s), found {count}")
    return _check


def ast_max_nodes(
    node_type: type[ast.AST], limit: int, *, label: str | None = None
) -> Callable[[ast.AST], None]:
    name = label or node_type.__name__

    def _check(tree: ast.AST) -> None:
        count = sum(1 for n in ast.walk(tree) if isinstance(n, node_type))
        expect(count <= limit, f"expected at most {limit} {name} node(s), found {count}")
    return _check


def ast_forbids_node(
    node_type: type[ast.AST], *, label: str | None = None
) -> Callable[[ast.AST], None]:
    name = label or node_type.__name__

    def _check(tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, node_type):
                raise GradeError(f"refactor must not use a {name} node")
    return _check


def ast_max_depth(limit: int) -> Callable[[ast.AST], None]:
    """Fail if nested compound-statement depth exceeds ``limit`` (a proxy for
    the deeply nested branches a refactor is expected to flatten)."""

    compound = (
        ast.If, ast.For, ast.While, ast.With, ast.Try,
        ast.AsyncFor, ast.AsyncWith,
    )

    def _depth(node: ast.AST, current: int) -> int:
        best = current
        for child in ast.iter_child_nodes(node):
            step = current + 1 if isinstance(child, compound) else current
            best = max(best, _depth(child, step))
        return best

    def _check(tree: ast.AST) -> None:
        depth = _depth(tree, 0)
        expect(depth <= limit, f"nesting depth {depth} exceeds allowed {limit}")
    return _check


def _call_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


# --------------------------------------------------------------------------- #
# test-writing — mutation testing
# --------------------------------------------------------------------------- #


def build_module(source: str, name: str = "impl") -> types.ModuleType:
    """Compile ``source`` into a fresh, isolated module object."""

    module = types.ModuleType(name)
    module.__dict__["__name__"] = name
    exec(compile(source, f"<{name}>", "exec"), module.__dict__)  # noqa: S102 - sandboxed
    return module


def mutation_kills(
    tests: Sequence[Callable[[types.ModuleType], None]],
    *,
    reference_source: str,
    mutant_sources: Sequence[str],
) -> int:
    """Run candidate ``tests`` against a reference implementation and each
    mutant. Every test must pass the reference (or the suite is invalid); a
    mutant is *killed* when at least one test raises against it. Returns the
    number of mutants killed.

    Raises :class:`GradeError` if the suite is empty or fails the reference —
    that prevents a vacuous "always pass" suite from scoring kills by accident.
    """

    if not tests:
        raise GradeError("no tests were provided by the submission")

    reference = build_module(reference_source, "solution")
    for test in tests:
        try:
            test(reference)
        except GradeError:
            raise
        except BaseException as exc:  # noqa: BLE001
            raise GradeError(
                f"a submitted test failed the correct reference implementation: "
                f"{type(exc).__name__}: {exc}"
            ) from None

    killed = 0
    for index, mutant_source in enumerate(mutant_sources):
        mutant = build_module(mutant_source, f"mutant_{index}")
        for test in tests:
            try:
                test(mutant)
            except BaseException:  # noqa: BLE001 - any failure kills the mutant
                killed += 1
                break
    return killed
