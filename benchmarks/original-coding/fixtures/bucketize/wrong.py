def bucketize(values, edges):
    if len(edges) < 2:
        raise ValueError("need at least two edges")
    counts = [0] * (len(edges) - 1)
    for value in values:
        for i in range(len(edges) - 1):
            # Inclusive upper bound double-counts values that sit on a boundary.
            if edges[i] <= value <= edges[i + 1]:
                counts[i] += 1
                break
    return counts
