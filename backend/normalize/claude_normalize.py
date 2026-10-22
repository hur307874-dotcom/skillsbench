"""归一化层：claude CLI 输出 → 统一 trace 事件（ARCHITECTURE §4 schema）。

两道防线（§2.2）：
1. 原始输出一律原样留存（run_meta.raw_event_ref），归一化只映射不丢弃；
2. 一致性校验 normalize_and_check()：归一化后 token/成本/turns 与原始值
   必须一致，不一致抛 NormalizeError（不靠肉眼）。

支持两种 claude 输出：
- summary JSON（--output-format json）：单对象，产出 run_meta + result 事件
  （无逐步细节；需要逐步事件时驱动应改用 stream-json）；
- stream JSONL（--output-format stream-json --verbose）：逐行事件，
  产出 step / tool_call / result 事件。
"""
from __future__ import annotations

import json
from pathlib import Path


class NormalizeError(RuntimeError):
    pass


def _events_from_summary(raw: dict, run_id: str) -> list[dict]:
    u = raw.get("usage", {}) or {}
    events = [{
        "type": "run_meta",
        "run_id": run_id,
        "cli": "claude-code",
        "model": next(iter(raw.get("modelUsage", {}) or {"unknown": 0})),
        "num_turns": raw.get("num_turns", 0),
        "cost_usd": raw.get("total_cost_usd", 0.0),
        "tokens": {
            "in": u.get("input_tokens", 0),
            "out": u.get("output_tokens", 0),
            "cache_create": u.get("cache_creation_input_tokens", 0),
            "cache_read": u.get("cache_read_input_tokens", 0),
        },
        "duration_api_ms": raw.get("duration_api_ms", 0),
        "is_error": raw.get("is_error", False),
    }, {
        "type": "result",
        "run_id": run_id,
        "stop_reason": raw.get("stop_reason", ""),
        "text": str(raw.get("result", ""))[:4000],
    }]
    return events


def _events_from_stream(lines: list[dict], run_id: str) -> list[dict]:
    events: list[dict] = []
    i = 0
    for ev in lines:
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            events.append({"type": "run_meta", "run_id": run_id, "cli": "claude-code",
                           "model": ev.get("model", "unknown")})
        elif t == "assistant":
            i += 1
            msg = ev.get("message", {}) or {}
            for block in msg.get("content", []) or []:
                if block.get("type") == "text":
                    events.append({"type": "step", "i": i, "role": "assistant",
                                   "text": block.get("text", "")[:4000]})
                elif block.get("type") == "tool_use":
                    events.append({"type": "tool_call", "i": i,
                                   "name": block.get("name", ""),
                                   "args": json.dumps(block.get("input", {}),
                                                      ensure_ascii=False)[:2000]})
        elif t == "result":
            u = ev.get("usage", {}) or {}
            events.append({"type": "result", "run_id": run_id,
                           "stop_reason": ev.get("stop_reason", ""),
                           "num_turns": ev.get("num_turns", 0),
                           "cost_usd": ev.get("total_cost_usd", 0.0),
                           "tokens": {"in": u.get("input_tokens", 0),
                                      "out": u.get("output_tokens", 0),
                                      "cache_create": u.get("cache_creation_input_tokens", 0),
                                      "cache_read": u.get("cache_read_input_tokens", 0)},
                           "is_error": ev.get("is_error", False),
                           "text": str(ev.get("result", ""))[:4000]})
    return events


def normalize_trace(trace_path: Path, run_id: str) -> tuple[list[dict], dict]:
    """返回 (事件列表, 原始摘要)。原始文件不修改（raw_event_ref 指向它）。"""
    text = trace_path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        raise NormalizeError(f"空 trace：{trace_path}")
    try:
        raw = json.loads(text)  # summary 单对象
        if isinstance(raw, dict) and ("is_error" in raw or "result" in raw):
            return _events_from_summary(raw, run_id), raw
        raise NormalizeError(f"无法识别的 summary 结构：{trace_path}")
    except json.JSONDecodeError:
        lines = [json.loads(l) for l in text.splitlines() if l.strip()]
        return _events_from_stream(lines, run_id), {"stream_lines": len(lines)}


def check_consistency(events: list[dict], raw: dict, trace_path: Path) -> None:
    """一致性校验（§2.2 防线 2）：归一化后关键计数与原始值一致。"""
    if "usage" not in raw:  # stream 模式：以 result 事件为锚
        result = next((e for e in events if e["type"] == "result"), None)
        if result is None:
            raise NormalizeError(f"stream 缺 result 事件：{trace_path}")
        return
    meta = next(e for e in events if e["type"] == "run_meta")
    u = raw.get("usage", {}) or {}
    pairs = [
        ("num_turns", meta.get("num_turns"), raw.get("num_turns")),
        ("cost_usd", meta.get("cost_usd"), raw.get("total_cost_usd")),
        ("tokens.in", meta["tokens"]["in"], u.get("input_tokens")),
        ("tokens.out", meta["tokens"]["out"], u.get("output_tokens")),
        ("tokens.cache_create", meta["tokens"]["cache_create"],
         u.get("cache_creation_input_tokens")),
    ]
    for name, got, want in pairs:
        if got != want:
            raise NormalizeError(
                f"{trace_path}: 归一化前后 {name} 不一致：{got} != {want}")


def normalize_and_check(trace_path: Path, run_id: str) -> list[dict]:
    # 先识别 pi / codex 等 harness JSONL（多行、整体非单 JSON 对象）
    text = trace_path.read_text(encoding="utf-8", errors="replace").strip()
    if text:
        try:
            json.loads(text)
        except json.JSONDecodeError:
            from backend.normalize.harness_normalize import (
                check_harness_consistency, detect_format, normalize_harness)
            lines = [json.loads(l) for l in text.splitlines() if l.strip()]
            fmt = detect_format(lines)
            if fmt != "unknown":
                events, raw = normalize_harness(lines, run_id)
                check_harness_consistency(events, raw, fmt)
                for e in events:
                    e["raw_event_ref"] = str(trace_path)
                return events
    events, raw = normalize_trace(trace_path, run_id)
    check_consistency(events, raw, trace_path)
    for e in events:
        e["raw_event_ref"] = str(trace_path)
    return events
