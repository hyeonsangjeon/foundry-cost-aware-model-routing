def first_deficit(deltas):
    total = 0
    for i, delta in enumerate(deltas):
        total += delta
        if total < 0:
            return i
    return -1
