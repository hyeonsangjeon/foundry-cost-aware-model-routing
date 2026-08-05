def clamp_reading(value, lo, hi):
    # Never validates the bounds or rejects bools.
    return max(lo, min(value, hi))
