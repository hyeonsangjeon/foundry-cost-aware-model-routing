def _t_adds_base(m):
    assert m.merge_offsets(10, [0, 1, 2]) == [10, 11, 12]


def _t_base_matters(m):
    assert m.merge_offsets(5, [0]) == [5]


def _t_rejects_negative(m):
    try:
        m.merge_offsets(0, [1, -1])
    except ValueError:
        return
    raise AssertionError("expected ValueError for a negative delta")


TESTS = [_t_adds_base, _t_base_matters, _t_rejects_negative]
