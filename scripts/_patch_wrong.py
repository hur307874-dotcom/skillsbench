"""一次性：conv-streamkit-empty 的 gold 补丁与 wrong_01 重写（v2 知识外置版）。"""
import difflib
import shutil
from pathlib import Path

T = Path("tasks/pool-v3/conv-streamkit-empty")
fixture = T / "fixture/streamkit/__init__.py"
orig = fixture.read_text(encoding="utf-8")

SENTINEL = (
    'class EmptyStream:\n'
    '    """空流哨兵（单例）。所有公开 API 的空输入必须返回它。"""\n'
    '\n'
    '    _instance = None\n'
    '\n'
    '    def __new__(cls):\n'
    '        if cls._instance is None:\n'
    '            cls._instance = super().__new__(cls)\n'
    '        return cls._instance\n'
    '\n'
    '    def __iter__(self):\n'
    '        return iter(())\n'
    '\n'
    '    def __repr__(self):\n'
    '        return "EmptyStream"\n'
    '\n'
    '\n'
    'def _validate_stream(source, name="source"):\n'
    '    """公开 API 入参校验：None → ValueError；非可迭代 → TypeError。"""\n'
    '    if source is None:\n'
    '        raise ValueError(f"{name} 不能为 None")\n'
    '    if not hasattr(source, "__iter__"):\n'
    '        raise TypeError(f"{name} 必须是可迭代对象")\n'
    '\n'
    '\n'
)

fixed = orig.replace("def chain(*sources):", SENTINEL + "def chain(*sources):", 1)
fixed = fixed.replace("        return []  # 空输入行为待规范",
                      "        return EmptyStream()")
fixed = fixed.replace(
    "    items = [x for x in stream]\n"
    "    if not items:\n"
    "        return into()  # 空输入行为待规范",
    "    _validate_stream(stream)\n"
    "    items = [x for x in stream]\n"
    "    if not items:\n"
    "        return EmptyStream()")
d = list(difflib.unified_diff(orig.splitlines(), fixed.splitlines(), lineterm="", n=3,
                              fromfile="a/streamkit/__init__.py",
                              tofile="b/streamkit/__init__.py"))
(T / "solution/sites/site-01.patch").write_text(
    "\n".join(d) + "\n", encoding="utf-8", newline="\n")
print("gold 补丁重写（新增哨兵+校验+两处调用）")

wf = T / "wrong/wrong_01/streamkit/__init__.py"
shutil.copy(fixture, wf)
w = orig.replace("        return []  # 空输入行为待规范", "        return EMPTY_STREAM")
w = w.replace(
    "    items = [x for x in stream]\n"
    "    if not items:\n"
    "        return into()  # 空输入行为待规范",
    "    items = [x for x in stream]\n"
    "    if not items:\n"
    "        return EMPTY_STREAM")
w = w.replace("def chain(*sources):",
              "class _EmptyC:\n"
              "    def __iter__(self):\n"
              "        return iter(())\n"
              "\n\n"
              "EMPTY_STREAM = _EmptyC()\n"
              "\n\n"
              "def chain(*sources):", 1)
wf.write_text(w, encoding="utf-8")
print("wrong_01 重写（名错+非单例+缺共享校验）")
