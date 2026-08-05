def align_frames(left, right):
    for stream in (left, right):
        for (t0, _), (t1, _) in zip(stream, stream[1:]):
            if t1 <= t0:
                raise ValueError("timestamps must be strictly increasing")
    i = j = 0
    aligned = []
    while i < len(left) and j < len(right):
        lt, lv = left[i]
        rt, rv = right[j]
        if lt == rt:
            aligned.append((lt, lv, rv))
            i += 1
            j += 1
        elif lt < rt:
            i += 1
        else:
            j += 1
    return aligned
