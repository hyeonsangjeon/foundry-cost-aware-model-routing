def weekday_label(index):
    # Behaviour-preserving, but keeps the seven-way ladder the refactor removes.
    if index == 0:
        return "Mon"
    elif index == 1:
        return "Tue"
    elif index == 2:
        return "Wed"
    elif index == 3:
        return "Thu"
    elif index == 4:
        return "Fri"
    elif index == 5:
        return "Sat"
    elif index == 6:
        return "Sun"
    else:
        raise ValueError("index out of range")
