"""Grader for `align-frames` (edge-case).

Inner-join two timestamp-sorted streams on matching timestamps. Each stream must
be strictly increasing in timestamp.
"""

from __future__ import annotations

import types

from harness.checks import check_cases, check_raises, require


def grade(module: types.ModuleType, source: str) -> None:
    fn = require(module, "align_frames")
    check_cases(
        fn,
        [
            (
                ([(1, "a"), (2, "b"), (3, "c")], [(2, "x"), (3, "y"), (4, "z")]),
                [(2, "b", "x"), (3, "c", "y")],
            ),
            (([], [(1, "a")]), []),
            (([(1, "a")], [(2, "b")]), []),
            (([(1, "a"), (5, "e")], [(5, "z")]), [(5, "e", "z")]),
        ],
    )
    check_raises(fn, ([(1, "a"), (1, "b")], [(2, "c")]), ValueError)
    check_raises(fn, ([(1, "a")], [(3, "b"), (3, "c")]), ValueError)
