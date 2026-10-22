def median(xs):
    """Return the median of a non-empty list of numbers."""
    s = sorted(xs)
    return s[len(s) // 2]
