"""Grader for `merge-offsets` (test-writing).

The candidate submits ``TESTS`` for ``merge_offsets(base, deltas)``, which adds
``base`` to each non-negative delta. The suite must pass the reference and kill
every mutant.
"""

from __future__ import annotations

import types

from harness.checks import expect, mutation_kills, require

REFERENCE = '''
def merge_offsets(base, deltas):
    for delta in deltas:
        if delta < 0:
            raise ValueError("deltas must be non-negative")
    return [base + delta for delta in deltas]
'''

MUTANTS = [
    # M1: subtracts instead of adds.
    '''
def merge_offsets(base, deltas):
    for delta in deltas:
        if delta < 0:
            raise ValueError("deltas must be non-negative")
    return [base - delta for delta in deltas]
''',
    # M2: ignores the base entirely.
    '''
def merge_offsets(base, deltas):
    for delta in deltas:
        if delta < 0:
            raise ValueError("deltas must be non-negative")
    return [delta for delta in deltas]
''',
    # M3: drops the validation.
    '''
def merge_offsets(base, deltas):
    return [base + delta for delta in deltas]
''',
    # M4: multiplies instead of adds.
    '''
def merge_offsets(base, deltas):
    for delta in deltas:
        if delta < 0:
            raise ValueError("deltas must be non-negative")
    return [base * delta for delta in deltas]
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
