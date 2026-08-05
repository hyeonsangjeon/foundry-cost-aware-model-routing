def span_gaps(marks):
    for a, b in zip(marks, marks[1:]):
        if b <= a:
            raise ValueError("marks must be strictly ascending")
    return [b - a for a, b in zip(marks, marks[1:])]
