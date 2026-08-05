"""Grader for `horizon-peaks` (bug-fix).

The prompt ships a windowed-maximum with an off-by-one slice. A correct fix must
pass the bug-reproduction case (which the buggy code fails) and the regression
suite, and must validate the span.
"""

from __future__ import annotations

import types

from harness.checks import check_cases, check_raises, expect, grade_bugfix, require


def grade(module: types.ModuleType, source: str) -> None:
    require(module, "horizon_peaks")

    def reproduction(mod: types.ModuleType) -> None:
        # The trailing window must INCLUDE the current sample.
        expect(
            mod.horizon_peaks([3, 1, 4, 1, 5], 2) == [3, 3, 4, 4, 5],
            "each output must be the max of the window ending at the current index",
        )

    def regression_cases(mod: types.ModuleType) -> None:
        check_cases(
            mod.horizon_peaks,
            [
                (([5], 3), [5]),
                (([2, 2, 2], 1), [2, 2, 2]),
                (([1, 2, 3, 4], 2), [1, 2, 3, 4]),
                (([4, 3, 2, 1], 2), [4, 4, 3, 2]),
                (([7, 1, 1, 1, 9], 10), [7, 7, 7, 7, 9]),
            ],
        )

    def regression_raises(mod: types.ModuleType) -> None:
        check_raises(mod.horizon_peaks, ([1, 2], 0), ValueError)
        check_raises(mod.horizon_peaks, ([1, 2], -3), ValueError)

    grade_bugfix(
        module,
        reproduction=reproduction,
        regression=[regression_cases, regression_raises],
    )
