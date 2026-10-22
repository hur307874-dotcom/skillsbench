"""多 harness 归一化适配器：pi / codex JSONL → 统一 trace 事件。

在 claude_normalize 的两道防线基础上扩展：
- 格式自动识别（session+agent_start = pi；thread.started = codex）；
- 一致性校验：归一化后 token/turns 与源格式 usage 一致；
- 原始文件一律不动（raw_event_ref 指向原件）。

映射：
  pi    session→run_meta, message_end(assistant text)→step,
        tool_execution_start→tool_call, 末条 assistant message_end.usage→result
  codex thread.started→run_meta, agent_message→step,
        command_execution→tool_call(Bash), turn.completed.usage→result
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.normalize.claude_normalize import NormalizeError


def detect_format(lines: list[dict]) -> str:
    """pi / codex / unknown。"""
    types = {ev.get("type") for ev in lines[:5]}
    if "session" in types or "agent_start" in types:
        return "pi"
    if "thread.started" in types:
        return "codex"
    return "unknown"


def _pi_events(lines: list[dict], run_id: str) -> tuple[list[dict], dict]:
    events: list[dict] = []
    usage: dict = {}
    model = "unknown"
    i = 0
    for ev in lines:
        t = ev.get("type")
        if t == "session":
            events.append({"type": "run_meta", "run_id": run_id, "cli": "pi"})
        elif t == "message_end":
            msg = ev.get("message", {}) or {}
            if msg.get("role") == "assistant":
                model = msg.get("model", model)
                usage = msg.get("usage", usage) or usage
                i += 1
                for block in msg.get("content", []) or []:
                    if block.get("type") == "text":
                        events.append({"type": "step", "i": i, "role": "assistant",
                                       "text": block.get("text", "")[:4000]})
        elif t == "tool_execution_start":
            events.append({"type": "tool_call", "i": i,
                           "name": ev.get("toolName", ""),
                           "args": json.dumps(ev.get("args", {}),
                                              ensure_ascii=False)[:2000]})
    if events and events[0]["type"] == "run_meta":
        events[0]["model"] = model
    events.append({"type": "result", "run_id": run_id, "num_turns": i,
                   "tokens": {"in": usage.get("input", 0),
                              "out": usage.get("output", 0),
                              "cache_create": usage.get("cacheWrite", 0),
                              "cache_read": usage.get("cacheRead", 0)},
                   "is_error": False})
    return events, {"usage": usage, "num_turns": i}


def _codex_events(lines: list[dict], run_id: str) -> tuple[list[dict], dict]:
    events: list[dict] = []
    usage: dict = {}
    i = 0
    n_turns = 0
    for ev in lines:
        t = ev.get("type")
        if t == "thread.started":
            events.append({"type": "run_meta", "run_id": run_id, "cli": "codex"})
        elif t == "item.completed":
            item = ev.get("item", {}) or {}
            it = item.get("type")
            if it == "agent_message":
                i += 1
                events.append({"type": "step", "i": i, "role": "assistant",
                               "text": item.get("text", "")[:4000]})
            elif it == "command_execution":
                events.append({"type": "tool_call", "i": i, "name": "Bash",
                               "args": item.get("command", "")[:2000]})
        elif t == "turn.completed":
            n_turns += 1
            usage = ev.get("usage", usage) or usage
    events.append({"type": "result", "run_id": run_id, "num_turns": max(n_turns, 1),
                   "tokens": {"in": usage.get("input_tokens", 0),
                              "out": usage.get("output_tokens", 0),
                              "cache_create": 0,
                              "cache_read": usage.get("cached_input_tokens", 0)},
                   "is_error": False})
    return events, {"usage": usage, "num_turns": n_turns}


def normalize_harness(lines: list[dict], run_id: str) -> tuple[list[dict], dict]:
    fmt = detect_format(lines)
    if fmt == "pi":
        return _pi_events(lines, run_id)
    if fmt == "codex":
        return _codex_events(lines, run_id)
    raise NormalizeError(f"未知 harness 格式（run={run_id}）")


def check_harness_consistency(events: list[dict], raw: dict, fmt_hint: str) -> None:
    result = next((e for e in events if e["type"] == "result"), None)
    if result is None:
        raise NormalizeError("归一化缺 result 事件")
    u = raw.get("usage", {}) or {}
    if fmt_hint == "pi":
        if result["tokens"]["in"] != u.get("input", 0) or \
           result["tokens"]["out"] != u.get("output", 0):
            raise NormalizeError("pi 归一化前后 token 不一致")
    elif fmt_hint == "codex":
        if result["tokens"]["in"] != u.get("input_tokens", 0) or \
           result["tokens"]["out"] != u.get("output_tokens", 0):
            raise NormalizeError("codex 归一化前后 token 不一致")
