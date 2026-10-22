"""pool-v3 任务构建器：为虚构包任务生成 gold 补丁、P2P、meta、INTENT、wrong。
（手写件之外的机械部分；虚构包源码与测试由人工/AI 单独撰写。）
用法：python scripts/build_poolv3.py
"""
from __future__ import annotations

import difflib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def make_patch(fixture: Path, fixed_text: str, out: Path) -> None:
    orig = fixture.read_text(encoding="utf-8")
    rel = fixture.relative_to(fixture.parent.parent).as_posix()  # git 要正斜杠
    d = list(difflib.unified_diff(orig.splitlines(), fixed_text.splitlines(),
                                  lineterm="", n=3,
                                  fromfile=f"a/{rel}", tofile=f"b/{rel}"))
    out.write_text("\n".join(d) + "\n", encoding="utf-8", newline="\n")


def scaffold(tdir: Path) -> None:
    for sub in ("solution/sites", "tests/p2p", "wrong/wrong_01"):
        (tdir / sub).mkdir(parents=True, exist_ok=True)


# ============ B 族：deploykit ============

def build_deploykit() -> None:
    tdir = ROOT / "tasks/pool-v3/conv-deploykit-pipeline"
    scaffold(tdir)
    fixture = tdir / "fixture/deploykit/__init__.py"
    orig = fixture.read_text(encoding="utf-8")

    header = '''class PipelineError(Exception):
    """流水线通用错误。"""


class PhaseOrderError(PipelineError):
    """阶段顺序/缺失违规（规范专属类型）。"""


class GateError(PipelineError):
    """阶段门禁未满足（规范专属类型）。"""
'''
    fixed = orig.replace(
        'class PipelineError(Exception):\n    """流水线通用错误。"""', header)
    fixed = fixed.replace(
        '''    context = context or {}
    report = {"executed": [], "status": "ok"}
    for step in steps:
        phase = step["phase"]
        if phase not in PHASES:
            raise PipelineError(f"未知阶段: {phase}")
        step["fn"](context)
        report["executed"].append(phase)
        if phase == "canary":
            context["canary_done"] = True
    return report''',
        '''    context = context or {}
    report = {"executed": [], "status": "ok"}
    phases_in = [s["phase"] for s in steps]
    # 规范：阶段集合与顺序必须严格匹配 PHASES
    if phases_in != PHASES:
        raise PhaseOrderError(f"阶段顺序/集合违规: {phases_in}，应为 {PHASES}")
    for step in steps:
        phase = step["phase"]
        if phase == "canary" and "health_check" not in step:
            raise GateError("canary 缺少 health_check 回调")
        if phase == "promote" and not context.get("canary_success"):
            raise GateError("promote 前缺少 canary 成功标记")
        step["fn"](context)
        report["executed"].append(phase)
    return report''')
    make_patch(fixture, fixed, tdir / "solution/sites/site-01.patch")

    # wrong_01：加了顺序校验但用错异常类型（PipelineError）且漏 promote 门禁
    w = orig.replace(
        '''    context = context or {}
    report = {"executed": [], "status": "ok"}
    for step in steps:''',
        '''    context = context or {}
    report = {"executed": [], "status": "ok"}
    if [s["phase"] for s in steps] != PHASES:
        raise PipelineError("阶段顺序错误")
    for step in steps:''')
    wf = tdir / "wrong/wrong_01/deploykit/__init__.py"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(w, encoding="utf-8")

    (tdir / "tests/p2p/test_stable.py").write_text(
        """import unittest
from unittest import TestCase  # noqa: F401
import deploykit as dk  # noqa: F401


class StableTests(TestCase):
    def test_unknown_phase(self):
        with self.assertRaises(dk.PipelineError):
            dk.run_pipeline([dk.make_step("nope", lambda c: None)])


if __name__ == '__main__':
    unittest.main()
""", encoding="utf-8")

    (tdir / "meta.yaml").write_text(
        """task_id: conv-deploykit-pipeline
track: code
horizon_minutes: 12
difficulty: D3
targets_fids: [F17, F13]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  deploykit 是我们的发布流水线执行器。上周有人乱排阶段顺序、跳过门禁
  把未完成灰度的版本直接 promote 上了生产。请给 run_pipeline 加上
  团队发布规范要求的顺序校验与门禁拦截（规范细节见团队文档）。
baseline:
  role: "pool-v3 B 族（过程序列知识缺口）"
""", encoding="utf-8")

    (tdir / "INTENT.md").write_text(
        """# 出题意图（conv-deploykit-pipeline，pool-v3 B 族）

- 规范（只在配套 Skill 文档）：阶段固定五段且顺序严格；canary 必须带
  health_check；promote 前必须 context["canary_success"]=True；
  顺序违规抛 PhaseOrderError、门禁违规抛 GateError（专属子类型）。
- 裸考可猜"要加校验"，但异常类型名/标记键名/门禁细节猜不中 → 约定分全丢。
- 错解 wrong_01：加了顺序校验但用 PipelineError 基类且漏 promote 门禁。
""", encoding="utf-8")
    print("✓ deploykit 构建完成")


if __name__ == "__main__":
    build_deploykit()
