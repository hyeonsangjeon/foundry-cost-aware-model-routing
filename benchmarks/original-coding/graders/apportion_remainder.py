"""Grader for `apportion-remainder` (bug-fix).

The shipped code distributes ``total // buckets`` to every bucket and silently
drops the remainder, so the parts don't sum back to ``total``. A correct fix
hands the remainder to the earliest buckets.
"""

from __future__ import annotations

import types

from harness.checks import check_cases, check_raises, expect, grade_bugfix, require


def grade(module: types.ModuleType, source: str) -> None:
    require(module, "apportion")

    def reproduction(mod: types.ModuleType) -> None:
        result = mod.apportion(10, 3)
        expect(sum(result) == 10, "apportioned parts must sum back to the total")
        expect(result == [4, 3, 3], "the remainder must go to the earliest buckets")

    def regression(mod: types.ModuleType) -> None:
        check_cases(
            mod.apportion,
            [
                ((9, 3), [3, 3, 3]),
                ((0, 4), [0, 0, 0, 0]),
                ((5, 1), [5]),
                ((7, 4), [2, 2, 2, 1]),
            ],
        )
        check_raises(mod.apportion, (5, 0), ValueError)
        check_raises(mod.apportion, (-1, 3), ValueError)

    grade_bugfix(module, reproduction=reproduction, regression=[regression])
