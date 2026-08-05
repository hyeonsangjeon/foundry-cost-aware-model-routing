"""Grader for `collect-active` (refactor).

Behaviour must be preserved while the manual accumulate loop is replaced by a
comprehension. Structural constraint: a list comprehension is present and no
``for`` statement remains.
"""

from __future__ import annotations

import ast
import types

from harness.checks import (
    ast_forbids_node,
    ast_requires_node,
    check_cases,
    grade_refactor,
    require,
)


def grade(module: types.ModuleType, source: str) -> None:
    require(module, "collect_active")

    def behavior(mod: types.ModuleType) -> None:
        records = [
            {"id": 1, "state": "on"},
            {"id": 2, "state": "off"},
            {"id": 3, "state": "on"},
        ]
        check_cases(
            mod.collect_active,
            [
                ((records,), [1, 3]),
                (([],), []),
                (([{"id": 9, "state": "off"}],), []),
                (([{"id": 5, "state": "on"}],), [5]),
            ],
        )

    grade_refactor(
        module,
        source,
        behavior=[behavior],
        structure=[
            ast_requires_node(ast.ListComp, at_least=1, label="list comprehension"),
            ast_forbids_node(ast.For, label="for statement"),
        ],
    )
