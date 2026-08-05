"""Grader for `running-parity` (bug-fix).

The shipped code seeds the running parity accumulator with 1 instead of 0, so the
very first output is inverted. A correct fix makes ``out[0] == bits[0]``.
"""

from __future__ import annotations

import types

from harness.checks import check_cases, expect, grade_bugfix, require


def grade(module: types.ModuleType, source: str) -> None:
    require(module, "running_parity")

    def reproduction(mod: types.ModuleType) -> None:
        expect(
            mod.running_parity([0]) == [0],
            "the running parity of a single 0 must be 0, not 1",
        )

    def regression(mod: types.ModuleType) -> None:
        check_cases(
            mod.running_parity,
            [
                (([1],), [1]),
                (([1, 1],), [1, 0]),
                (([1, 0, 1],), [1, 1, 0]),
                (([],), []),
                (([0, 0, 0],), [0, 0, 0]),
            ],
        )

    grade_bugfix(module, reproduction=reproduction, regression=[regression])
