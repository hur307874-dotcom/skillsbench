"""行为信号检测器 ×7：trace 事件 → 0/1（纯函数，不调 LLM）。

对应 failure_modes.yaml 的 observable 定义；中介链①环的功效来源。
输入：归一化事件列表（normalize 层输出）+ run 记录（判分侧信号用）。
输出：{"name", "present": bool, "wasted_turns"?, "wasted_tokens"?, "detail"?}

注意：step/tool_call 级检测器需要 stream-json 事件流；
summary 格式（无 step 事件）下相关检测器返回 present=False + detail="no_events"，
不伪造阴性结果——报告须按 has_events 过滤展示。
"""
from __future__ import annotations

import re

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
RUN_TOOL_HINTS = ("Bash", "bash", "shell", "run")
# F15 只匹配"向用户发出确认/批准请求"的句式（疑问/请求语气），不匹配验证语境
# （"RED confirmed" / "Let me confirm the tests pass" / "grep confirms"）。
# 校准依据：pi-ql1 批次 5/5 假阳全部来自验证语境（2026-09-27 实测，见 EXPERIMENT_LOG）。
CONFIRM_PAT = re.compile(
    r"(please confirm|do you approve|shall I|would you like me to|can I proceed|"
    r"may I proceed|is that (?:ok|okay)|awaiting your (?:confirmation|approval)|"
    r"get your approval|"
    r"请您确认|请确认(?=[吗？?])|是否确认|需要我继续吗|是否可以继续|是否继续|"
    r"要我(?:继续|开始|修改)吗|我可以(?:继续|开始|修改)吗|请您批准|是否同意)", re.I)
DONE_PAT = re.compile(r"(修复完成|已完成|done|fixed|all tests pass|修改完毕)", re.I)
MISSING_FILE_PAT = re.compile(r"(CONTEXT\.md|docs/adr|ADR-?\d)", re.I)


def _steps(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("type") == "step"]


def _tools(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("type") == "tool_call"]


def _result(events: list[dict]) -> dict:
    return next((e for e in events if e.get("type") == "result"), {})


def has_step_events(events: list[dict]) -> bool:
    return bool(_steps(events) or _tools(events))


# ① F15 等待不存在的用户（I1 的主信号，H1 主指标）
def phantom_user_interaction(events: list[dict]) -> dict:
    steps = _steps(events)
    if not steps:
        return {"name": "phantom_user_interaction", "present": False, "detail": "no_events"}
    hits = [s for s in steps if s.get("role") == "assistant" and CONFIRM_PAT.search(s.get("text", ""))]
    if not hits:
        return {"name": "phantom_user_interaction", "present": False}
    # 浪费轮次 ≈ 命中确认句式后、无真实用户输入仍继续的 assistant 步数
    first_hit_i = hits[0].get("i", 0)
    later = [s for s in steps if s.get("i", 0) >= first_hit_i and s.get("role") == "assistant"]
    return {"name": "phantom_user_interaction", "present": True,
            "wasted_turns": max(len(later) - 1, 1),
            "detail": f"命中 {len(hits)} 处确认请求句式"}


# ② F03 不跑测试就宣布完成
def missing_verification(events: list[dict]) -> dict:
    tools = _tools(events)
    if not tools:
        return {"name": "missing_verification", "present": False, "detail": "no_events"}
    edit_idx = [k for k, t in enumerate(tools) if t.get("name") in EDIT_TOOLS]
    if not edit_idx:
        return {"name": "missing_verification", "present": False}
    last_edit = max(edit_idx)
    ran_after = any(any(h in t.get("name", "") for h in RUN_TOOL_HINTS)
                    for t in tools[last_edit + 1:])
    claims_done = bool(DONE_PAT.search(_result(events).get("text", "")))
    present = (not ran_after) and claims_done
    return {"name": "missing_verification", "present": present,
            "detail": "末次编辑后无运行事件且宣称完成" if present else ""}


