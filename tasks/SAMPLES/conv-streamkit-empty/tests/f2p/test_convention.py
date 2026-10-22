import unittest
from unittest import TestCase  # noqa: F401

import streamkit as sk  # noqa: F401


class ConventionTests(TestCase):
    """约定符合度（规范只在内部文档：SK1 空输入占位 / SK2 错误延迟 / SK3 校验入口）。"""

    def test_empty_window_yields_single_blank(self):
        self.assertEqual(list(sk.window([], 2)), [sk.BLANK])

    def test_empty_collect_returns_blank_container(self):
        self.assertEqual(sk.collect(iter([])), [sk.BLANK])

    def test_blank_repr(self):
        self.assertEqual(repr(sk.BLANK), "<blank>")

    def test_none_collect_returns_broken_not_raise(self):
        self.assertIs(sk.collect(None), sk.BROKEN)
        self.assertEqual(list(sk.BROKEN), [])

    def test_errors_deferred_to_raise_pending(self):
        sk.collect(None)
        self.assertTrue(sk.pending_errors())
        with self.assertRaises(sk.StreamFault):
            sk.raise_pending()
        self.assertEqual(sk.pending_errors(), [])

    def test_shared_audit_entry(self):
        self.assertTrue(hasattr(sk, "_audit_inbound"),
                        "缺少统一校验入口 _audit_inbound")


if __name__ == '__main__':
    unittest.main()
