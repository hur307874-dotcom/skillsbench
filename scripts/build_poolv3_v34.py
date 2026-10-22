"""pool-v3 正式版 v3.4 总构建（2026-10-03；10-04 适配 docker 沙箱）。

铁律落地：
- v3.3 约定反直觉（与行业通行做法反向，模型猜不中）；
- v3.4 命名不可自然猜中（BLANK/BROKEN/_audit_inbound/SequenceFault/held/ZILCH/clobber...）；
- 隔离改由 docker 沙箱提供（pi-docker 驱动：容器内只挂 /repo 与 /skill）——
  任务回到标准布局（tests/solution/wrong/INTENT 留在工作区任务目录内）；
- 约定 Skill 文档仍放安全仓 D:/ai_project/skillbench-v3-secure/skills/
  （纵深防御：文档内容同时是"答案"，不放工作区防宿主误跑 pi 驱动时泄题）；
- 旧版（v3.3 前）任务与约定文档归档到安全仓 archive/，清出工作区搜盘半径。

产物：
  工作区  tasks/pool-v3/<task>/{fixture/,meta.yaml,tests/,solution/,wrong/,INTENT.md}
  安全仓  skills/{streamkit-convention,deploykit-spec,fluxdb-semantics,placebo-cooking}/
  工作区  matrix/poolv3d-<fam>-<arm>.yaml × 9（臂间隔离批次）

用法：python scripts/build_poolv3_v34.py
"""
from __future__ import annotations

import difflib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEC = Path("D:/ai_project/skillbench-v3-secure")


def w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def make_patch(fixture_file: Path, fixed_text: str, out: Path) -> None:
    orig = fixture_file.read_text(encoding="utf-8")
    rel = fixture_file.relative_to(fixture_file.parent.parent).as_posix()
    d = list(difflib.unified_diff(orig.splitlines(), fixed_text.splitlines(),
                                  lineterm="", n=3,
                                  fromfile=f"a/{rel}", tofile=f"b/{rel}"))
    w(out, "\n".join(d) + "\n")


def archive_old() -> None:
    """旧版处理（docker 沙箱时代的务实版）。

    安全沙箱拦截跨目录 move/rename（回收站不可用），且旧目录有句柄锁。
    但 pi-docker 驱动的 agent 只看得见容器内 /repo——工作区旧文件物理不可达，
    因此旧 tasks/skills 原地保留即可（2026-10-04 与用户的确认一致）：
    本函数只做 placebo 文档向安全仓的复制（预设引用安全仓路径）。
    """
    import time as _time
    pc = ROOT / "skills/placebo-cooking"
    if pc.exists():
        dst = SEC / "skills/placebo-cooking"
        if dst.exists():
            aside = dst.with_name(f"{dst.name}-prev{int(_time.time())}")
            shutil.move(str(dst), str(aside))
        shutil.copytree(pc, dst)
        print("  placebo-cooking 已复制到安全仓")
    print("  （旧 tasks/pool-v3 与旧 skills 原地保留——容器隔离覆盖，无需迁移）")


# =====================================================================
# 族 1：streamkit（空输入占位 + 错误延迟 + 统一校验入口）
# =====================================================================

SK_FIXTURE = '''"""streamkit —— 轻量流处理工具库。"""


def chain(*sources):
    """顺序拼接多个流。"""
    for s in sources:
        if s is None:
            raise ValueError("source 不能为 None")
        if not hasattr(s, "__iter__"):
            raise TypeError("source 必须是可迭代对象")
    for s in sources:
        yield from s


def window(seq, n):
    """滑动窗口，产出长度 n 的元组。"""
    if seq is None:
        raise ValueError("seq 不能为 None")
    if not hasattr(seq, "__iter__"):
        raise TypeError("seq 必须是可迭代对象")
    if n < 1:
        raise ValueError("n 必须 >= 1")
    items = list(seq)
    if not items:
        return []
    return (tuple(items[i:i + n]) for i in range(len(items) - n + 1))


def collect(stream, into=list):
    """把流收集成容器。"""
    items = [x for x in stream]
    if not items:
        return into()
    return into(items)


def take(stream, k):
    """取前 k 个元素。"""
    for i, x in enumerate(stream):
        if i > k:
            break
        yield x
'''

