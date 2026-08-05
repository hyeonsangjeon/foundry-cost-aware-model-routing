def collect_active(records):
    # Behaviour-preserving, but keeps the manual loop the refactor should remove.
    result = []
    for record in records:
        if record["state"] == "on":
            result.append(record["id"])
    return result
