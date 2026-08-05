"""Grader for `even-parity` (test-writing).

The candidate submits ``TESTS`` for ``even_parity``. The suite must pass the
reference implementation and kill every mutant.
"""

from __future__ import annotations

import types

from harness.checks import expect, mutation_kills, require

REFERENCE = '''
def even_parity(bits):
    for bit in bits:
        if bit not in (0, 1):
            raise ValueError("bits must be 0 or 1")
    return sum(bits) % 2
'''

MUTANTS = [
    # M1: constant zero.
    '''
def even_parity(bits):
    for bit in bits:
        if bit not in (0, 1):
            raise ValueError("bits must be 0 or 1")
    return 0
''',
    # M2: computes odd parity.
    '''
def even_parity(bits):
    for bit in bits:
        if bit not in (0, 1):
            raise ValueError("bits must be 0 or 1")
    return (sum(bits) + 1) % 2
''',
    # M3: drops input validation.
    '''
def even_parity(bits):
    return sum(bits) % 2
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