SK_GOLD = '''"""streamkit —— 轻量流处理工具库。"""


class _Blank:
    """空输入占位元素（规范 SK1）。"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "<blank>"


BLANK = _Blank()


class _Broken:
    """校验失败占位流（规范 SK2）：可迭代，产出零元素。"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __iter__(self):
        return iter(())

    def __repr__(self):
        return "<broken>"


BROKEN = _Broken()

_errors = []


class StreamFault(Exception):
    """延迟抛出的校验错误汇总（规范 SK2）。"""


def pending_errors():
    """累计校验错误的副本。"""
    return list(_errors)


def raise_pending():
    """有累计错误时抛 StreamFault 并清空队列。"""
    if _errors:
        msgs = list(_errors)
        del _errors[:]
        raise StreamFault("; ".join(msgs))


def _audit_inbound(source, name="source"):
    """规范 SK3：公开 API 唯一校验入口。失败不抛——记队列、返回 False。"""
    if source is None:
        _errors.append(f"{name} 为 None")
        return False
    if not hasattr(source, "__iter__"):
        _errors.append(f"{name} 不可迭代")
        return False
    return True


def chain(*sources):
    """顺序拼接多个流。"""
    for i, s in enumerate(sources):
        if not _audit_inbound(s, f"sources[{i}]"):
            return iter(BROKEN)
    for s in sources:
        yield from s


def window(seq, n):
    """滑动窗口，产出长度 n 的元组。"""
    if not _audit_inbound(seq, "seq"):
        return BROKEN
    if n < 1:
        _errors.append("n 必须 >= 1")
        return BROKEN
    items = list(seq)
    if not items:
        return iter([BLANK])
    return (tuple(items[i:i + n]) for i in range(len(items) - n + 1))


def collect(stream, into=list):
    """把流收集成容器。"""
    if not _audit_inbound(stream):
        return BROKEN
    items = [x for x in stream]
    if not items:
        return into([BLANK])
    return into(items)


def take(stream, k):
    """取前 k 个元素。"""
    if not _audit_inbound(stream):
        return
    for i, x in enumerate(stream):
        if i >= k:
            break
        yield x
'''

SK_WRONG = '''"""streamkit —— 轻量流处理工具库。"""


class EmptyStream:
    """空流哨兵（单例）。"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __iter__(self):
        return iter(())

    def __repr__(self):
        return "EmptyStream"


def _validate_stream(source, name="source"):
    if source is None:
        raise ValueError(f"{name} 不能为 None")
    if not hasattr(source, "__iter__"):
        raise TypeError(f"{name} 必须是可迭代对象")


def chain(*sources):
    """顺序拼接多个流。"""
    for s in sources:
        _validate_stream(s)
    for s in sources:
        yield from s


def window(seq, n):
    """滑动窗口，产出长度 n 的元组。"""
    _validate_stream(seq, "seq")
    if n < 1:
        raise ValueError("n 必须 >= 1")
    items = list(seq)
    if not items:
        return iter([EmptyStream()])
    return (tuple(items[i:i + n]) for i in range(len(items) - n + 1))


def collect(stream, into=list):
    """把流收集成容器。"""
    _validate_stream(stream)
    items = [x for x in stream]
    if not items:
        return into([EmptyStream()])
    return into(items)


def take(stream, k):
    """取前 k 个元素。"""
    for i, x in enumerate(stream):
        if i >= k:
            break
        yield x
'''

SK_TEST_BEHAVIOR = '''import unittest
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
'''

SK_TEST_CONVENTION = '''import unittest
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
'''

SK_TEST_STABLE = '''import unittest
from unittest import TestCase  # noqa: F401

import streamkit as sk  # noqa: F401


class StableTests(TestCase):
    def test_window_full_cover(self):
        self.assertEqual(list(sk.window([1, 2, 3], 3)), [(1, 2, 3)])

    def test_collect_into_set(self):
        self.assertEqual(sk.collect(iter([1, 1, 2]), into=set), {1, 2})


if __name__ == '__main__':
    unittest.main()
'''

SK_META = '''task_id: conv-streamkit-empty
track: code
horizon_minutes: 10
difficulty: D2
targets_fids: [F17, F13]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  streamkit 是我们内部的流处理工具库。用户反馈 take 总是多给元素：
  take(xs, 3) 实际拿到 4 个。另外空输入与异常输入（None 等）的
  处理要按团队规范统一（规范细节见团队文档）。
baseline:
  role: "pool-v3 正式版 v3.4（反直觉约定）"
'''

SK_INTENT = '''# 出题意图（conv-streamkit-empty，pool-v3 v3.4）

- 行为分（无需规范）：take 的 off-by-one（i > k 应为 i >= k），用户报告可直接定位。
- 约定分（只在 Skill 文档，反直觉）：
  - SK1 空输入**不返回空**，返回单元素流 [BLANK]（占位元素单例）；
  - SK2 校验失败**绝不立即抛**——返回 BROKEN 单例、错误进队列，
    只在 raise_pending() 时抛 StreamFault；
  - SK3 校验唯一入口 `_audit_inbound`。
- 裸考天花板：行业通行做法（空哨兵 EmptyStream + 立即 ValueError）正是 wrong_01，
  行为分拿满、约定分全丢。
'''

