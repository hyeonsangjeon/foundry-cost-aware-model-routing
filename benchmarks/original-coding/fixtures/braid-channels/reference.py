def braid_channels(pulses, stride):
    if stride <= 0:
        raise ValueError("stride must be positive")
    braided = []
    for residue in range(stride):
        braided.extend(pulses[residue::stride])
    return braided
