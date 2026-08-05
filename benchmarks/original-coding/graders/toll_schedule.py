"""Grader for `toll-schedule` (implementation).

Overlapping toll segments must contribute the MAX active rate at each time unit,
not the sum. Half-open intervals ``[start, end)``.
"""

from __future__ import annotations

import types

from harness.checks import check_cases, check_raises, require


def grade(module: types.ModuleType, source: str) -> None:
    fn = require(module, "toll_schedule")
    check_cases(
        fn,
        [
            (([(0, 5, 2)], [(0, 5)]), [10]),
            (([(0, 4, 2), (2, 6, 5)], [(0, 6)]), [24]),
            (([(0, 2, 3)], [(0, 4), (1, 1)]), [6, 0]),
            (([], [(0, 3)]), [0]),
            (([(0, 3, 4), (1, 2, 9)], [(0, 3)]), [17]),
        ],
    )
    check_raises(fn, ([(5, 2, 1)], [(0, 1)]), ValueError)
    check_raises(fn, ([(0, 5, 2)], [(3, 1)]), ValueError)