SK_SKILL = '''# streamkit 团队规范（内部库行为约定，v3.4）

适用：streamkit（内部流处理工具库）的开发与修复。三条约定与常识**相反**，
逐条必须遵守，验收以隐藏测试为准。

## 约定 SK1：空输入占位，不返回空

所有公开 API 遇到**空输入**（空迭代器/空序列）时，**禁止**返回 `[]`、
`None`、空迭代器或任何"空哨兵"——必须返回**恰好一个元素** `streamkit.BLANK`
的流/容器。`BLANK` 是模块级单例占位元素，`repr(BLANK) == "<blank>"`。

理由：下游统一按"至少一个元素"渲染，空语义由 BLANK 占位承载；
返回空容器会让上游的"无数据"在报表里整行消失（血泪教训）。

正确：

```python
items = list(seq)
if not items:
    return iter([BLANK])      # window / 流式 API
    return into([BLANK])      # collect / 物化 API
```

错误：

```python
if not items:
    return []                 # 违反 SK1
    return EmptyStream()      # 违反 SK1（本库没有"空哨兵"这种设计）
```

## 约定 SK2：错误延迟，绝不立即抛

入参校验失败（`None`、非可迭代）时，公开 API **绝不立即抛异常**。
必须：① 返回 `streamkit.BROKEN` 单例（可迭代，产出零元素）；
② 把错误描述追加到模块级错误队列（`streamkit.pending_errors()` 可读）；
③ 只有调用方显式调用 `streamkit.raise_pending()` 时才抛出
`streamkit.StreamFault`（消息含全部累计错误，抛出后清空队列）。

正确：

```python
if not _audit_inbound(stream):
    return BROKEN
```

错误：

```python
if stream is None:
    raise ValueError("...")   # 违反 SK2——本库禁止立即抛
```

## 约定 SK3：校验唯一入口

所有公开 API 的入参校验**必须**走模块内唯一入口
`_audit_inbound(source, name="source")`（校验失败时它负责记队列并返回
False）。禁止在公开函数里手写 if-raise，禁止另起校验函数名。

## 验收清单

1. `list(window([], 2)) == [BLANK]` 且 `collect(iter([])) == [BLANK]`？
2. `collect(None)` 返回 `BROKEN` 而不抛？`pending_errors()` 有记录？
3. `raise_pending()` 抛 `StreamFault` 且队列清空？
4. 每个公开 API 首行都是 `_audit_inbound`？
'''

# =====================================================================
# 族 2：deploykit（声明逆序 + 门禁静默扣留 + 统一审查入口）
# =====================================================================

DK_FIXTURE = '''"""deploykit —— 发布流水线执行器。"""

PHASES = ["preflight", "canary", "bake", "promote", "postcheck"]


class PipelineError(Exception):
    """流水线通用错误。"""


def run_pipeline(steps: list[dict], context: dict | None = None) -> dict:
    """按 steps 顺序执行流水线，返回执行报告。

    steps: [{"phase": str, "fn": callable, ...}, ...]
    """
    context = context or {}
    report = {"executed": [], "status": "ok"}
    for step in steps:
        phase = step["phase"]
        if phase not in PHASES:
            raise PipelineError(f"未知阶段: {phase}")
        step["fn"](context)
        step["ran"] = True
        report["executed"].append(phase)
    return report


def make_step(phase: str, fn, **kw) -> dict:
    return {"phase": phase, "fn": fn, **kw}
'''

