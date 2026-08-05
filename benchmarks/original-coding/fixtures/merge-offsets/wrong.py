def _t_length_only(m):
    # Too weak: every mutant preserves length, so none are killed.
    assert len(m.merge_offsets(1, [1, 2, 3])) == 3


TESTS = [_t_length_only]
