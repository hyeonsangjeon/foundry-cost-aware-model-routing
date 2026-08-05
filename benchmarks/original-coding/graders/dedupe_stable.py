"""Grader for `dedupe-stable` (refactor).

Behaviour must be preserved while the quadratic nested-loop membership scan is
replaced by a single-pass approach. Structural constraint: at most one ``for``
statement (a set/dict-based pass, a comprehension, or ``dict.fromkeys`` all
satisfy it; the nested ``for``-in-``for`` smell does not).
"""

from __future__ import annotations

import ast
import types

from harness.checks import ast_max_nodes, check_cases, grade_refactor, require


def grade(module: types.ModuleType, source: str) -> None:
    require(module, "dedupe_stable")

    def behavior(mod: types.ModuleType) -> None:
        check_cases(
            mod.dedupe_stable,
            [
                (([1, 2, 1, 3, 2],), [1, 2, 3]),
                (([],), []),
                (([5, 5, 5],), [5]),
                ((["a", "b", "a"],), ["a", "b"]),
                (([1, 2, 3],), [1, 2, 3]),
            ],
        )

    grade_refactor(
        module,
        source,
        behavior=[behavior],
        structure=[ast_max_nodes(ast.For, 1, label="for statement")],
    )
