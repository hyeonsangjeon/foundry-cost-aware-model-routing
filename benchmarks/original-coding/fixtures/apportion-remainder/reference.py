def apportion(total, buckets):
    if buckets <= 0:
        raise ValueError("buckets must be positive")
    if total < 0:
        raise ValueError("total must be non-negative")
    base, extra = divmod(total, buckets)
    return [base + (1 if i < extra else 0) for i in range(buckets)]
