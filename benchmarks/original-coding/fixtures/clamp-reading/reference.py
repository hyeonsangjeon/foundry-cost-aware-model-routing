def clamp_reading(value, lo, hi):
    for name, candidate in (("value", value), ("lo", lo), ("hi", hi)):
        if isinstance(candidate, bool):
            raise TypeError(f"{name} must not be a bool")
    if lo > hi:
        raise ValueError("lo must not exceed hi")
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value
