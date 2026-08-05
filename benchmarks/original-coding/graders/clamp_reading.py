"""Grader for `clamp-reading` (edge-case)."""

from __future__ import annotations

import types

from harness.checks import check_cases, check_raises, require


def grade(module: types.ModuleType, source: str) -> None:
    fn = require(module, "clamp_reading")
    check_cases(
        fn,
        [
            ((5, 0, 10), 5),
            ((-3, 0, 10), 0),
            ((99, 0, 10), 10),
            ((0, 0, 10), 0),
            ((10, 0, 10), 10),
            ((7, 7, 7), 7),
        ],
    )
    check_raises(fn, (5, 10, 0), ValueError)
    check_raises(fn, (True, 0, 10), TypeError)
    check_raises(fn, (5, False, 10), TypeError)
