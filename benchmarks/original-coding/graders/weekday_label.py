"""Grader for `weekday-label` (refactor).

Behaviour must be preserved while the seven-way ``if/elif`` ladder is replaced by
a lookup table. Structural constraint: at most one ``if`` remains (range check).
"""

from __future__ import annotations

import ast
import types

from harness.checks import ast_max_nodes, check_cases, check_raises, grade_refactor, require


def grade(module: types.ModuleType, source: str) -> None:
    require(module, "weekday_label")

    def behavior(mod: types.ModuleType) -> None:
        check_cases(
            mod.weekday_label,
            [
                ((0,), "Mon"),
                ((1,), "Tue"),
                ((3,), "Thu"),
                ((6,), "Sun"),
            ],
        )
        check_raises(mod.weekday_label, (7,), ValueError)
        check_raises(mod.weekday_label, (-1,), ValueError)

    grade_refactor(
        module,
        source,
        behavior=[behavior],
        structure=[ast_max_nodes(ast.If, 1, label="if")],
    )