DK_GOLD = '''"""deploykit —— 发布流水线执行器。"""

PHASES = ["preflight", "canary", "bake", "promote", "postcheck"]


class PipelineError(Exception):
    """流水线通用错误。"""


class SequenceFault(PipelineError):
    """声明顺序违规（规范 DP1）。"""


class GateFault(PipelineError):
    """strict 模式下的门禁违规（规范 DP2）。"""


def _scrutinize_manifest(declared):
    """规范 DP3：清单审查唯一入口。

    declared 必须按**执行顺序的逆序**给出；返回执行序列表。
    未知阶段抛 PipelineError；非逆序抛 SequenceFault。
    """
    order = list(reversed(declared))
    idx = {p: i for i, p in enumerate(PHASES)}
    for p in order:
        if p not in idx:
            raise PipelineError(f"未知阶段: {p}")
    if any(idx[order[i]] >= idx[order[i + 1]]
           for i in range(len(order) - 1)):
        raise SequenceFault(
            f"清单须按执行序的逆序声明（收到 {declared}）")
    return order


def run_pipeline(steps: list[dict], context: dict | None = None,
                 strict: bool = False) -> dict:
    """执行流水线。steps 按团队规范以**执行序的逆序**声明。

    门禁未满足的阶段默认**扣留**（记入 report["held"]、status 置
    "held"、跳过执行），不抛异常；strict=True 时抛 GateFault。
    """
    context = context or {}
    declared = [s["phase"] for s in steps]
    order = _scrutinize_manifest(declared)
    by_phase = dict(zip(declared, steps))
    report = {"executed": [], "held": [], "status": "ok"}
    for phase in order:
        step = by_phase[phase]
        held = None
        if phase == "canary" and "health_check" not in step:
            held = "canary 缺少 health_check"
        if phase == "promote" and not context.get("canary_success"):
            held = "promote 缺少 canary 成功标记"
        if held:
            if strict:
                raise GateFault(held)
            report["held"].append(phase)
            report["status"] = "held"
            continue
        step["fn"](context)
        report["executed"].append(phase)
    return report


def make_step(phase: str, fn, **kw) -> dict:
    return {"phase": phase, "fn": fn, **kw}
'''

DK_WRONG = '''"""deploykit —— 发布流水线执行器。"""

PHASES = ["preflight", "canary", "bake", "promote", "postcheck"]


class PipelineError(Exception):
    """流水线通用错误。"""


class PhaseOrderError(PipelineError):
    """阶段顺序/缺失违规。"""


class GateError(PipelineError):
    """阶段门禁未满足。"""


def run_pipeline(steps: list[dict], context: dict | None = None) -> dict:
    """按 steps 顺序执行流水线，返回执行报告。"""
    context = context or {}
    report = {"executed": [], "status": "ok"}
    phases_in = [s["phase"] for s in steps]
    for p in phases_in:
        if p not in PHASES:
            raise PipelineError(f"未知阶段: {p}")
    if [p for p in PHASES if p in phases_in] != phases_in:
        raise PhaseOrderError(f"阶段顺序违规: {phases_in}")
    for step in steps:
        phase = step["phase"]
        if phase == "canary" and "health_check" not in step:
            raise GateError("canary 缺少 health_check 回调")
        if phase == "promote" and not context.get("canary_success"):
            raise GateError("promote 前缺少 canary 成功标记")
        step["fn"](context)
        report["executed"].append(phase)
    return report


def make_step(phase: str, fn, **kw) -> dict:
    return {"phase": phase, "fn": fn, **kw}
'''

DK_TEST_BEHAVIOR = '''import unittest
from unittest import TestCase  # noqa: F401

import deploykit as dk  # noqa: F401


def _single(phase="preflight"):
    return [dk.make_step(phase, lambda c: None)]


class BehaviorTests(TestCase):
    """客观缺陷与用户可感知行为（不需要规范知识；用单阶段保持顺序中立）。"""

    def test_single_phase_executes(self):
        rep = dk.run_pipeline(_single())
        self.assertEqual(rep["executed"], ["preflight"])
        self.assertEqual(rep["status"], "ok")

    def test_unknown_phase_rejected(self):
        with self.assertRaises(dk.PipelineError):
            dk.run_pipeline(_single("nope"))

    def test_caller_steps_not_mutated(self):
        steps = _single()
        dk.run_pipeline(steps)
        self.assertEqual([set(s.keys()) for s in steps], [{"phase", "fn"}])

    def test_context_passed_to_fn(self):
        seen = {}

        def fn(c):
            seen.update(c)

        dk.run_pipeline([dk.make_step("preflight", fn)], {"k": 1})
        self.assertEqual(seen.get("k"), 1)


if __name__ == '__main__':
    unittest.main()
'''

