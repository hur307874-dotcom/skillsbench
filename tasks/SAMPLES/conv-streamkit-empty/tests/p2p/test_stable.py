import unittest
from unittest import TestCase  # noqa: F401

import streamkit as sk  # noqa: F401


class StableTests(TestCase):
    def test_window_full_cover(self):
        self.assertEqual(list(sk.window([1, 2, 3], 3)), [(1, 2, 3)])

    def test_collect_into_set(self):
        self.assertEqual(sk.collect(iter([1, 1, 2]), into=set), {1, 2})


if __name__ == '__main__':
    unittest.main()
