def bucketize(values, edges):
    if len(edges) < 2:
        raise ValueError("need at least two edges")
    for a, b in zip(edges, edges[1:]):
        if b <= a:
            raise ValueError("edges must be strictly ascending")
    counts = [0] * (len(edges) - 1)
    for value in values:
        for i in range(len(edges) - 1):
            if edges[i] <= value < edges[i + 1]:
                counts[i] += 1
                break
    return counts
