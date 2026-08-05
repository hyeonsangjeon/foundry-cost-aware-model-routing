def shard_key(token, width):
    if width <= 0:
        raise ValueError("width must be positive")
    return "".join(token[i] for i in range(0, len(token), width)).upper()
