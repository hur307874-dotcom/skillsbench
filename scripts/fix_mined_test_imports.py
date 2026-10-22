"""mined 池 f2p 测试结构修复 v2（2026-10-09）。

两个结构性缺陷（挖掘提取时丢的）：
1. 模块级 import 缺失（v1 已修：补 itertools/operator/functools/mi 星导入）；
2. **TestCase 类包装缺失**——提取的测试方法保留了类内缩进（4 空格），
   但没有 `class TestX(TestCase):` 外壳 → IndentationError: unexpected indent。

v2 修复：在 HEADER 后、第一个缩进的 `def test_` 前插入 class 声明（幂等）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER = (
    "import unittest\n"
    "from unittest import TestCase  # noqa: F401\n"
    "from itertools import *  # noqa: F401,F403\n"
    "from operator import *  # noqa: F401,F403\n"
    "from functools import *  # noqa: F401,F403\n"
    "import more_itertools as mi  # noqa: F401\n"
    "from more_itertools import *  # noqa: F401,F403\n"
)
CLASS_DECL = "\n\nclass TestMined(TestCase):\n"
_DROP = {"import unittest",
         "from unittest import TestCase  # noqa: F401",
         "import more_itertools as mi  # noqa: F401",
         "from itertools import *  # noqa: F401,F403",
         "from operator import *  # noqa: F401,F403",
         "from functools import *  # noqa: F401,F403",
         "from more_itertools import *  # noqa: F401,F403"}


def fix(tf: Path) -> str:
    text = tf.read_text(encoding="utf-8")
    if re.search(r"^class \w+\(TestCase\)", text, re.M) and "from itertools import *" in text:
        return "ok"
    lines = text.splitlines(keepends=True)
    body = [ln for ln in lines if ln.strip() not in _DROP]
    out = HEADER
    inserted = False
    for ln in body:
        if not inserted and re.match(r"^\s+def test_", ln):
            out += CLASS_DECL
            inserted = True
        out += ln
    if not inserted:  # 没有类内缩进方法（模块级测试函数）——不需要 class
        out = HEADER + "".join(body)
    tf.write_text(out, encoding="utf-8", newline="\n")
    return "fixed"


def main() -> int:
    stats = {"fixed": 0, "ok": 0}
    for tf in (ROOT / "tasks" / "pool-v2-mined").glob("*/tests/f2p/*.py"):
        stats[fix(tf)] += 1
    print(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
