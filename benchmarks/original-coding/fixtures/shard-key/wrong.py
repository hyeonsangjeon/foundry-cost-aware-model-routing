def shard_key(token, width):
    # Forgets to upper-case the selected characters.
    return token[::width]
