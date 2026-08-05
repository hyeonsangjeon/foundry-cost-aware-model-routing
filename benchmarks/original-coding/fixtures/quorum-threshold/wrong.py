from collections import Counter


def quorum_threshold(votes, ratio):
    if ratio <= 0 or ratio > 1:
        raise ValueError("ratio must be in (0, 1]")
    counts = Counter(votes)
    need = ratio * len(votes)
    # Uses >= instead of a strict majority threshold.
    return sorted(candidate for candidate, seen in counts.items() if seen >= need)
