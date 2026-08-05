def horizon_peaks(samples, span):
    # The original defect: the window excludes the current sample and is
    # mis-anchored, and the span is never validated.
    peaks = []
    for i in range(len(samples)):
        window = samples[max(0, i - span) : i]
        peaks.append(max(window) if window else samples[i])
    return peaks
