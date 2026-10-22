import unittest
from unittest import TestCase  # noqa: F401
from itertools import *  # noqa: F401,F403
from operator import *  # noqa: F401,F403
from functools import *  # noqa: F401,F403
import more_itertools as mi  # noqa: F401
from more_itertools import *  # noqa: F401,F403




class TestMined(TestCase):
    def test_true(self):
        """Iterable has ``n`` ``True`` elements"""
        self.assertTrue(mi.exactly_n([True, False, True], 2))
        self.assertTrue(mi.exactly_n([1, 1, 1, 0], 3))
        self.assertTrue(mi.exactly_n([False, False], 0))
        self.assertTrue(mi.exactly_n(range(100), 10, lambda x: x < 10))
        self.assertTrue(mi.exactly_n(repeat(True, 100), 100))
        self.assertTrue(mi.exactly_n(repeat(False, 100), 100, predicate=not_))


    def test_false(self):
        """Iterable does not have ``n`` ``True`` elements"""
        self.assertFalse(mi.exactly_n([True, False, False], 2))
        self.assertFalse(mi.exactly_n([True, True, False], 1))
        self.assertFalse(mi.exactly_n([False], 1))
        self.assertFalse(mi.exactly_n([True], -1))
        self.assertFalse(mi.exactly_n([True], -10))
        self.assertFalse(mi.exactly_n([], -1))
        self.assertFalse(mi.exactly_n([], -10))
        self.assertFalse(mi.exactly_n([True], 0))
        self.assertFalse(mi.exactly_n(repeat(True), 100))


    def test_empty(self):
        """Return ``True`` if the iterable is empty and ``n`` is 0"""
        self.assertTrue(mi.exactly_n([], 0))
        self.assertFalse(mi.exactly_n([], 1))




if __name__ == '__main__':
    unittest.main()
