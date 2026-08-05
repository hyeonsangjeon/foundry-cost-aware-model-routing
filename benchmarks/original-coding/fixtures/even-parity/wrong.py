def _t_in_range(m):
    # Too weak: every mutant also returns 0 or 1, so nothing is killed.
    assert m.even_parity([1, 1]) in (0, 1)


TESTS = [_t_in_range]
