def merge_rosters(a, b):
    i = j = 0
    out = []
    while i < len(a) and j < len(b):
        if a[i] < b[j]:
            out.append(a[i])
            i += 1
        elif b[j] < a[i]:
            out.append(b[j])
            j += 1
        else:
            # Only cross-stream ties are de-duplicated here...
            out.append(a[i])
            i += 1
            j += 1
    # ...and these tail copies never check for repeats at all.
    out.extend(a[i:])
    out.extend(b[j:])
    return out
