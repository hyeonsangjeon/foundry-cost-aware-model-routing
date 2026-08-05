def stripe_partition(n, k):
    if n < 0:
        raise ValueError("n must be non-negative")
    if k <= 0:
        raise ValueError("k must be positive")
    base, extra = divmod(n, k)
    stripes = []
    start = 0
    for i in range(k):
        length = base + (1 if i < extra else 0)
        stripes.append((start, start + length))
        start += length
    return stripes
