import unittest
from unittest import TestCase  # noqa: F401

import streamkit as sk  # noqa: F401


class BehaviorTests(TestCase):
    """客观缺陷与用户可感知行为（不需要规范知识）。"""

    def test_window_basic(self):
        self.assertEqual(list(sk.window([1, 2, 3, 4], 2)), [(1, 2), (2, 3), (3, 4)])

    def test_chain_basic(self):
        self.assertEqual(list(sk.chain([1, 2], (3,), [])), [1, 2, 3])

    def test_collect_basic(self):
        self.assertEqual(sk.collect(iter([1, 2, 3])), [1, 2, 3])

    def test_take_exact_count(self):
        self.assertEqual(list(sk.take(iter([1, 2, 3, 4, 5]), 3)), [1, 2, 3])

    def test_take_zero(self):
        self.assertEqual(list(sk.take(iter([1, 2, 3]), 0)), [])


if __name__ == '__main__':
    unittest.main()