# ③ F01 未复现就动手改
def no_reproduction(events: list[dict]) -> dict:
    tools = _tools(events)
    if not tools:
        return {"name": "no_reproduction", "present": False, "detail": "no_events"}
    first_edit = next((k for k, t in enumerate(tools) if t.get("name") in EDIT_TOOLS), None)
    if first_edit is None:
        return {"name": "no_reproduction", "present": False}
    ran_before = any(any(h in t.get("name", "") for h in RUN_TOOL_HINTS)
                     for t in tools[:first_edit])
    return {"name": "no_reproduction", "present": not ran_before,
            "detail": "首次编辑前无任何运行/复现事件" if not ran_before else ""}


# ④ F11 过度验证：同一工具同样参数 ≥3 次且无中间修改
def over_verification(events: list[dict]) -> dict:
    tools = _tools(events)
    if not tools:
        return {"name": "over_verification", "present": False, "detail": "no_events"}
    streak, best = 1, 1
    for a, b in zip(tools, tools[1:]):
        same = a.get("name") == b.get("name") and a.get("args") == b.get("args")
        streak = streak + 1 if same else 1
        best = max(best, streak)
    return {"name": "over_verification", "present": best >= 3,
            "detail": f"同一调用连续重复 {best} 次" if best >= 3 else ""}


# ⑤ F16 批量造测试：多个测试函数在同一/连续 Edit 落盘且无实现-测试交替
def horizontal_test_batching(events: list[dict]) -> dict:
    tools = _tools(events)
    if not tools:
        return {"name": "horizontal_test_batching", "present": False, "detail": "no_events"}
    for t in tools:
        if t.get("name") not in EDIT_TOOLS:
            continue
        args = t.get("args", "")
        if "test_" in args and args.count("def test_") >= 3:
            return {"name": "horizontal_test_batching", "present": True,
                    "detail": f"单次编辑落盘 ≥3 个测试函数（{t.get('name')}）"}
    return {"name": "horizontal_test_batching", "present": False}


# ⑥ F19 空转查找不存在的项目文件（I6 的信号）
def phantom_file_search(events: list[dict]) -> dict:
    tools = _tools(events)
    if not tools:
        return {"name": "phantom_file_search", "present": False, "detail": "no_events"}
    hits = [t for t in tools
            if t.get("name") in ("Read", "Glob", "Grep", "read", "glob")
            and MISSING_FILE_PAT.search(t.get("args", ""))]
    return {"name": "phantom_file_search", "present": len(hits) >= 1,
            "wasted_turns": len(hits),
            "detail": f"{len(hits)} 次查找 CONTEXT.md/docs/adr 类文件" if hits else ""}


# ⑦ F05 漏改同模式调用点（判分侧信号：吃 run 记录而非 trace）
def incomplete_fix(run_record: dict) -> dict:
    fixed = run_record.get("sites_fixed")
    required = run_record.get("sites_required")
    if fixed is None or required is None:
        return {"name": "incomplete_fix", "present": False, "detail": "no_sites_info"}
    return {"name": "incomplete_fix", "present": fixed < required,
            "detail": f"修改 {fixed}/{required} 处"}


ALL_TRACE_DETECTORS = [
    phantom_user_interaction, missing_verification, no_reproduction,
    over_verification, horizontal_test_batching, phantom_file_search,
]
ALL_RECORD_DETECTORS = [incomplete_fix]

FID_OF = {
    "phantom_user_interaction": "F15",
    "missing_verification": "F03",
    "no_reproduction": "F01",
    "over_verification": "F11",
    "horizontal_test_batching": "F16",
    "phantom_file_search": "F19",
    "incomplete_fix": "F05",
}


def detect_all(events: list[dict], run_record: dict | None = None) -> list[dict]:
    """跑全部检测器，返回带 F-ID 映射的结果列表。"""
    out = []
    for det in ALL_TRACE_DETECTORS:
        r = det(events)
        r["f_id"] = FID_OF[r["name"]]
        out.append(r)
    if run_record:
        for det in ALL_RECORD_DETECTORS:
            r = det(run_record)
            r["f_id"] = FID_OF[r["name"]]
            out.append(r)
    return out
