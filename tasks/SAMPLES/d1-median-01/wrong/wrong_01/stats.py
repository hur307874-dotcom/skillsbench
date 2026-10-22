def median(xs):
    """Return the median of a non-empty list of numbers."""
    s = sorted(xs)
    n = len(s)
    return (s[n // 2 - 1] + s[n // 2]) / 2