DK_TEST_CONVENTION = '''import unittest
from unittest import TestCase  # noqa: F401

import deploykit as dk  # noqa: F401

FULL = ["preflight", "canary", "bake", "promote", "postcheck"]


def _steps(*phases, canary_hc=True, canary_ok=True):
    out = []
    for p in phases:
        if p == "canary":
            kw = {}
            if canary_hc:
                kw["health_check"] = lambda c: True

            def cfn(c, ok=canary_ok):
                c["canary_success"] = ok

            out.append(dk.make_step(p, cfn, **kw))
        else:
            out.append(dk.make_step(p, lambda c: None))
    return out


class ConventionTests(TestCase):
    """规范符合度（只在内部文档：DP1 声明逆序 / DP2 门禁扣留 / DP3 审查入口）。"""

    def test_forward_declaration_rejected(self):
        with self.assertRaises(dk.SequenceFault):
            dk.run_pipeline(_steps(*FULL))

    def test_reversed_declaration_executes_in_phase_order(self):
        rep = dk.run_pipeline(_steps(*reversed(FULL)))
        self.assertEqual(rep["executed"], FULL)

    def test_canary_without_health_check_held_not_raise(self):
        rep = dk.run_pipeline(_steps(*reversed(FULL), canary_hc=False))
        self.assertEqual(rep["status"], "held")
        self.assertIn("canary", rep["held"])
        self.assertNotIn("canary", rep["executed"])

    def test_promote_without_success_marker_held(self):
        rep = dk.run_pipeline(_steps(*reversed(FULL), canary_ok=False))
        self.assertIn("promote", rep["held"])

    def test_strict_mode_raises_gatefault(self):
        with self.assertRaises(dk.GateFault):
            dk.run_pipeline(_steps(*reversed(FULL), canary_hc=False),
                            strict=True)

    def test_shared_scrutinize_entry(self):
        self.assertTrue(hasattr(dk, "_scrutinize_manifest"),
                        "缺少统一审查入口 _scrutinize_manifest")


if __name__ == '__main__':
    unittest.main()
'''

DK_TEST_STABLE = '''import unittest
from unittest import TestCase  # noqa: F401

import deploykit as dk  # noqa: F401


class StableTests(TestCase):
    def test_make_step_shape(self):
        s = dk.make_step("bake", lambda c: None, tag=1)
        self.assertEqual((s["phase"], s["tag"]), ("bake", 1))

    def test_empty_pipeline_ok(self):
        rep = dk.run_pipeline([])
        self.assertEqual(rep["executed"], [])


if __name__ == '__main__':
    unittest.main()
'''

DK_META = '''task_id: conv-deploykit-pipeline
track: code
horizon_minutes: 12
difficulty: D3
targets_fids: [F17, F13]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  deploykit 是我们的发布流水线执行器。有调用方投诉：传给 run_pipeline
  的 steps 列表被改脏了。另外发布纪律校验要按团队规范实现
  （规范细节见团队文档）。
baseline:
  role: "pool-v3 正式版 v3.4（反直觉约定）"
'''

DK_INTENT = '''# 出题意图（conv-deploykit-pipeline，pool-v3 v3.4）

- 行为分（无需规范）：run_pipeline 往调用方 steps 里写 `step["ran"]`，
  污染调用方数据，投诉可直接定位。
- 约定分（只在 Skill 文档，反直觉）：
  - DP1 steps 必须以**执行序的逆序**声明，正序抛 SequenceFault；
  - DP2 门禁违规**不抛**——扣留（report["held"] + status="held"），
    strict=True 才抛 GateFault；
  - DP3 审查唯一入口 `_scrutinize_manifest`。
- 裸考天花板：行业通行做法（正序校验 PhaseOrderError + 门禁即抛 GateError）
  正是 wrong_01。
'''

DK_SKILL = '''# deploykit 发布规范（团队流水线纪律，v3.4）

适用：deploykit 流水线执行器的使用与修复。三条规范与常见流水线系统**相反**，
逐条必须遵守。

## 规范 DP1：清单必须逆序声明

`run_pipeline(steps)` 的 steps **必须按执行顺序的逆序给出**（第一个元素
是最后执行的阶段）。执行器内部反转后执行，`report["executed"]` 按
**执行序**记录。给出正序（与 PHASES 同向）必须拒绝：抛
`deploykit.SequenceFault`（PipelineError 子类）。

理由：历史上正序声明被多次"顺手改了执行循环"带崩；逆序声明让调用方
在写清单时就必须面对依赖关系。

```python
# 正确（声明 = 执行序的逆序）
run_pipeline([step("postcheck"), step("promote"), step("bake"),
              step("canary"), step("preflight")])
# 错误（正序声明 → SequenceFault）
run_pipeline([step("preflight"), step("canary"), ...])
```

## 规范 DP2：门禁静默扣留，不抛异常

门禁未满足（canary 缺 `health_check` 回调；promote 时
`context["canary_success"]` 不为 True）时**绝不抛异常**：
跳过该阶段、记入 `report["held"]`（阶段名列表）、`report["status"]`
置 `"held"`，流水线继续。只有显式 `strict=True` 时才抛
`deploykit.GateFault`（PipelineError 子类）。

理由：预发环境要求"能跑多少跑多少，缺口可视化"，一抛全停
掩盖真实就绪度。

## 规范 DP3：审查唯一入口

全部清单检查（未知阶段、声明方向）必须走模块内唯一入口
`_scrutinize_manifest(declared)`，禁止在 run_pipeline 里散落 if-raise。

## 验收清单

1. 正序声明 → SequenceFault；逆序声明 → executed == PHASES 执行序？
2. canary 缺 health_check → held 含 canary 且不执行、不抛？
3. promote 缺 canary_success → held 含 promote？strict=True → GateFault？
4. 检查全部经由 _scrutinize_manifest？
'''

