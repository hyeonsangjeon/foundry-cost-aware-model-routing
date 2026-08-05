"""Grader for `first-deficit` (bug-fix).

The shipped code tests the running total *before* adding the current delta, so it
reports the crossing one step late (or misses it entirely). A correct fix adds
the delta first, then checks whether the prefix sum has gone negative.
"""

from __future__ import annotations

import types

from harness.checks import check_cases, expect, grade_bugfix, require


def grade(module: types.ModuleType, source: str) -> None:
    require(module, "first_deficit")

    def reproduction(mod: types.ModuleType) -> None:
        expect(
            mod.first_deficit([3, -1, -5]) == 2,
            "the first index whose prefix sum is negative is 2",
        )

    def regression(mod: types.ModuleType) -> None:
        check_cases(
            mod.first_deficit,
            [
                (([1, 2, 3],), -1),
                (([-1],), 0),
                (([5, -10, 100],), 1),
                (([0, 0, -1],), 2),
                (([],), -1),
            ],
        )

    grade_bugfix(module, reproduction=reproduction, regression=[regression])
