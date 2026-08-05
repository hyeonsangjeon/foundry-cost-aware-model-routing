def _t_sums_to_one(m):
    result = m.normalize_cadence([1, 1, 2])
    assert abs(sum(result) - 1.0) < 1e-9
    assert len(result) == 3


def _t_proportional(m):
    result = m.normalize_cadence([3, 1])
    assert abs(result[0] - 0.75) < 1e-9
    assert abs(result[1] - 0.25) < 1e-9


def _t_empty_is_empty_list(m):
    assert m.normalize_cadence([]) == []


def _t_rejects_nonpositive(m):
    try:
        m.normalize_cadence([3, -1])
    except ValueError:
        return
    raise AssertionError("expected ValueError for a non-positive beat")


TESTS = [_t_sums_to_one, _t_proportional, _t_empty_is_empty_list, _t_rejects_nonpositive]
