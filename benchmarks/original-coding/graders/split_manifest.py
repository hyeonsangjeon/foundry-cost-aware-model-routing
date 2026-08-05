"""Grader for `split-manifest` (edge-case).

Focuses on boundary conditions (empty input, capacity of one, capacity larger
than the manifest, exact multiples) and exact exception types for invalid
capacities (``TypeError`` vs ``ValueError``, including the bool-is-not-int trap).
"""

from __future__ import annotations

import types

from harness.checks import check_cases, check_raises, require


def grade(module: types.ModuleType, source: str) -> None:
    fn = require(module, "split_manifest")
    check_cases(
        fn,
        [
            (([1, 2, 3, 4], 2), [[1, 2], [3, 4]]),
            (([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]),
            (([], 3), []),
            (([9], 1), [[9]]),
            (([1, 2], 5), [[1, 2]]),
            (([1, 2, 3], 1), [[1], [2], [3]]),
        ],
    )
    check_raises(fn, ([1, 2, 3], 0), ValueError)
    check_raises(fn, ([1, 2, 3], -1), ValueError)
    check_raises(fn, ([1, 2, 3], 2.0), TypeError)
    check_raises(fn, ([1, 2, 3], True), TypeError)
