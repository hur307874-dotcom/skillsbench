"""Pilot Gate 自动化 + 渠道健康聚合（POOL_V2 §8 常驻门禁的机械化）。

两职能：
1. pilot 批次 → 逐任务判定书：A0 裸考通过率落 [0.4, 0.8] 准入；
   >0.8 打回（天花板侧，登记为成本区分用）；<0.4 打回（地板，需降难度）；
   判定书自动回填任务 meta.baseline（幂等，不重复写）。
2. 渠道健康：批次中位 tps vs 全库历史中位 tps → 标记降级窗口；
   完成率类结论在降级窗口内必须挂"渠道存疑"标签（渠道混淆协议）。

用法：
    python -m backend.gate.pilot_gate results/pilot-multi-1 --arm A0
    python -m backend.gate.pilot_gate --health results/pool-v20-main
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
BAND = (0.4, 0.8)          # Pilot Gate 准入带（A0 裸考通过率）
HEALTH_RATIO = 0.5         # 批次中位 tps < 历史中位 × 此比例 → 降级窗口
DB = ROOT / "results" / "traces.duckdb"


def _load_batch(batch_dir: Path) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for l in (batch_dir / "runs.jsonl").read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l)
            by_id[r["run_id"]] = r
    return by_id


def gate_verdicts(batch_dir: Path, gate_arm: str = "A0") -> list[dict]:
    """逐任务判定：完成率口径（满分/总，含超时与死跑）。"""
    runs = _load_batch(batch_dir)
    tasks: dict[str, list[dict]] = {}
    for r in runs.values():
        if r["arm"] == gate_arm:
            tasks.setdefault(r["task_id"], []).append(r)
    out = []
    for tid, rs in sorted(tasks.items()):
        n = len(rs)
        full = sum(1 for r in rs if not r.get("dead") and "error" not in r
                   and r.get("score") == 1.0)
        rate = full / n if n else 0
        if BAND[0] <= rate <= BAND[1]:
            verdict, role = "准入", "带内（分数区分主力）"
        elif rate > BAND[1]:
            verdict, role = "带外-天花板", "天花板侧（成本区分用）"
        else:
            verdict, role = "带外-地板", "地板（需降难度或登记边界样本）"
        out.append({"task_id": tid, "n": n, "full": full,
                    "rate": round(rate, 3), "verdict": verdict, "role": role})
    return out


def backfill_baseline(verdicts: list[dict], model: str,
                      pool_dir: Path, dry: bool = False) -> int:
    """判定书回填 meta.baseline（幂等：已存在且值相同则跳过）。"""
    changed = 0
    for v in verdicts:
        mp = pool_dir / v["task_id"] / "meta.yaml"
        if not mp.exists():
            continue
        meta = yaml.safe_load(mp.read_text(encoding="utf-8"))
        bl = meta.get("baseline") or {}
        key = f"{model}-{gate_arm_key()}"
        entry = f"{v['rate']}  # pilot-gate 自动回填"
        if bl.get(key) == entry and bl.get("role") == v["role"]:
            continue
        bl[key] = entry
        bl["role"] = v["role"]
        meta["baseline"] = bl
        if not dry:
            mp.write_text(yaml.safe_dump(meta, allow_unicode=True, sort_keys=False),
                          encoding="utf-8")
        changed += 1
    return changed


def gate_arm_key() -> str:
    return "A0"


def channel_health(batch_dir: Path) -> dict:
    """批次渠道健康：中位 tps vs 全库历史中位（HEALTH_RATIO 阈值）。
    老记录无 tps 字段时用 output_tokens/wall_s 现算（同一物理量）。"""
    runs = list(_load_batch(batch_dir).values())
    tps_vals = []
    for r in runs:
        if r.get("tps"):
            tps_vals.append(r["tps"])
        elif r.get("wall_s") and r.get("output_tokens"):
            tps_vals.append(r["output_tokens"] / r["wall_s"])
    batch_med = sorted(tps_vals)[len(tps_vals) // 2] if tps_vals else None
    hist_med = None
    if DB.exists():
        con = duckdb.connect(str(DB), read_only=True)
        row = con.execute(
            "SELECT tps FROM runs WHERE tps IS NOT NULL AND tps > 0").fetchall()
        if row:
            vals = sorted(r[0] for r in row)
            hist_med = vals[len(vals) // 2]
    degraded = (batch_med is not None and hist_med is not None
                and batch_med < hist_med * HEALTH_RATIO)
    return {"batch": batch_dir.name, "batch_median_tps": batch_med,
            "historical_median_tps": hist_med,
            "degraded": degraded,
            "note": "降级窗口：完成率类结论须挂渠道存疑标签" if degraded
                    else "渠道健康：完成率类结论可采信"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("batch_dir", nargs="?", default=None)
    ap.add_argument("--arm", default="A0")
    ap.add_argument("--model", default="deepseek-v4.1-flash")
    ap.add_argument("--pool", default="tasks/pool-v2/forged-final")
    ap.add_argument("--backfill", action="store_true", help="回填 meta.baseline")
    ap.add_argument("--health", action="store_true", help="只跑渠道健康")
    args = ap.parse_args()

    if args.health:
        h = channel_health(Path(args.batch_dir))
        print(json.dumps(h, ensure_ascii=False, indent=1))
        return 0

    verdicts = gate_verdicts(Path(args.batch_dir), args.arm)
    print(f"Pilot Gate 判定书（批次 {Path(args.batch_dir).name}，臂 {args.arm}，"
          f"准入带 {BAND}）：")
    for v in verdicts:
        mark = "✅" if v["verdict"] == "准入" else "⛔"
        print(f"  {mark} {v['task_id']:32s} {v['rate']:.2f} ({v['full']}/{v['n']})"
              f" → {v['verdict']}｜{v['role']}")
    if args.backfill:
        n = backfill_baseline(verdicts, args.model, ROOT / args.pool)
        print(f"baseline 回填：{n} 个 meta 更新")
    h = channel_health(Path(args.batch_dir))
    print(f"渠道健康：批次中位 tps {h['batch_median_tps']} vs 历史 "
          f"{h['historical_median_tps']} → {h['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
