def first_deficit(deltas):
    total = 0
    for i, delta in enumerate(deltas):
        # BUG: checks the total before folding in the current delta.
        if total < 0:
            return i
        total += delta
    return -1
