def dedupe_stable(seq):
    # Behaviour-preserving, but keeps the quadratic nested-loop scan.
    out = []
    for item in seq:
        found = False
        for kept in out:
            if kept == item:
                found = True
        if not found:
            out.append(item)
    return out