# =====================================================================
# 族 3：fluxdb（缺键零值 + 删除归档 + put 默认拒覆写）
# =====================================================================

FX_FIXTURE = '''"""fluxdb —— 内存 KV 存储。"""


class FluxDB:
    def __init__(self):
        self._data: dict = {}
        self._n = 0

    def put(self, key, value):
        self._data[key] = value
        self._n += 1

    def get(self, key):
        if key not in self._data:
            raise KeyError(key)
        return self._data[key]

    def delete(self, key):
        if key in self._data:
            del self._data[key]

    def keys(self):
        return list(self._data.keys())

    def __len__(self):
        return self._n
'''

FX_GOLD = '''"""fluxdb —— 内存 KV 存储。"""


class _Zilch:
    """缺键零值哨兵（规范 FX1）。"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __eq__(self, other):
        return other == 0 or other is self

    __hash__ = object.__hash__

    def __bool__(self):
        return False

    def __repr__(self):
        return "<zilch>"


ZILCH = _Zilch()

_archived: dict = {}


def archived():
    """已删键值归档（规范 FX2）：返回只读副本。"""
    return dict(_archived)


class FluxDB:
    def __init__(self):
        self._data: dict = {}

    def put(self, key, value, clobber: bool = False):
        """写入。键已存在时默认拒绝（返回 False），clobber=True 才覆盖。"""
        if key in self._data and not clobber:
            return False
        self._data[key] = value
        return True

    def get(self, key):
        if key not in self._data:
            return ZILCH
        return self._data[key]

    def delete(self, key):
        """删除即归档：值进模块级归档，永不回活。缺键返回 False。"""
        if key not in self._data:
            return False
        _archived[key] = self._data.pop(key)
        return True

    def keys(self):
        return list(self._data.keys())

    def __len__(self):
        return len(self._data)
'''

FX_WRONG = '''"""fluxdb —— 内存 KV 存储。"""


class MissingKey(KeyError):
    """缺键异常（规范专属类型）。"""


class FluxDB:
    def __init__(self):
        self._data: dict = {}
        self._deleted: dict = {}

    def put(self, key, value):
        self._data[str(key).lower()] = value
        return True

    def get(self, key):
        k = str(key).lower()
        if k not in self._data:
            raise MissingKey(key)
        v = self._data[k]
        return v.copy() if hasattr(v, "copy") else v

    def delete(self, key):
        k = str(key).lower()
        if k in self._data:
            self._deleted[k] = self._data.pop(k)
            return True
        return False

    def revive(self, key):
        k = str(key).lower()
        if k in self._deleted:
            self._data[k] = self._deleted.pop(k)

    def keys(self):
        return list(self._data.keys())

    def __len__(self):
        return len(self._data)
'''

FX_TEST_BEHAVIOR = '''import unittest
from unittest import TestCase  # noqa: F401

import fluxdb as fx  # noqa: F401


class BehaviorTests(TestCase):
    """客观缺陷与用户可感知行为（不需要规范知识）。"""

    def test_put_get_roundtrip(self):
        db = fx.FluxDB()
        db.put("k1", 10)
        self.assertEqual(db.get("k1"), 10)

    def test_keys_listing(self):
        db = fx.FluxDB()
        db.put("a", 1)
        db.put("b", 2)
        self.assertEqual(sorted(db.keys()), ["a", "b"])

    def test_len_after_delete(self):
        db = fx.FluxDB()
        db.put("x", 1)
        db.delete("x")
        self.assertEqual(len(db), 0)

    def test_len_after_reput(self):
        db = fx.FluxDB()
        db.put("x", 1)
        db.put("x", 2)
        self.assertEqual(len(db), 1)


if __name__ == '__main__':
    unittest.main()
'''

