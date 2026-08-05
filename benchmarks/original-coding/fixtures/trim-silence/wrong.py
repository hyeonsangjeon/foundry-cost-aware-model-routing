def trim_silence(frames):
    # Strips interior zeros too, instead of only the leading/trailing runs.
    return [frame for frame in frames if frame != 0]
