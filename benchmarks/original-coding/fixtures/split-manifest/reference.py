def split_manifest(items, capacity):
    if isinstance(capacity, bool) or not isinstance(capacity, int):
        raise TypeError("capacity must be an int")
    if capacity <= 0:
        raise ValueError("capacity must be positive")
    return [list(items[i : i + capacity]) for i in range(0, len(items), capacity)]
