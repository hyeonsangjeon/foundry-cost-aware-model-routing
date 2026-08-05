"""Grader for `quorum-threshold` (implementation)."""

from __future__ import annotations

import types

from harness.checks import check_cases, check_raises, require


def grade(module: types.ModuleType, source: str) -> None:
    fn = require(module, "quorum_threshold")
    check_cases(
        fn,
        [
            (([1, 1, 1, 2, 3], 0.5), [1]),
            (([1, 2, 3, 4], 0.25), []),
            (([5, 5, 6, 6], 0.5), []),
            (([7, 7, 7], 0.5), [7]),
            (([], 0.5), []),
            (([1, 1, 2, 2, 2], 0.4), [2]),
        ],
    )
    check_raises(fn, ([1], 0), ValueError)
    check_raises(fn, ([1], 1.5), ValueError)
