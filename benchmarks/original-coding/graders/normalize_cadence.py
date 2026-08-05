"""Grader for `normalize-cadence` (test-writing).

The candidate submits a ``TESTS`` list of callables (each taking an impl module).
The suite must pass the correct reference implementation and *kill* every mutant
below. Reference and mutant sources live here so they never leak into the task
JSONL.
"""

from __future__ import annotations

import types

from harness.checks import expect, mutation_kills, require

REFERENCE = '''
def normalize_cadence(beats):
    if any(b <= 0 for b in beats):
        raise ValueError("beats must be positive")
    total = sum(beats)
    if not beats:
        return []
    return [b / total for b in beats]
'''

MUTANTS = [
    # M1: forgets to normalise.
    '''
def normalize_cadence(beats):
    if any(b <= 0 for b in beats):
        raise ValueError("beats must be positive")
    return list(beats)
''',
    # M2: drops the positivity validation.
    '''
def normalize_cadence(beats):
    if not beats:
        return []
    total = sum(beats)
    return [b / total for b in beats]
''',
    # M3: normalises against the max instead of the sum.
    '''
def normalize_cadence(beats):
    if any(b <= 0 for b in beats):
        raise ValueError("beats must be positive")
    if not beats:
        return []
    scale = max(beats)
    return [b / scale for b in beats]
''',
    # M4: returns None instead of [] for the empty cadence.
    '''
def normalize_cadence(beats):
    if any(b <= 0 for b in beats):
        raise ValueError("beats must be positive")
    if not beats:
        return None
    total = sum(beats)
    return [b / total for b in beats]
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
    expect(
        killed == len(MUTANTS),
        f"the test suite killed only {killed}/{len(MUTANTS)} mutants",
    )
