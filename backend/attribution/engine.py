"""归因引擎：守卫调度 + 证据日志 + F-ID 聚合 + manifest 指令联动（L2→L3）。

数据驱动三原则：
- F-ID 语义从 failure_modes.yaml 读（不复制描述进代码）；
- 事件从 DuckDB 读（run/events 已归一）；
- manifest 联动读**任意**传入的 Skill 目录（--skill），代码零 Skill 名。

用法：
    python -m backend.attribution.engine --batch pool-v20-main
    python -m backend.attribution.engine --batch ablation-glm52 --skill skills/<any-skill>
    python -m backend.attribution.engine --run forged-multi-sieve-A0-r01
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from backend.attribution.detectors import (DETECTORS, RunCtx,  # noqa: E402
                                           classify_activity)
from backend.attribution.kappa_gate import gate as kappa_gate, stamp_hits  # noqa: E402

DB = ROOT / "results" / "traces.duckdb"
FM = ROOT / "failure_modes.yaml"


def load_outputs(trace_path: str | None) -> list[str]:
    """从原始 trace 提取每次工具执行的输出文本（按执行顺序）。

    配对规则：tool_execution_start（按 toolCallId 记序）→ tool_execution_end 取
    result.content 文本；isError 加前缀。归一化事件流不存输出（B1 依赖本函数）。
    """
    outs: list[str] = []
    if not trace_path or not Path(trace_path).exists():
        return outs
    pending: dict[str, int] = {}
    for line in Path(trace_path).open(encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = e.get("type")
        if t == "tool_execution_start":
            pending[e.get("toolCallId", "")] = len(outs)
            outs.append("")
        elif t == "tool_execution_end":
            k = pending.get(e.get("toolCallId", ""))
            if k is None:
                continue
            cont = (e.get("result") or {}).get("content") or []
            text = "\n".join(c.get("text", "") for c in cont if c.get("type") == "text")
            if e.get("isError"):
                text = "ERROR: " + text
            outs[k] = text[:4000]
    return outs


def events_from_raw(trace_path: str | None) -> tuple[list[dict], dict[int, str]]:
    """从原始 trace 直接构建归一化事件 + 工具输出（raw 是事实源）。

    归一化层有滞后/漏事件风险（κ 卡 6：raw 有 edit 而 DuckDB 事件缺失），
    trace_ref 可用时优先走本函数；返回 (events, outputs_by_call_idx)。
    """
    events: list[dict] = []
    outputs: dict[int, str] = {}
    if not trace_path or not Path(trace_path).exists():
        return events, outputs
    pending: dict[str, int] = {}
    idx = 0
    for line in Path(trace_path).open(encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = e.get("type")
        if t == "tool_execution_start":
            pending[e.get("toolCallId", "")] = idx
            events.append({"idx": idx, "type": "tool_call",
                           "payload": {"name": e.get("toolName", ""),
                                       "args": e.get("args", "")}})
            idx += 1
        elif t == "tool_execution_end":
            k = pending.get(e.get("toolCallId", ""))
            if k is not None:
                cont = (e.get("result") or {}).get("content") or []
                text = "\n".join(c.get("text", "") for c in cont
                                 if c.get("type") == "text")
                if e.get("isError"):
                    text = "ERROR: " + text
                outputs[k] = text[:4000]
        elif t == "message_end":
            msg = e.get("message", {}) or {}
            for c in msg.get("content", []) or []:
                if c.get("type") == "text" and (c.get("text") or "").strip():
                    events.append({"idx": idx, "type": "step",
                                   "payload": {"role": msg.get("role", ""),
                                               "text": c["text"]}})
                    idx += 1
    return events, outputs


def load_fids() -> dict[str, str]:
    fm = yaml.safe_load(FM.read_text(encoding="utf-8"))
    return {f["id"]: f["desc"] for f in fm}


def load_events(run_ids: list[str] | None = None,
                batch: str | None = None) -> dict[str, list[dict]]:
    con = duckdb.connect(str(DB), read_only=True)
    where = "1=1"
    params: list = []
    if batch:
        where += " AND batch_id = ?"
        params.append(batch)
    if run_ids:
        where += " AND run_id IN (" + ",".join("?" * len(run_ids)) + ")"
        params += run_ids
    rows = con.execute(
        f"SELECT run_id, idx, type, payload FROM events WHERE {where} ORDER BY run_id, idx",
        params).fetchall()
    out: dict[str, list[dict]] = {}
    for rid, idx, typ, payload in rows:
        out.setdefault(rid, []).append(
            {"idx": idx, "type": typ, "payload": json.loads(payload)})
    return out


def load_run_records(batch: str | None = None) -> dict[str, dict]:
    """runs.jsonl 读 run 级字段（score/tests/sites_required/turns/dead/error）。"""
    import glob
    out: dict[str, dict] = {}
    for f in glob.glob(str(ROOT / "results" / "*" / "runs.jsonl")):
        b = Path(f).parent.name
        if batch and b != batch:
            continue
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if line:
                r = json.loads(line)
                out[r["run_id"]] = r
    return out


def load_sites_required() -> dict[str, int]:
    """任务 meta 的 sites_required（通用：扫 pool-v2 与旧池 meta，不挑目录）。"""
    out = {}
    for mp in glob.glob(str(ROOT / "tasks" / "**" / "meta.yaml"), recursive=True):
        try:
            m = yaml.safe_load(open(mp, encoding="utf-8"))
            if m and m.get("task_id"):
                out[m["task_id"]] = m.get("sites_required", 1)
        except Exception:
            continue
    return out


def attribute_run(run_id: str, events: list[dict], rec: dict | None,
                  sites_req: int, fids: dict[str, str]) -> dict:
    # 原始 trace 优先（归一化层可能滞后/漏事件）；无 trace 才用 DuckDB 事件
    raw_events, raw_outputs = events_from_raw(
        rec.get("trace_ref") if rec else None)
    if raw_events:
        events = raw_events
    ctx = RunCtx(run_id=run_id, events=events,
                 score=rec.get("score") if rec else None,
                 tests=rec.get("tests", "") if rec else "",
                 sites_required=sites_req,
                 num_turns=rec.get("num_turns", 0) if rec else 0)
    if raw_events:
        ctx.outputs = raw_outputs
    else:
        # 退化路径：DuckDB 事件 + 按序配对输出
        outs = load_outputs(rec.get("trace_ref") if rec else None)
        for k, (idx, _n, _a) in enumerate(ctx.calls()):
            if k < len(outs) and outs[k]:
                ctx.outputs[idx] = outs[k]

    # B15 前置活动性门：无活动/零写操作的 run 不进 F-ID 判定
    activity = classify_activity(
        ctx,
        input_tokens=rec.get("input_tokens") if rec else None,
        output_tokens=rec.get("output_tokens") if rec else None,
        error=str(rec.get("error", "")) if rec else "")
    if activity != "ok":
        return {"run_id": run_id, "activity": activity, "hits": [],
                "skipped": True}
    hits = []
    for det in DETECTORS:
        h = det(ctx)
        if h:
            hits.append({"f_id": h.f_id, "desc": fids.get(h.f_id, ""),
                         "confidence": h.confidence,
                         "evidence_idx": h.evidence_idx, "note": h.note})
    return {"run_id": run_id, "activity": activity, "hits": hits,
            "skipped": bool(rec and (rec.get("dead") or "error" in rec))}


def link_manifest(hits: list[dict], skill_dir: Path) -> list[dict]:
    """F-ID → manifest.targets → 指令级归因（任意 Skill 目录通用）。"""
    mp = skill_dir / "manifest.yaml"
    if not mp.exists():
        return []
    manifest = yaml.safe_load(mp.read_text(encoding="utf-8"))
    instructions = manifest.get("instructions", [])
    out = []
    for h in hits:
        for ins in instructions:
            if h["f_id"] in (ins.get("targets") or []):
                out.append({"f_id": h["f_id"],
                            "instruction": ins.get("id"),
                            "lines": ins.get("lines"),
                            "prediction": ins.get("prediction", "")[:80],
                            "confidence": h["confidence"]})
    return out


def aggregate(records: list[dict]) -> dict:
    """批次聚合：F-ID 频次（high 与 medium/low 分列）。"""
    freq: dict[str, dict[str, int]] = {}
    runs_with_hits = 0
    for r in records:
        if r["hits"]:
            runs_with_hits += 1
        for h in r["hits"]:
            f = freq.setdefault(h["f_id"], {"high": 0, "medium_low": 0})
            f["high" if h["confidence"] == "high" else "medium_low"] += 1
    return {"total_runs": len(records), "runs_with_hits": runs_with_hits,
            "f_id_freq": freq}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default=None)
    ap.add_argument("--run", dest="run_ids", nargs="*", default=None)
    ap.add_argument("--skill", default=None, help="Skill 目录（指令级联动，可选）")
    ap.add_argument("--json", dest="as_json", action="store_true")
    args = ap.parse_args()

    fids = load_fids()
    events_by_run = load_events(args.run_ids, args.batch)
    recs = load_run_records(args.batch)
    sites_map = load_sites_required()

    records = []
    for rid, evs in sorted(events_by_run.items()):
        rec = recs.get(rid)
        sr = sites_map.get(rec["task_id"], 1) if rec else 1
        records.append(attribute_run(rid, evs, rec, sr, fids))

    instr_links = []
    if args.skill:
        for r in records:
            for link in link_manifest(r["hits"], Path(args.skill)):
                instr_links.append({**link, "run_id": r["run_id"]})

    agg = aggregate(records)
    g = kappa_gate()
    for r in records:
        r["hits"] = stamp_hits(r["hits"], g)
        if not r["hits"] and r.get("activity") == "ok":
            r["credibility"] = g["negative_status"]  # 无罪结论按阴性采信规则
    # 活动性分布（B15 后渠道死/无编辑与能力失败分列）
    act_dist: dict[str, int] = {}
    for r in records:
        act_dist[r.get("activity", "?")] = act_dist.get(r.get("activity", "?"), 0) + 1
    result = {"aggregate": agg, "activity_dist": act_dist, "kappa_gate": g,
              "records": records, "instruction_links": instr_links}

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0

    print(f"归因批次：{args.batch or '单 run'}｜run {agg['total_runs']}，"
          f"有命中 {agg['runs_with_hits']}｜活动性 {act_dist}")
    print(f"κ 门：{g['detector_version']} κ={g['kappa']} "
          f"{'过门' if g['pass'] else '未过门（阳性待复核）'}")
    for fid, c in sorted(agg["f_id_freq"].items()):
        print(f"  {fid}（{fids.get(fid, '')[:30]}…）：high {c['high']}｜m/l {c['medium_low']}")
    if instr_links:
        print("\n指令级联动（manifest.targets 反查）：")
        seen = {}
        for l in instr_links:
            k = (l["f_id"], l["instruction"])
            seen[k] = seen.get(k, 0) + 1
        for (fid, ins), n in sorted(seen.items()):
            print(f"  {fid} → 指令 {ins}（×{n} run）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
