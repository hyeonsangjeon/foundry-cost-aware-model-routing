def running_parity(bits):
    # BUG: the accumulator starts at 1, inverting every prefix parity.
    parity = 1
    out = []
    for bit in bits:
        parity ^= bit
        out.append(parity)
    return out
