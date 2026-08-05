def _t_returns_a_list(m):
    # Far too weak: every mutant also returns a list here, so none are killed.
    assert isinstance(m.normalize_cadence([1, 1]), list)


TESTS = [_t_returns_a_list]
