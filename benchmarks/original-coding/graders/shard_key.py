"""Grader for `shard-key` (implementation)."""

from __future__ import annotations

import types

from harness.checks import check_cases, check_raises, require


def grade(module: types.ModuleType, source: str) -> None:
    fn = require(module, "shard_key")
    check_cases(
        fn,
        [
            (("abcdefgh", 3), "ADG"),
            (("abcdefgh", 1), "ABCDEFGH"),
            (("", 2), ""),
            (("xy", 5), "X"),
            (("hello world", 4), "HOR"),
        ],
    )
    check_raises(fn, ("abc", 0), ValueError)
    check_raises(fn, ("abc", -1), ValueError)
