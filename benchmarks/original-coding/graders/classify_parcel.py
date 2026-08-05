"""Grader for `classify-parcel` (refactor).

Behaviour of `parcel_band` must be preserved while the deeply nested branch
ladder in the prompt is flattened. Structural constraint: nesting depth <= 2.
"""

from __future__ import annotations

import types

from harness.checks import (
    ast_max_depth,
    check_cases,
    check_raises,
    grade_refactor,
    require,
)


def grade(module: types.ModuleType, source: str) -> None:
    require(module, "parcel_band")

    def behavior(mod: types.ModuleType) -> None:
        check_cases(
            mod.parcel_band,
            [
                ((50, "inner"), "I-S"),
                ((100, "inner"), "I-S"),
                ((500, "inner"), "I-M"),
                ((1000, "inner"), "I-M"),
                ((5000, "inner"), "I-L"),
                ((50, "outer"), "O-S"),
                ((100, "outer"), "O-S"),
                ((999, "outer"), "O-M"),
                ((2000, "outer"), "O-L"),
            ],
        )
        check_raises(mod.parcel_band, (0, "inner"), ValueError)
        check_raises(mod.parcel_band, (-5, "outer"), ValueError)
        check_raises(mod.parcel_band, (10, "middle"), ValueError)

    grade_refactor(
        module,
        source,
        behavior=[behavior],
        structure=[ast_max_depth(2)],
    )
