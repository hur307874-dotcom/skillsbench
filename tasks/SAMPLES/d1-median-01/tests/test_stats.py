from stats import median


def test_odd():
    assert median([1, 3, 5]) == 3


def test_even_two():
    assert median([1, 3]) == 2.0


def test_even_unsorted():
    assert median([4, 1, 2, 3]) == 2.5
