def span_gaps(marks):
    # Wrong sign and no ascending validation.
    return [marks[i] - marks[i + 1] for i in range(len(marks) - 1)]
