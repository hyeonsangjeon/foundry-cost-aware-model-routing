"""Grader for `bucketize` (edge-case). Half-open buckets ``[edge[i], edge[i+1])``."""

from __future__ import annotations

import types

from harness.checks import check_cases, check_raises, require


def grade(module: types.ModuleType, source: str) -> None:
    fn = require(module, "bucketize")
    check_cases(
        fn,
        [
            (([1, 2, 3, 4, 5], [0, 3, 6]), [2, 3]),
            (([3], [0, 3, 6]), [0, 1]),
            (([6], [0, 3, 6]), [0, 0]),
            (([-1, 0], [0, 3, 6]), [1, 0]),
            (([], [0, 10]), [0]),
        ],
    )
    check_raises(fn, ([1], [5]), ValueError)
    check_raises(fn, ([1], [0, 0, 1]), ValueError)
    check_raises(fn, ([1], [3, 1]), ValueError)
