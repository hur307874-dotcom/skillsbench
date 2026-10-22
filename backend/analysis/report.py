"""报告生成器：从 DuckDB 出 markdown 评测报告（quick 档口径）。

用法：
    python -m backend.analysis.report results/real-q1
    python -m backend.analysis.report results/real-q1 --out results/real-q1/report.md

quick 档口径（MATRIX_TIERS §1）：只报方向 + 逐任务符号，不报 CI；
必披露项自动写入报告（无 A1 真实触发 / 无 placebo / n 小无 CI）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.store.db import connect  # noqa: E402

DISCLOSURES = [
    "无 A1（自主触发）→ 收益为**内容上限**，真实收益 ≤ 此值",
    "无 A0p（placebo）→ 无法排除注意力效应",
    "样本量小（n≤2/格）→ 无 CI，只报方向 + 逐任务符号",
    "② 环「行为→结果」为观察性关联，非严格因果（消融臂为准实验佐证，确诊档提供）",
]


def _table(headers: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return out


def generate(batch_id: str) -> str:
    con = connect()
    L: list[str] = [f"# 评测报告 — 批次 {batch_id}", ""]

    runs = con.execute(
        "SELECT COUNT(*), SUM(cost_usd), AVG(score), AVG(wall_s) FROM runs WHERE batch_id = ?",
        [batch_id]).fetchone()
    L += [f"**规模**：{runs[0]} run | 总成本 ${runs[1]:.2f} | "
          f"平均得分 {runs[2]:.2f} | 平均墙钟 {runs[3]:.0f}s", ""]

    # 臂 × 难度
    L += ["## 1. 臂 × 难度对照", ""]
    rows = con.execute(
        "SELECT arm, difficulty, n, ROUND(avg_score,2), ROUND(pass_rate,2), "
        "ROUND(avg_cost,3), ROUND(avg_turns,1) FROM v_arm_stats WHERE batch_id = ?",
        [batch_id]).fetchall()
    L += _table(["臂", "难度", "n", "平均得分", "通过率", "平均成本$", "平均轮次"], rows)
    L.append("")

    # 配对差值
    L += ["## 2. 逐任务配对（A1f − A0）", ""]
    rows = con.execute(
        "SELECT task_id, difficulty, a0_score, a1f_score, ROUND(diff,2), "
        "ROUND(a0_cost,3), ROUND(a1f_cost,3), ROUND(cost_diff,3) "
        "FROM v_paired WHERE batch_id = ?", [batch_id]).fetchall()
    L += _table(["任务", "难度", "A0", "A1f", "差值", "A0$", "A1f$", "成本差$"], rows)
    pos = sum(1 for r in rows if (r[4] or 0) > 0)
    neg = sum(1 for r in rows if (r[4] or 0) < 0)
    cost_up = sum(1 for r in rows if (r[7] or 0) > 0)
    L += ["",
          f"**符号统计**：增益为正 {pos}/{len(rows)}，为负 {neg}/{len(rows)}；"
          f"成本上升 {cost_up}/{len(rows)}。", ""]

    # 行为信号
    L += ["## 3. 行为信号与 F-ID 命中", ""]
    sig_rows = con.execute(
        "SELECT run_id, name, f_id, wasted_turns, detail FROM signals "
        "WHERE batch_id = ? AND present", [batch_id]).fetchall()
    if sig_rows:
        L += _table(["run", "信号", "F-ID", "浪费轮次", "说明"], sig_rows)
    else:
        L += ["（无命中。注：summary 格式 trace 无 step 事件时检测器不报阴性，"
              "需 stream-json 事件流。）"]
    L.append("")

    # 披露
    L += ["## 4. 必披露项（quick 档口径）", ""]
    L += [f"- {d}" for d in DISCLOSURES]
    L += ["", "> 本报告由 report.py 从 traces.duckdb 自动生成；"
          "原始 trace 见各 run 的 raw_event_ref。", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(prog="skill-bench report")
    ap.add_argument("batch_dir")
    ap.add_argument("--out")
    args = ap.parse_args()
    batch_id = Path(args.batch_dir).name
    text = generate(batch_id)
    out = Path(args.out or Path(args.batch_dir) / "report.md")
    out.write_text(text, encoding="utf-8")
    print(f"报告已生成：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
