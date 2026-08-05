def _t_even_count(m):
    assert m.even_parity([1, 1]) == 0


def _t_odd_count(m):
    assert m.even_parity([1, 1, 1]) == 1


def _t_empty(m):
    assert m.even_parity([]) == 0


def _t_validates(m):
    try:
        m.even_parity([2])
    except ValueError:
        return
    raise AssertionError("expected ValueError for a non-binary input")


TESTS = [_t_even_count, _t_odd_count, _t_empty, _t_validates]
