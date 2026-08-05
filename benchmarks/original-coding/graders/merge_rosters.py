"""Grader for `merge-rosters` (bug-fix).

Merge two ascending rosters into one strictly-ascending roster with no repeats.
The shipped code only de-duplicates values that coincide across the two streams
during the merge; duplicates *within* a single stream (and the ones that spill
into the tail copy) slip through. A correct fix suppresses every repeat.
"""

from __future__ import annotations

import types

from harness.checks import check_cases, expect, grade_bugfix, require


def grade(module: types.ModuleType, source: str) -> None:
    require(module, "merge_rosters")

    def reproduction(mod: types.ModuleType) -> None:
        expect(
            mod.merge_rosters([1, 2, 2, 3], [2, 4]) == [1, 2, 3, 4],
            "duplicates within a stream must be collapsed, not passed through",
        )

    def regression(mod: types.ModuleType) -> None:
        check_cases(
            mod.merge_rosters,
            [
                (([1, 3, 5], [2, 4, 6]), [1, 2, 3, 4, 5, 6]),
                (([], []), []),
                (([1, 2, 3], []), [1, 2, 3]),
                (([1, 1, 1], [1]), [1]),
                (([2, 4], [1, 2, 3, 4, 5]), [1, 2, 3, 4, 5]),
            ],
        )

    grade_bugfix(module, reproduction=reproduction, regression=[regression])
