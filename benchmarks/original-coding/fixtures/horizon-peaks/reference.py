def horizon_peaks(samples, span):
    if span <= 0:
        raise ValueError("span must be positive")
    peaks = []
    for i in range(len(samples)):
        start = max(0, i - span + 1)
        peaks.append(max(samples[start : i + 1]))
    return peaks
