def align_frames(left, right):
    # Joins by position instead of by matching timestamp, and never validates.
    return [(lt, lv, rv) for (lt, lv), (rt, rv) in zip(left, right)]
