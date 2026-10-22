"""κ 回归套件（B3 补给线③）：20 张人工标注卡自动重放。

每次改检测器后运行：把 20 卡的 run 重新过当前归因管线（含 B15 活动性门），
与 docs/kappa_labels.json 的人工标签对比。
验收标准（v2-activity-gate）：
- 7 条历史误报（卡 1/2/3/4/5/7/8）必须零 F-ID 命中；
- 卡 6 的 F05 必须保留（唯一被人工认可的阳性）；
- 全部 20 卡机器结论 == 人工标签 → κ=1.0（重放口径）。

用法：python scripts/kappa_replay.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.attribution.engine import (attribute_run, load_events,
                                        load_run_records, load_sites_required,
                                        load_fids)

CARDS_FILE = ROOT / "docs" / "kappa_labels.json"


def main() -> int:
    data = json.loads(CARDS_FILE.read_text(encoding="utf-8"))
    cards = data["labels"]
    fids = load_fids()
    sites_map = load_sites_required()

    rows = []
    for c in cards:
        batch, run_id = c["batch"], c["run"]
        events_by_run = load_events([run_id], batch)
        evs = events_by_run.get(run_id, [])
        recs = load_run_records(batch)
        rec = recs.get(run_id)
        sr = sites_map.get(rec["task_id"], 1) if rec else 1
        r = attribute_run(run_id, evs, rec, sr, fids)
        machine = "无罪"
        if r["hits"]:
            machine = r["hits"][0]["f_id"]
        elif r.get("activity") != "ok":
            machine = f"({r['activity']})"
        rows.append({
            "card": c["card"], "run": run_id, "batch": batch,
            "detector_v1": c["detector"], "human": c["human"],
            "machine_v2": machine,
            "was_fp": c["detector"] != c["human"],
        })

    print(f"{'卡':>3} {'v1 机器':>7} {'人工':>5} {'v2 机器':>12}  结果")
    NO_FID = {"无罪", "(no_edit)", "(channel_dead)"}
    fp_fixed = fp_total = kept_pos = 0
    for r in rows:
        no_fid_now = r["machine_v2"] in NO_FID
        agree = (r["machine_v2"] == r["human"]) or (r["human"] == "无罪" and no_fid_now)
        if r["was_fp"]:
            fp_total += 1
            fp_fixed += no_fid_now
            verdict = "✓ 误报已消除" if no_fid_now else "✗ 仍误报"
        else:
            kept_pos += agree
            verdict = "✓ 一致" if agree else f"✗ 不一致（应为 {r['human']}）"
        print(f"{r['card']:>3} {r['detector_v1']:>7} {r['human']:>5} "
              f"{r['machine_v2']:>12}  {verdict}")

    print(f"\n历史误报消除：{fp_fixed}/{fp_total}（要求 7/7）")
    print(f"原一致卡保持：{kept_pos}/{len(rows) - fp_total}")
    passed = fp_fixed == fp_total == 7 and kept_pos == len(rows) - fp_total
    print(f"回归判定：{'✅ 通过（v2 可发布，建议复标小轮确认 κ）' if passed else '❌ 未通过'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
