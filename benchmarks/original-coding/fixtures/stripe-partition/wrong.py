def stripe_partition(n, k):
    if n < 0:
        raise ValueError("n must be non-negative")
    if k <= 0:
        raise ValueError("k must be positive")
    # Drops the remainder, so the stripes never cover the tail elements.
    base = n // k
    stripes = []
    start = 0
    for _ in range(k):
        stripes.append((start, start + base))
        start += base
    return stripes
