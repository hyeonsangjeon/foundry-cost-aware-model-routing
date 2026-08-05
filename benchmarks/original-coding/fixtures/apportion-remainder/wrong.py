def apportion(total, buckets):
    if buckets <= 0:
        raise ValueError("buckets must be positive")
    if total < 0:
        raise ValueError("total must be non-negative")
    # BUG: the remainder from the integer division is discarded.
    base = total // buckets
    return [base for _ in range(buckets)]
