"""检测器单测：合成事件序列逐条验证（机器出题机器判，同系统纪律）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.attribution.detectors import (RunCtx, detect_f01, detect_f03,
                                           detect_f05, detect_f11, detect_f15,
                                           detect_f16, detect_f17, detect_f19,
                                           classify_activity)


def ev(i, typ, **payload):
    return {"idx": i, "type": typ, "payload": {"type": typ, **payload}}


def bash(i, cmd):
    return ev(i, "tool_call", name="bash", args={"command": cmd})


def write(i, path):
    return ev(i, "tool_call", name="edit", args={"file_path": path})


def say(i, role, text):
    return ev(i, "step", role=role, text=text)


def ctx(events, score=None, tests="", sites=1):
    return RunCtx(run_id="t", events=events, score=score, tests=tests,
                  sites_required=sites)


def test_f01():
    # 先改后跑且结果坏 → 命中；成功 run → 不判（合法静态分析）
    bad = dict(score=0.5, tests="f2p:2/4")
    h = detect_f01(ctx([bash(1, "grep -rn foo ."), write(2, "a.py"),
                        bash(3, "python -m pytest tests/ -q")], **bad))
    assert h and h.f_id == "F01" and h.confidence == "high", "F01 应命中"
    h = detect_f01(ctx([bash(1, "grep -rn foo ."), write(2, "a.py"),
                        bash(3, "python -c 'import x'")], score=1.0))
    assert h is None, "F01 不应命中（成功 run 不归因）"
    h = detect_f01(ctx([bash(1, "python -m pytest tests/ -q"), write(2, "a.py")], **bad))
    assert h is None, "F01 不应命中（先跑后改）"
    h = detect_f01(ctx([write(1, "a.py")], **bad))
    assert h is None, "F01 guard：无运行事件不可判"


def test_f03():
    bad = dict(score=0.0, tests="f2p:0/4")
    h = detect_f03(ctx([bash(1, "python -m pytest tests/ -q"), write(2, "a.py"),
                        say(3, "assistant", "修复完成，问题已解决")], **bad))
    assert h and h.f_id == "F03", "F03 应命中"
    h = detect_f03(ctx([bash(1, "python -m pytest tests/ -q"), write(2, "a.py"),
                        say(3, "assistant", "修复完成")], score=1.0))
    assert h is None, "F03 不应命中（成功声明非失效）"
    h = detect_f03(ctx([write(1, "a.py"), bash(2, "python -m pytest tests/ -q"),
                        say(3, "assistant", "修复完成")], **bad))
    assert h is None, "F03 不应命中（写后有验证）"


def test_f05():
    h = detect_f05(ctx([], score=0.67, tests="f2p:4/6", sites=3))
    assert h and h.f_id == "F05" and h.confidence == "medium", "F05 应命中"
    assert detect_f05(ctx([], score=1.0, sites=3)) is None
    assert detect_f05(ctx([], score=0.5, sites=1)) is None, "单点任务不判 F05"


def test_f11():
    h = detect_f11(ctx([bash(1, "pytest -q"), bash(2, "pytest -q"),
                        bash(3, "pytest -q")]))
    assert h and h.f_id == "F11", "F11 应命中"
    h = detect_f11(ctx([bash(1, "pytest -q"), write(2, "a.py"),
                        bash(3, "pytest -q"), bash(4, "pytest -q")]))
    assert h is None, "F11 不应命中（中间有修改）"


def test_f15():
    h = detect_f15(ctx([say(1, "assistant", "I found it. Shall I proceed with the fix?"),
                        say(2, "assistant", "Proceeding anyway..."), write(3, "a.py")]))
    assert h and h.f_id == "F15", "F15 应命中"
    h = detect_f15(ctx([say(1, "assistant", "Shall I proceed?"),
                        say(2, "user", "yes go ahead"), write(3, "a.py")]))
    assert h is None, "F15 不应命中（有真实用户回应）"
    h = detect_f15(ctx([say(1, "assistant", "RED confirmed，测试如预期失败"),
                        write(2, "a.py")]))
    assert h is None, "F15 不应命中（行话非请求句式，校准回归）"


def test_f16():
    h = detect_f16(ctx([write(1, "tests/test_a.py"), write(2, "tests/test_b.py"),
                        write(3, "src/impl.py")], score=0.5, tests="f2p:1/4"))
    assert h and h.f_id == "F16", "F16 应命中（结果坏）"
    h = detect_f16(ctx([write(1, "src/impl.py"), write(2, "tests/test_a.py")],
                       score=0.5))
    assert h is None, "F16 不应命中（先实现后测试）"
    h = detect_f16(ctx([write(1, "tests/test_a.py"), write(2, "tests/test_b.py"),
                        write(3, "src/impl.py")], score=1.0))
    assert h is None, "F16 不应命中（成功 run 不归因，κ 卡 1 回归）"


def _ctx_with_outputs(events, outputs, score=None, tests="", sites=1):
    c = RunCtx(run_id="t", events=events, score=score, tests=tests,
               sites_required=sites)
    c.outputs = outputs
    return c


def test_f17():
    # pytest 失败 → 改 → 同签名再失败 → 命中
    evs = [bash(1, "python -m pytest -q"), write(2, "a.py"),
           bash(3, "python -m pytest -q")]
    outs = {1: "FAILED tests/test_x.py::test_a - AssertionError",
            3: "FAILED tests/test_x.py::test_a - AssertionError"}
    h = detect_f17(_ctx_with_outputs(evs, outs, score=0.0, tests="f2p:0/4"))
    assert h and h.f_id == "F17" and h.confidence == "high", "F17 应命中（同签名复现）"
    # 改后通过（无签名）→ 不判
    outs2 = {1: "FAILED tests/test_x.py::test_a", 3: "4 passed"}
    h = detect_f17(_ctx_with_outputs(evs, outs2, score=0.5))
    assert h is None, "F17 不应命中（改后签名消失）"
    # 无输出数据 → guard 不判
    h = detect_f17(ctx(evs, score=0.0))
    assert h is None, "F17 guard：无输出不判"
    # 成功 run 不判
    h = detect_f17(_ctx_with_outputs(evs, outs, score=1.0))
    assert h is None, "F17 不应命中（成功 run 不归因）"


def test_f19():
    read = lambda i, p: ev(i, "tool_call", name="read", args={"path": p})
    evs = [read(1, "CONTEXT.md"), read(2, "docs/adr/001.md"), write(3, "a.py")]
    outs = {1: "Error: No such file or directory", 2: "path not found"}
    h = detect_f19(_ctx_with_outputs(evs, outs, score=0.0, tests="f2p:0/4"))
    assert h and h.f_id == "F19", "F19 应命中（≥2 次 not found）"
    evs1 = [read(1, "CONTEXT.md"), write(2, "a.py")]
    outs1 = {1: "No such file"}
    h = detect_f19(_ctx_with_outputs(evs1, outs1, score=0.0))
    assert h is None, "F19 不应命中（仅 1 次）"
    evs2 = [read(1, "a.py"), read(2, "b.py"), write(3, "a.py")]
    outs2 = {1: "file content here", 2: "more content"}
    h = detect_f19(_ctx_with_outputs(evs2, outs2, score=0.0))
    assert h is None, "F19 不应命中（文件都存在）"


def test_activity_gate():
    c = ctx([bash(1, "ls")], score=0.0)
    # 渠道死：token 显式全 0 且无任何工具调用
    c_empty = ctx([], score=0.0)
    assert classify_activity(c_empty, 0, 0) == "channel_dead"
    # 渠道死：超时且事件流无任何工具调用
    assert classify_activity(c_empty, None, None, "timeout 720s") == "channel_dead"
    # token 显式 0/0 但事件流有调用+有写：以事件为准 → ok（κ 卡 6 回归）
    c3 = ctx([bash(1, "ls"), write(2, "a.py")], score=0.5)
    assert classify_activity(c3, 0, 0) == "ok"
    # token 字段缺失（老批次）≠ 0：有调用但无写 → no_edit
    assert classify_activity(c, None, None) == "no_edit"
    # 合法无编辑：有 token 无写操作
    assert classify_activity(c, 100, 200) == "no_edit"
    # 正常：有写操作
    c2 = ctx([write(1, "a.py")], score=1.0)
    assert classify_activity(c2, 100, 200) == "ok"
    # 超时有调用无写 → no_edit 而非 channel_dead（探索后放弃是合法结局）
    assert classify_activity(c, None, None, "timeout 720s") == "no_edit"


if __name__ == "__main__":
    for f in [test_f01, test_f03, test_f05, test_f11, test_f15, test_f16,
              test_f17, test_f19, test_activity_gate]:
        f()
        print(f"✓ {f.__name__}")
    print("全部检测器单测通过")
