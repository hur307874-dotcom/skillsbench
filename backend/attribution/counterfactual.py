"""L4 反事实自检（B2）：归因阳性结论的证据矛盾检查（辅助 LLM，temp=0）。

方法（LLM-as-a-Judge 纪律）：
- 对每条 F-ID 命中，把「该 F-ID 的可观测判据」+「证据事件原文」交给辅助 LLM，
  要求判定 支持/矛盾/不确定 且**必须引用证据原文**；
- 判"矛盾"的命中降级为 disputed（不进定量结论，与 κ 门水印并列）；
- 红线：辅助 LLM 只做证据核对，不重新归因（归因仍是检测器的事）。

用法：
    python -m backend.attribution.counterfactual --batch poolv3d-streamkit-a1f
    （或在 engine 输出 records 后作为后处理调用 check_hits(records)）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.llm_client import chat  # noqa: E402

PROMPT_TMPL = """你是归因证据核对员。一个自动检测器对一次 AI 编程 run 下了失效归因，
你的唯一任务：核对证据是否支持该归因，**不得重新归因**。

失效模式 {f_id} 的可观测判据：
{observable}

检测器给出的归因说明：{note}

证据事件（trace 节选）：
{evidence}

要求：
1. 逐条核对证据是否满足可观测判据；
2. 输出严格三行：
判定：支持 | 矛盾 | 不确定
引用：<从证据原文中抄一句最关键的话>
理由：<一句话>
"""


def build_evidence(events: list[dict], evidence_idx: list[int], limit: int = 6) -> str:
    by_idx = {e["idx"]: e for e in events}
    lines = []
    for i in evidence_idx[:limit]:
        e = by_idx.get(i)
        if not e:
            continue
        p = e["payload"]
        if e["type"] == "tool_call":
            lines.append(f"#{i} 工具 {p.get('name')}: {str(p.get('args'))[:120]}")
        elif e["type"] == "step":
            lines.append(f"#{i} {p.get('role')} 说: {(p.get('text') or '')[:120]}")
    return "\n".join(lines) or "（无证据事件文本）"


def check_hit(f_id: str, observable: str, note: str,
              evidence: str, timeout: int = 90) -> dict:
    """单条命中的反事实核对。"""
    prompt = PROMPT_TMPL.format(f_id=f_id, observable=observable,
                                note=note or "（无）", evidence=evidence)
    try:
        out = chat([{"role": "user", "content": prompt}],
                   temperature=0, max_tokens=300, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return {"verdict": "unclear", "quote": "", "reason": f"辅助 LLM 调用失败：{e}"[:100]}
    m = re.search(r"判定：\s*(支持|矛盾|不确定)", out)
    q = re.search(r"引用：\s*(.+)", out)
    r = re.search(r"理由：\s*(.+)", out)
    verdict = {"支持": "support", "矛盾": "contradict", "不确定": "unclear"}.get(
        m.group(1) if m else "", "unclear")
    return {"verdict": verdict,
            "quote": (q.group(1).strip()[:150] if q else ""),
            "reason": (r.group(1).strip()[:150] if r else "")}


def check_hits(records: list[dict], events_by_run: dict[str, list[dict]],
               fid_observables: dict[str, str]) -> list[dict]:
    """对 records 里的阳性命中批量做 L4 核对（就地写 l4 字段并降级矛盾项）。"""
    for rec in records:
        evs = events_by_run.get(rec["run_id"], [])
        for h in rec.get("hits", []):
            ev_text = build_evidence(evs, h.get("evidence_idx", []))
            res = check_hit(h["f_id"], fid_observables.get(h["f_id"], ""),
                            h.get("note", ""), ev_text)
            h["l4"] = res
            if res["verdict"] == "contradict":
                h["credibility"] = "disputed（L4 矛盾）"
    return records


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    args = ap.parse_args()
    from backend.attribution.engine import (attribute_run, load_events,
                                            load_run_records, load_sites_required,
                                            load_fids)
    import yaml
    fm = yaml.safe_load((ROOT / "failure_modes.yaml").read_text(encoding="utf-8"))
    obs = {f["id"]: f.get("observable", "") for f in fm}
    fids = load_fids()
    events_by_run = load_events(batch=args.batch)
    recs = load_run_records(args.batch)
    sites = load_sites_required()
    records = []
    for rid, evs in sorted(events_by_run.items()):
        rec = recs.get(rid)
        records.append(attribute_run(rid, evs, rec,
                                     sites.get(rec["task_id"], 1) if rec else 1, fids))
    records = check_hits(records, events_by_run, obs)
    n_hits = sum(len(r["hits"]) for r in records)
    n_disp = sum(1 for r in records for h in r["hits"]
                 if h.get("l4", {}).get("verdict") == "contradict")
    print(f"L4 反事实自检：批次 {args.batch}，命中 {n_hits}，判矛盾 {n_disp}")
    for r in records:
        for h in r["hits"]:
            l4 = h.get("l4", {})
            print(f"  {r['run_id']} {h['f_id']} -> {l4.get('verdict')}｜{l4.get('reason', '')[:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