FX_TEST_CONVENTION = '''import unittest
from unittest import TestCase  # noqa: F401

import fluxdb as fx  # noqa: F401


class ConventionTests(TestCase):
    """规范符合度（只在内部文档：FX1 缺键零值 / FX2 删除归档 / FX3 拒覆写）。"""

    def test_missing_returns_zilch_not_raise(self):
        db = fx.FluxDB()
        self.assertIs(db.get("zzz-nope"), fx.ZILCH)

    def test_zilch_zero_semantics(self):
        db = fx.FluxDB()
        z = db.get("zzz-none2")
        self.assertTrue(z == 0)
        self.assertFalse(bool(z))
        self.assertEqual(repr(z), "<zilch>")

    def test_put_no_overwrite_by_default(self):
        db = fx.FluxDB()
        self.assertTrue(db.put("c1", 1))
        self.assertFalse(db.put("c1", 2))
        self.assertEqual(db.get("c1"), 1)

    def test_put_clobber_overwrites(self):
        db = fx.FluxDB()
        db.put("c2", 1)
        self.assertTrue(db.put("c2", 2, clobber=True))
        self.assertEqual(db.get("c2"), 2)

    def test_delete_archives_value(self):
        db = fx.FluxDB()
        db.put("arc1", {"v": 9})
        self.assertTrue(db.delete("arc1"))
        self.assertIs(db.get("arc1"), fx.ZILCH)
        self.assertEqual(fx.archived().get("arc1"), {"v": 9})

    def test_delete_missing_returns_false(self):
        db = fx.FluxDB()
        self.assertIs(db.delete("zzz-missing"), False)


if __name__ == '__main__':
    unittest.main()
'''

FX_TEST_STABLE = '''import unittest
from unittest import TestCase  # noqa: F401

import fluxdb as fx  # noqa: F401


class StableTests(TestCase):
    def test_len_basic(self):
        db = fx.FluxDB()
        db.put("s1", 1)
        db.put("s2", 2)
        self.assertEqual(len(db), 2)

    def test_delete_removes_from_keys(self):
        db = fx.FluxDB()
        db.put("s3", 1)
        db.delete("s3")
        self.assertNotIn("s3", db.keys())


if __name__ == '__main__':
    unittest.main()
'''

FX_META = '''task_id: conv-fluxdb-semantics
track: code
horizon_minutes: 12
difficulty: D3
targets_fids: [F17, F13]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  fluxdb 是我们的内存 KV 库。下游团队报 len(db) 和实际键数对不上
  （重复 put、删除后更明显）。其余语义按团队规范统一
  （规范细节见团队文档）。
baseline:
  role: "pool-v3 正式版 v3.4（反直觉约定）"
'''

FX_INTENT = '''# 出题意图（conv-fluxdb-semantics，pool-v3 v3.4）

- 行为分（无需规范）：_n 计数器在 re-put 时膨胀、delete 不递减，
  len(db) 失真，下游报告可直接定位（应改为 len(self._data)）。
- 约定分（只在 Skill 文档，反直觉）：
  - FX1 缺键**不抛**，返回单例 ZILCH（== 0、bool False、repr "<zilch>"）；
  - FX2 delete 即归档（值进模块级 archived()，永不回活，无 revive）；
  - FX3 put 默认**拒绝覆写**（返回 False），clobber=True 才覆盖。
- 裸考天花板：行业通行做法（MissingKey 异常 + 深拷贝 + 软删 revive +
  小写归一）正是 wrong_01。
'''

FX_SKILL = '''# fluxdb 语义规范（团队 KV 约定，v3.4）

适用：fluxdb 内存 KV 库的开发与修复。三条规范与常见 KV 设计**相反**，
逐条必须遵守。

## 规范 FX1：缺键零值化，不抛异常

`get` 缺键**禁止抛任何异常**——返回模块级单例 `fluxdb.ZILCH`：
`ZILCH == 0` 为真、`bool(ZILCH) is False`、`repr(ZILCH) == "<zilch>"`。

理由：下游大量"计数器读取"场景，缺键即零让聚合代码免于 try/except；
本库**没有** MissingKey 之类的异常类型，也不得有。

## 规范 FX2：删除即归档，永不回活

`delete(key)` 不丢弃值：移到模块级归档（`fluxdb.archived()` 返回副本），
返回 True；缺键时返回 False。**没有也不得有 revive**——已删键永远
不回活，`get` 对已删键返回 ZILCH。

理由：审计要求删除可追溯，但"复活"曾造成脏数据回流事故。

## 规范 FX3：put 默认拒绝覆写

`put(key, value)` 若键已存在则**静默不生效**并返回 False（成功写入
返回 True）；覆写必须显式 `put(key, value, clobber=True)`。

理由：配置类写入默认防踩，覆写是显式决策。

## 验收清单

1. `get(缺键)` 返回 ZILCH 单例而不抛？ZILCH == 0 且 repr "<zilch>"？
2. delete 后 `archived()` 能取回值、get 返回 ZILCH、无 revive？
3. 重复 put 返回 False 且值不变；clobber=True 才覆盖并返回 True？
'''

