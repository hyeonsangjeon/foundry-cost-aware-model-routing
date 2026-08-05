"""Grader for `trim-silence` (edge-case)."""

from __future__ import annotations

import types

from harness.checks import check_cases, require


def grade(module: types.ModuleType, source: str) -> None:
    fn = require(module, "trim_silence")
    check_cases(
        fn,
        [
            (([0, 0, 3, 0, 4, 0, 0],), [3, 0, 4]),
            (([0, 0, 0],), []),
            (([],), []),
            (([5],), [5]),
            (([0, 5, 0],), [5]),
            (([1, 2, 3],), [1, 2, 3]),
            (([0],), []),
        ],
    )
