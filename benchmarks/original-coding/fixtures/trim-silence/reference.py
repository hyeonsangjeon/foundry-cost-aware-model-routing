def trim_silence(frames):
    start = 0
    end = len(frames)
    while start < end and frames[start] == 0:
        start += 1
    while end > start and frames[end - 1] == 0:
        end -= 1
    return frames[start:end]