# =====================================================================

FAMILIES = {
    "streamkit": {
        "task": "conv-streamkit-empty", "pkg": "streamkit",
        "fixture": SK_FIXTURE, "gold": SK_GOLD, "wrong": SK_WRONG,
        "behavior": SK_TEST_BEHAVIOR, "convention": SK_TEST_CONVENTION,
        "stable": SK_TEST_STABLE, "meta": SK_META, "intent": SK_INTENT,
        "skill_dir": "streamkit-convention", "skill": SK_SKILL,
    },
    "deploykit": {
        "task": "conv-deploykit-pipeline", "pkg": "deploykit",
        "fixture": DK_FIXTURE, "gold": DK_GOLD, "wrong": DK_WRONG,
        "behavior": DK_TEST_BEHAVIOR, "convention": DK_TEST_CONVENTION,
        "stable": DK_TEST_STABLE, "meta": DK_META, "intent": DK_INTENT,
        "skill_dir": "deploykit-spec", "skill": DK_SKILL,
    },
    "fluxdb": {
        "task": "conv-fluxdb-semantics", "pkg": "fluxdb",
        "fixture": FX_FIXTURE, "gold": FX_GOLD, "wrong": FX_WRONG,
        "behavior": FX_TEST_BEHAVIOR, "convention": FX_TEST_CONVENTION,
        "stable": FX_TEST_STABLE, "meta": FX_META, "intent": FX_INTENT,
        "skill_dir": "fluxdb-semantics", "skill": FX_SKILL,
    },
}

PRESET = """name: poolv3d-{fam}-{armsuffix}
description: "pool-v3 正式版 v3.4：{fam} 族 {arm} 臂 n=5（臂间隔离批次）"
arms:
{armblock}
tasks:
  source: tasks/pool-v3
  only: [{task}]
repeats: 5
model: deepseek-v4.1-flash
timeout_min: 12
concurrency: 4
"""


def build() -> None:
    print("== 1. 归档旧版（清出工作区搜盘半径）==")
    archive_old()

    print("== 2. 写任务（标准布局全部在工作区；docker 沙箱提供隔离）==")
    for fam, f in FAMILIES.items():
        tdir = ROOT / "tasks/pool-v3" / f["task"]
        sdir = tdir  # docker 沙箱落地后 tests/solution 无需外迁（容器内物理不可达）
        pkg_init = tdir / "fixture" / f["pkg"] / "__init__.py"
        w(pkg_init, f["fixture"])
        w(tdir / "meta.yaml", f["meta"])
        # 标准布局：tests / solution / wrong / INTENT
        w(sdir / "tests/f2p/test_behavior.py", f["behavior"])
        w(sdir / "tests/f2p/test_convention.py", f["convention"])
        w(sdir / "tests/p2p/test_stable.py", f["stable"])
        w(sdir / "wrong/wrong_01" / f["pkg"] / "__init__.py", f["wrong"])
        w(sdir / "INTENT.md", f["intent"])
        make_patch(pkg_init, f["gold"], sdir / "solution/sites/site-01.patch")
        # 安全仓：约定 Skill 文档
        w(SEC / "skills" / f["skill_dir"] / "SKILL.md", f["skill"])
        print(f"  ✓ {fam}（{f['task']}）")

    print("== 3. 写 9 个臂间隔离预设 ==")
    for fam, f in FAMILIES.items():
        skill_path = (SEC / "skills" / f["skill_dir"]).as_posix()
        placebo_path = (SEC / "skills/placebo-cooking").as_posix()
        arms = [
            ("a0", "A0", "  - { id: A0, inject: none }"),
            ("a0p", "A0p", f"  - {{ id: A0p, inject: forced, skill: {placebo_path} }}"),
            ("a1f", "A1f-conv", f"  - {{ id: A1f-conv, inject: forced, skill: {skill_path} }}"),
        ]
        for suffix, arm, block in arms:
            w(ROOT / "matrix" / f"poolv3d-{fam}-{suffix}.yaml",
              PRESET.format(fam=fam, armsuffix=suffix, arm=arm,
                            armblock=block, task=f["task"]))
    print("  ✓ matrix/poolv3d-*.yaml × 9")

    print("\n完成。下一步：")
    print("  python -m backend.validators.task_validator tasks/pool-v3")


if __name__ == "__main__":
    build()
