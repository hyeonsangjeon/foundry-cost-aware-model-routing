"""Grader for `stripe-partition` (implementation)."""

from __future__ import annotations

import types

from harness.checks import check_cases, check_raises, require


def grade(module: types.ModuleType, source: str) -> None:
    fn = require(module, "stripe_partition")
    check_cases(
        fn,
        [
            ((10, 3), [(0, 4), (4, 7), (7, 10)]),
            ((9, 3), [(0, 3), (3, 6), (6, 9)]),
            ((2, 3), [(0, 1), (1, 2), (2, 2)]),
            ((0, 2), [(0, 0), (0, 0)]),
            ((5, 1), [(0, 5)]),
        ],
    )
    check_raises(fn, (5, 0), ValueError)
    check_raises(fn, (-1, 3), ValueError)
