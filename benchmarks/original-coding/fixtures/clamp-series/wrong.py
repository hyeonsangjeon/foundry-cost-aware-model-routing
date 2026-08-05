def _t_returns_list(m):
    # Too weak: shape-only assertions leave every mutant alive.
    result = m.clamp_series([1, 2], 0, 10)
    assert isinstance(result, list)
    assert len(result) == 2


TESTS = [_t_returns_list]
