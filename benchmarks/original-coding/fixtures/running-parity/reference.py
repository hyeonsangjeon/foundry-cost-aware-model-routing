def running_parity(bits):
    parity = 0
    out = []
    for bit in bits:
        parity ^= bit
        out.append(parity)
    return out
