"""B13 报告 CLI：从 runs.jsonl 直接生成批次报告（无需先入 DuckDB）。

与 backend.analysis.report（quick 档、DuckDB 口径）互补：
- 数据源 = 批次目录的 runs.jsonl（跑完即可报，含未入库批次）；
- 修正口径：run_id 去重（保留最新）、渠道死单列（token 全 0 + timeout/error）；
- 输出 = 臂间对照表 + 成本表 + 活动性分布 + 判定一句话 + report.md 落盘。

用法：
    python -m backend.analysis.cli_report results/poolv3d-streamkit-a0
    python -m backend.analysis.cli_report results/poolv3d-streamkit-a0 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


def load_runs(batch: Path) -> list[dict]:
    f = batch / "runs.jsonl"
    if not f.exists():
        return []
    latest: dict[str, dict] = {}
    for line in f.open(encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            latest[r.get("run_id", "?")] = r
    return list(latest.values())


def is_channel_dead(r: dict) -> bool:
    zero = not (r.get("input_tokens") or r.get("output_tokens"))
    return zero and ("timeout" in str(r.get("error", "")) or "error" in r
                     or r.get("dead"))


def arm_stats(rows: list[dict]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r.get("arm", "?")].append(r)
    out = {}
    for arm, rs in sorted(groups.items()):
        ch = sum(1 for r in rs if is_channel_dead(r))
        valid = [r for r in rs if not is_channel_dead(r)]
        scores = [r["score"] for r in valid if isinstance(r.get("score"), (int, float))]
        out[arm] = {
            "n_total": len(rs), "n_valid": len(valid), "channel_dead": ch,
            "mean_score": sum(scores) / len(scores) if scores else None,
            "mean_turns": (sum(r.get("num_turns", 0) for r in valid) / len(valid)) if valid else 0,
            "mean_wall_s": (sum(r.get("wall_s", 0) for r in valid) / len(valid)) if valid else 0,
            "mean_out_tok": (sum(r.get("output_tokens", 0) for r in valid) / len(valid)) if valid else 0,
            "cost_usd": sum(r.get("cost_usd", 0) for r in rs),
        }
    return out


def verdict(stats: dict[str, dict]) -> str:
    """判定一句话：主对照臂对（优先 A1f-conv/A1f vs A0）方向 + 成本。"""
    a0 = stats.get("A0", {})
    a1 = stats.get("A1f-conv") or stats.get("A1f") or {}
    if not a0 or not a1 or a0.get("mean_score") is None or a1.get("mean_score") is None:
        return "样本不足，无法判定（补齐有效 run 后重报）"
    d = a1["mean_score"] - a0["mean_score"]
    cost_d = a1["mean_out_tok"] / a0["mean_out_tok"] if a0["mean_out_tok"] else 0
    direction = "正收益" if d > 0.1 else ("负收益" if d < -0.1 else "零增益")
    placebo = ""
    if "A0p" in stats and stats["A0p"].get("mean_score") is not None:
        dp = stats["A0p"]["mean_score"] - a0["mean_score"]
        placebo = f"；安慰剂差 {dp:+.3f}" + ("（长度效应排除）" if abs(dp) <= 0.15 else "（注意注意力效应）")
    return (f"{direction}：Skill 臂均分 {a1['mean_score']:.3f} vs A0 {a0['mean_score']:.3f}"
            f"（Δ{d:+.3f}），成本比 ×{cost_d:.2f}{placebo}")


def render(batch_id: str, rows: list[dict], stats: dict[str, dict]) -> str:
    L = [f"# 批次报告 — {batch_id}", ""]
    L.append(f"run 总数 {len(rows)}（去重后）｜生成于 backend.analysis.cli_report")
    L += ["", "## 臂间对照", "",
          "| 臂 | n(有效/总) | 渠道死 | 均分 | 均轮次 | 均墙钟s | 均出token | 成本$ |",
          "|---|---|---|---|---|---|---|---|"]
    for arm, s in stats.items():
        ms = f"{s['mean_score']:.3f}" if s["mean_score"] is not None else "—"
        L.append(f"| {arm} | {s['n_valid']}/{s['n_total']} | {s['channel_dead']} | {ms} | "
                 f"{s['mean_turns']:.1f} | {s['mean_wall_s']:.0f} | {s['mean_out_tok']:.0f} | "
                 f"{s['cost_usd']:.3f} |")
    L += ["", "## 判定", "", verdict(stats), ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("batch", help="批次目录（如 results/poolv3d-streamkit-a0）")
    ap.add_argument("--json", dest="as_json", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    batch = Path(args.batch)
    rows = load_runs(batch)
    if not rows:
        print(f"无 runs.jsonl：{batch}")
        return 1
    stats = arm_stats(rows)
    if args.as_json:
        print(json.dumps({"batch": batch.name, "stats": stats,
                          "verdict": verdict(stats)}, ensure_ascii=False, indent=1))
        return 0
    md = render(batch.name, rows, stats)
    out = Path(args.out) if args.out else batch / "report.md"
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"\n（已写入 {out}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
