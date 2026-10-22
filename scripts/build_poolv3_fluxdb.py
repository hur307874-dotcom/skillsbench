"""pool-v3 C 族 fluxdb 构建（gold/wrong/p2p/meta/INTENT）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_poolv3 import make_patch, scaffold  # noqa: E402

GOLD_FLUXDB = '''"""fluxdb —— 内存 KV 存储（规范实现：gold）。"""

import copy


class MissingKey(Exception):
    """缺键专用异常（规范要求：不是 KeyError）"""


class FluxDB:
    def __init__(self):
        self._data: dict = {}
        self._trash: dict = {}

    @staticmethod
    def _norm(key):
        return str(key).lower()

    def put(self, key, value):
        self._data[self._norm(key)] = value

    def get(self, key):
        k = self._norm(key)
        if k not in self._data:
            raise MissingKey(k)
        return copy.deepcopy(self._data[k])

    def delete(self, key, hard=False):
        k = self._norm(key)
        if k in self._data:
            if hard:
                del self._data[k]
            else:
                self._trash[k] = self._data.pop(k)

    def revive(self, key):
        k = self._norm(key)
        if k not in self._trash:
            raise MissingKey(k)
        self._data[k] = self._trash.pop(k)

    def keys(self):
        return list(self._data.keys())
'''


def build_fluxdb() -> None:
    tdir = ROOT / "tasks/pool-v3/conv-fluxdb-semantics"
    scaffold(tdir)
    fixture = tdir / "fixture/fluxdb/__init__.py"
    make_patch(fixture, GOLD_FLUXDB, tdir / "solution/sites/site-01.patch")

    # wrong_01：只把 KeyError 改名成 MissingKey（继承 KeyError、其余语义全漏）
    w = fixture.read_text(encoding="utf-8").replace(
        "class FluxDB:",
        "class MissingKey(KeyError):\n    pass\n\n\nclass FluxDB:").replace(
        "raise KeyError(key)", "raise MissingKey(key)")
    wf = tdir / "wrong/wrong_01/fluxdb/__init__.py"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(w, encoding="utf-8")

    (tdir / "tests/p2p/test_stable.py").write_text(
        "import unittest\nfrom unittest import TestCase  # noqa: F401\n"
        "import fluxdb as fx  # noqa: F401\n\n\n"
        "class StableTests(TestCase):\n"
        "    def test_put_get(self):\n"
        "        db = fx.FluxDB()\n"
        "        db.put('a', 1)\n"
        "        self.assertEqual(db.get('a'), 1)\n\n\n"
        "if __name__ == '__main__':\n    unittest.main()\n",
        encoding="utf-8")

    (tdir / "meta.yaml").write_text(
        "task_id: conv-fluxdb-semantics\n"
        "track: code\n"
        "horizon_minutes: 12\n"
        "difficulty: D3\n"
        "targets_fids: [F17, F13]\n"
        "sites_required: 1\n"
        "forbidden_edits: [tests/, _tests/]\n"
        "prompt: |\n"
        "  fluxdb 是我们的内存 KV 库。多个下游团队踩了语义不一致的坑：\n"
        "  拿到的值被外面改坏、删掉的键找不回来、异常类型和文档对不上、\n"
        "  大小写键重复。请按团队语义规范统一修正（规范细节见团队文档）。\n"
        "baseline:\n"
        '  role: "pool-v3 C 族（冷门语义 API 知识缺口）"\n',
        encoding="utf-8")

    (tdir / "INTENT.md").write_text(
        "# 出题意图（conv-fluxdb-semantics，pool-v3 C 族）\n\n"
        "- 规范（只在配套 Skill 文档）：get 深拷贝；delete 默认软删 + revive；\n"
        "  缺键抛 MissingKey（独立类型，不是 KeyError 也不是其子类）；\n"
        "  键统一小写归一。\n"
        "- 裸考能猜\"返回拷贝更安全\"，但 MissingKey 命名/软删默认/小写归一\n"
        "  猜不中 → 约定分大丢。\n"
        "- 错解 wrong_01：只把 KeyError 改名成 MissingKey（继承 KeyError、\n"
        "  其余语义全漏）。\n",
        encoding="utf-8")
    print("✓ fluxdb 构建完成")


if __name__ == "__main__":
    build_fluxdb()
