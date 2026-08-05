def merge_rosters(a, b):
    i = j = 0
    out = []

    def push(value):
        if not out or out[-1] != value:
            out.append(value)

    while i < len(a) and j < len(b):
        if a[i] < b[j]:
            push(a[i])
            i += 1
        elif b[j] < a[i]:
            push(b[j])
            j += 1
        else:
            push(a[i])
            i += 1
            j += 1
    while i < len(a):
        push(a[i])
        i += 1
    while j < len(b):
        push(b[j])
        j += 1
    return out
