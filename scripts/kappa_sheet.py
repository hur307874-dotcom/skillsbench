"""κ 校准表生成器：抽样 run + 检测器判定 + 关键证据，供人工标注。

采样策略：跨批次混合（命中批 + 全满分批 + 弱基座批），命中/未命中约 1:2，
每张卡片给出检测器结论与支撑证据（事件摘要），标注者只需判 同意/不同意。

用法：python scripts/kappa_sheet.py  → 输出 docs/kappa_sheet.md
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.attribution.engine import (attribute_run, load_events, load_fids,
                                        load_run_records, load_sites_required)

SAMPLE_BATCHES = ["gradient-glm-5.2", "v2-glm52", "heldout-final",
                  "pool-v20-main", "forged-v13", "pilot-multi2"]
N = 20


def main() -> int:
    fids = load_fids()
    sites = load_sites_required()

    # run_id 跨批次会撞名（续跑语义），记录与事件必须按 (batch, run_id) 对齐
    import duckdb
    con = duckdb.connect(str(ROOT / "results" / "traces.duckdb"), read_only=True)
    rows = con.execute(
        "SELECT DISTINCT batch_id, run_id FROM events").fetchall()
    have_events = set(rows)
    recs: dict[tuple, dict] = {}
    import glob
    for f in glob.glob(str(ROOT / "results" / "*" / "runs.jsonl")):
        b = Path(f).parent.name
        for l in open(f, encoding="utf-8"):
            l = l.strip()
            if l:
                r = json.loads(l)
                if (b, r["run_id"]) in have_events:
                    recs[(b, r["run_id"])] = r

    rng = random.Random(20261002)
    pool = sorted(recs.keys())
    rng.shuffle(pool)
    # 分层采样：先算检测器结论，命中卡全收（池子小），无罪卡随机补足 N
    hits, cleans = [], []
    for key in pool:
        batch, rid = key
        rec = recs[key]
        evs = load_events([rid], batch).get(rid, [])
        sr = sites.get(rec["task_id"], 1)
        attr = attribute_run(rid, evs, rec, sr, fids)
        (hits if attr["hits"] else cleans).append((key, rec, evs, attr))
    picks = hits[:8] + cleans[:N - min(8, len(hits))]
    print(f"分层：命中 {len(hits[:8])} + 无罪 {len(picks) - len(hits[:8])}")

    lines = ["# κ 校准表（归因器采信门）",
             "",
             f"采样 {len(picks)} 个 run（批次混合，seed=20261002）。",
             "标注方法：逐条看【检测器结论】与【证据摘要】，判 **同意 / 不同意**；",
             "不同意请注明正确结论（如：应为 F05 / 应为无罪）。",
             "判定规则：κ = (Po − Pe) / (1 − Pe)，≥0.7 归因器自动采信。",
             ""]
    rows_for_calc = []
    for i, ((batch, rid), rec, evs, attr) in enumerate(picks, 1):
        verdict = "、".join(h["f_id"] for h in attr["hits"]) or "无罪（无命中）"
        snippets = []
        for e in evs[:40]:
            p = e["payload"]
            if e["type"] == "tool_call":
                snippets.append(f"#{e['idx']} 工具 {p.get('name')}: "
                                f"{str(p.get('args'))[:80]}")
            elif e["type"] == "step" and p.get("role") == "assistant":
                t = (p.get("text") or "").replace("\n", " ")[:80]
                if t:
                    snippets.append(f"#{e['idx']} 说: {t}")
            if len(snippets) >= 6:
                break
        score = rec.get("score", "?")
        tests = rec.get("tests", "")
        lines += [
            f"## 卡片 {i}：{rid}（批次 {batch}）",
            f"- 任务 {rec['task_id']}｜臂 {rec['arm']}｜机器分 {score}（{tests}）",
            f"- **检测器结论：{verdict}**",
            "- 证据摘要：",
            *[f"  - `{s}`" for s in snippets],
            "- 你的判定：＿＿＿（同意 / 不同意：____）",
            ""]
        rows_for_calc.append({"i": i, "batch": batch, "run_id": rid,
                              "detector": verdict})

    out = ROOT / "docs" / "kappa_sheet.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    (ROOT / "docs" / "kappa_sheet_calc.json").write_text(
        json.dumps(rows_for_calc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"校准表已生成：{out}（{len(picks)} 张卡片）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
