def toll_schedule(segments, queries):
    for start, end, rate in segments:
        if end < start or rate < 0:
            raise ValueError("invalid segment")
    totals = []
    for a, b in queries:
        if b < a:
            raise ValueError("invalid query window")
        total = 0
        for t in range(a, b):
            active = [rate for start, end, rate in segments if start <= t < end]
            total += max(active) if active else 0
        totals.append(total)
    return totals
