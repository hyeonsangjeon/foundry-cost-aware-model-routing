def split_manifest(items, capacity):
    # Naive: never validates capacity, so negative/float/bool inputs are not
    # rejected with the required exception types.
    chunks = []
    for i in range(0, len(items), capacity):
        chunks.append(items[i : i + capacity])
    return chunks
