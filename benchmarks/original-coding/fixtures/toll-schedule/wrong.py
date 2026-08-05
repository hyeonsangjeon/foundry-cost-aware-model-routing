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
            # Sums overlapping rates instead of taking the max active rate.
            total += sum(rate for start, end, rate in segments if start <= t < end)
        totals.append(total)
    return totals
