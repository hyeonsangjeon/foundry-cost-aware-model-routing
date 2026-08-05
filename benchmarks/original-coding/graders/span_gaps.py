"""Grader for `span-gaps` (implementation)."""

from __future__ import annotations

import types

from harness.checks import check_cases, check_raises, require


def grade(module: types.ModuleType, source: str) -> None:
    fn = require(module, "span_gaps")
    check_cases(
        fn,
        [
            (([2, 5, 9],), [3, 4]),
            (([],), []),
            (([7],), []),
            (([0, 1, 2, 3],), [1, 1, 1]),
            (([10, 20, 45],), [10, 25]),
        ],
    )
    check_raises(fn, ([3, 3],), ValueError)
    check_raises(fn, ([5, 4],), ValueError)
