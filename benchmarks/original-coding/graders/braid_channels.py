"""Grader for `braid-channels` (implementation).

Hidden I/O cases plus exception-type checks for the strided regrouping.
"""

from __future__ import annotations

import types

from harness.checks import check_cases, check_raises, require


def grade(module: types.ModuleType, source: str) -> None:
    fn = require(module, "braid_channels")
    check_cases(
        fn,
        [
            (([10, 11, 12, 13, 14], 2), [10, 12, 14, 11, 13]),
            (([1, 2, 3, 4, 5, 6], 3), [1, 4, 2, 5, 3, 6]),
            (([], 4), []),
            (([9], 1), [9]),
            (([5, 6, 7], 5), [5, 6, 7]),
            (([0, 1, 2, 3, 4, 5, 6, 7], 4), [0, 4, 1, 5, 2, 6, 3, 7]),
        ],
    )
    check_raises(fn, ([1, 2, 3], 0), ValueError)
    check_raises(fn, ([1, 2, 3], -2), ValueError)
