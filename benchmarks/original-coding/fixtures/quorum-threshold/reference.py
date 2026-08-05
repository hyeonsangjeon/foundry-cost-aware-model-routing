from collections import Counter


def quorum_threshold(votes, ratio):
    if ratio <= 0 or ratio > 1:
        raise ValueError("ratio must be in (0, 1]")
    if not votes:
        return []
    counts = Counter(votes)
    need = ratio * len(votes)
    return sorted(candidate for candidate, seen in counts.items() if seen > need)
