"""行为信号检测器单元测试（合成事件，不调 LLM、不需要真实 trace）。

用法：python -m pytest backend/graders/test_behavior_signals.py -q
"""
from backend.graders.behavior_signals import detect_all


def ev_step(i, text, role="assistant"):
    return {"type": "step", "i": i, "role": role, "text": text}


def ev_tool(i, name, args=""):
    return {"type": "tool_call", "i": i, "name": name, "args": args}


def ev_result(text="", **kw):
    return {"type": "result", "text": text, **kw}


def names(results):
    return {r["name"]: r for r in results}


# --- F15 幻影用户交互 ---
def test_phantom_user_positive():
    events = [
        ev_step(1, "我先分析一下"),
        ev_step(2, "请您确认是否继续修改？"),
        ev_step(3, "既然您同意了，我继续"),
        ev_step(4, "修改完成"),
        ev_result("已完成"),
    ]
    r = names(detect_all(events))["phantom_user_interaction"]
    assert r["present"] and r["wasted_turns"] >= 1


def test_phantom_user_negative():
    events = [ev_step(1, "直接修改"), ev_tool(2, "Edit", "{}"), ev_result("done")]
    assert not names(detect_all(events))["phantom_user_interaction"]["present"]


# --- F03 不跑测试就宣布完成 ---
def test_missing_verification_positive():
    events = [
        ev_tool(1, "Read", "{}"),
        ev_tool(2, "Edit", "{}"),
        ev_result("修复完成"),
    ]
    assert names(detect_all(events))["missing_verification"]["present"]


def test_missing_verification_negative_ran_tests():
    events = [
        ev_tool(1, "Edit", "{}"),
        ev_tool(2, "Bash", '{"command":"pytest -q"}'),
        ev_result("修复完成，测试全过"),
    ]
    assert not names(detect_all(events))["missing_verification"]["present"]


# --- F01 未复现就动手 ---
def test_no_reproduction_positive():
    events = [ev_tool(1, "Edit", "{}"), ev_tool(2, "Bash", "{}")]
    assert names(detect_all(events))["no_reproduction"]["present"]


def test_no_reproduction_negative():
    events = [ev_tool(1, "Bash", '{"command":"python calc.py"}'), ev_tool(2, "Edit", "{}")]
    assert not names(detect_all(events))["no_reproduction"]["present"]


# --- F11 过度验证 ---
def test_over_verification_positive():
    events = [ev_tool(i, "Bash", '{"command":"pytest -q"}') for i in range(1, 4)]
    assert names(detect_all(events))["over_verification"]["present"]


def test_over_verification_negative_with_edit_between():
    events = [
        ev_tool(1, "Bash", '{"command":"pytest -q"}'),
        ev_tool(2, "Edit", "{}"),
        ev_tool(3, "Bash", '{"command":"pytest -q"}'),
    ]
    assert not names(detect_all(events))["over_verification"]["present"]


# --- F16 批量造测试 ---
def test_horizontal_test_batching_positive():
    events = [ev_tool(1, "Write", '{"file_path":"test_x.py","content":"def test_a():\\ndef test_b():\\ndef test_c():\\n"}')]
    assert names(detect_all(events))["horizontal_test_batching"]["present"]


def test_horizontal_test_batching_negative():
    events = [ev_tool(1, "Write", '{"file_path":"x.py","content":"def f():\\n"}')]
    assert not names(detect_all(events))["horizontal_test_batching"]["present"]


# --- F19 空转查找 ---
def test_phantom_file_search_positive():
    events = [ev_tool(1, "Read", '{"file_path":"CONTEXT.md"}'),
              ev_tool(2, "Glob", '{"pattern":"docs/adr/**"}')]
    r = names(detect_all(events))["phantom_file_search"]
    assert r["present"] and r["wasted_turns"] == 2


# --- F05 判分侧 ---
def test_incomplete_fix_positive():
    r = names(detect_all([], {"sites_fixed": 1, "sites_required": 4}))["incomplete_fix"]
    assert r["present"] and "1/4" in r["detail"]


def test_incomplete_fix_negative():
    assert not names(detect_all([], {"sites_fixed": 4, "sites_required": 4}))["incomplete_fix"]["present"]


# --- summary 格式（无 step 事件）不伪造阳性 ---
def test_no_step_events_no_false_positive():
    events = [{"type": "run_meta"}, ev_result("修复完成")]
    rs = detect_all(events)
    assert all(not r["present"] for r in rs)
    assert any(r.get("detail") == "no_events" for r in rs)


# --- F-ID 映射齐全 ---
def test_fid_mapping():
    rs = detect_all([ev_step(1, "请您确认")], {"sites_fixed": 1, "sites_required": 2})
    assert all(r["f_id"].startswith("F") for r in rs)


# --- F15 假阳回归（pi-ql1 实测 5/5 假阳，2026-09-27 校准）---
def test_phantom_user_fp_red_confirmed():
    events = [ev_step(1, "RED confirmed. Now the fix."), ev_result("done")]
    assert not names(detect_all(events))["phantom_user_interaction"]["present"]


def test_phantom_user_fp_confirm_tests():
    events = [ev_step(1, "Let me confirm the required tests pass"), ev_result("done")]
    assert not names(detect_all(events))["phantom_user_interaction"]["present"]


def test_phantom_user_fp_grep_confirms():
    events = [ev_step(1, "grep confirms zero remaining references"), ev_result("done")]
    assert not names(detect_all(events))["phantom_user_interaction"]["present"]


def test_phantom_user_tp_please_confirm():
    events = [ev_step(1, "I've found the issue. Please confirm before I proceed."), ev_result("done")]
    assert names(detect_all(events))["phantom_user_interaction"]["present"]


def test_phantom_user_tp_shall_i():
    events = [ev_step(1, "Shall I apply this fix?"), ev_result("done")]
    assert names(detect_all(events))["phantom_user_interaction"]["present"]


def test_phantom_user_tp_zh():
    events = [ev_step(1, "需要我继续吗？"), ev_result("done")]
    assert names(detect_all(events))["phantom_user_interaction"]["present"]
