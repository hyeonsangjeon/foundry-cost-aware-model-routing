def _t_clamps_low(m):
    assert m.clamp_series([-5, 0, 3], 0, 10) == [0, 0, 3]


def _t_clamps_high(m):
    assert m.clamp_series([3, 10, 15], 0, 10) == [3, 10, 10]


def _t_passthrough(m):
    assert m.clamp_series([2, 4, 6], 0, 10) == [2, 4, 6]


def _t_both_bounds(m):
    assert m.clamp_series([-5, 50], 0, 10) == [0, 10]


def _t_validates(m):
    try:
        m.clamp_series([1], 10, 0)
    except ValueError:
        return
    raise AssertionError("expected ValueError when lo exceeds hi")


TESTS = [_t_clamps_low, _t_clamps_high, _t_passthrough, _t_both_bounds, _t_validates]
