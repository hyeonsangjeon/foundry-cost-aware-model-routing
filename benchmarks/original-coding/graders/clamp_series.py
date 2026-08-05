"""Grader for `clamp-series` (test-writing).

The candidate submits ``TESTS`` for ``clamp_series(xs, lo, hi)``, which clamps
each value into ``[lo, hi]`` and rejects ``lo > hi``. The suite must pass the
reference and kill every mutant, including the ones that only clamp one side.
"""

from __future__ import annotations

import types

from harness.checks import expect, mutation_kills, require

REFERENCE = '''
def clamp_series(xs, lo, hi):
    if lo > hi:
        raise ValueError("lo must not exceed hi")
    return [lo if x < lo else hi if x > hi else x for x in xs]
'''

MUTANTS = [
    # M1: clamps only the low side.
    '''
def clamp_series(xs, lo, hi):
    if lo > hi:
        raise ValueError("lo must not exceed hi")
    return [lo if x < lo else x for x in xs]
''',
    # M2: clamps only the high side.
    '''
def clamp_series(xs, lo, hi):
    if lo > hi:
        raise ValueError("lo must not exceed hi")
    return [hi if x > hi else x for x in xs]
''',
    # M3: drops the bound validation.
    '''
def clamp_series(xs, lo, hi):
    return [lo if x < lo else hi if x > hi else x for x in xs]
''',
    # M4: returns the series unchanged.
    '''
def clamp_series(xs, lo, hi):
    if lo > hi:
        raise ValueError("lo must not exceed hi")
    return list(xs)
''',
    # M5: swaps which bound each side clamps to.
    '''
def clamp_series(xs, lo, hi):
    if lo > hi:
        raise ValueError("lo must not exceed hi")
    return [hi if x < lo else lo if x > hi else x for x in xs]
''',
]


def grade(module: types.ModuleType, source: str) -> None:
    tests = require(module, "TESTS")
    expect(
        isinstance(tests, (list, tuple)) and len(tests) > 0,
        "TESTS must be a non-empty list of callables",
    )
    for test in tests:
        expect(callable(test), "every entry in TESTS must be callable")
    killed = mutation_kills(tests, reference_source=REFERENCE, mutant_sources=MUTANTS)
    expect(killed == len(MUTANTS), f"the test suite killed only {killed}/{len(MUTANTS)} mutants")
