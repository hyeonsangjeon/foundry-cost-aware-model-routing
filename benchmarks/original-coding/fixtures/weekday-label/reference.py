_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def weekday_label(index):
    if index < 0 or index >= len(_LABELS):
        raise ValueError("index out of range")
    return _LABELS[index]
