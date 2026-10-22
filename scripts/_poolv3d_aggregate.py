"""poolv3d 确认批聚合 + C7 判定（2026-10-04）。

修正历史口径错误（10-03 诊断）：
- 按 run_id 去重（重试保留最新一条）；
- dead_run 二分：usage 全 0 = 渠道死（剔除）；usage>0 = 合法无编辑（保留，计 0.4 保底）；
- C7 判定规则（NEXT_STEPS 写死）：
  n≥4/臂、非降级窗口（渠道死 <25%）、A0≤0.6、A0p≈A0（|Δ|≤0.15）、conv≥A0+0.2。

用法：python scripts/_poolv3d_aggregate.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

FAMS = ["streamkit", "deploykit", "fluxdb"]
ARMS = [("a0", "A0"), ("a0p", "A0p"), ("a1f", "A1f-conv")]


def load_batch(b: Path) -> list[dict]:
    f = b / "runs.jsonl"
    if not f.exists():
        return []
    latest: dict[str, dict] = {}
    for line in f.open(encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        latest[r.get("run_id", "?")] = r  # 重试保留最新
    return list(latest.values())


def classify(rows: list[dict]) -> tuple[list[dict], int]:
    """返回 (有效 run 列表, 渠道死数量)。"""
    valid, channel_dead = [], 0
    for r in rows:
        if r.get("dead"):
            usage_zero = not (r.get("input_tokens") or r.get("output_tokens"))
            if usage_zero or "timeout" in str(r.get("error", "")):
                channel_dead += 1
                continue
        if "timeout" in str(r.get("error", "")):
            channel_dead += 1
            continue
        valid.append(r)
    return valid, channel_dead


def main() -> None:
    base = Path("results")
    print(f"{'族':<12}{'臂':<10}{'n':>4}{'渠道死':>6}{'均分':>8}  分数")
    agg: dict[str, dict[str, tuple[int, float, list[float]]]] = defaultdict(dict)
    for fam in FAMS:
        for suffix, arm in ARMS:
            rows = load_batch(base / f"poolv3d-{fam}-{suffix}")
            valid, ch_dead = classify(rows)
            scores = [r["score"] for r in valid if isinstance(r.get("score"), (int, float))]
            mean = sum(scores) / len(scores) if scores else float("nan")
            agg[fam][arm] = (len(valid), mean, scores, ch_dead)
            print(f"{fam:<12}{arm:<10}{len(valid):>4}{ch_dead:>6}"
                  f"{mean:>8.3f}  {[round(s,2) for s in scores]}")

    print("\n===== C7 判定（规则：n≥4、渠道死<25%、A0≤0.6、|A0p−A0|≤0.15、conv≥A0+0.2）=====")
    verdicts = []
    for fam in FAMS:
        a_n, a_m, _, a_ch = agg[fam].get("A0", (0, float("nan"), [], 0))
        p_n, p_m, _, p_ch = agg[fam].get("A0p", (0, float("nan"), [], 0))
        c_n, c_m, _, c_ch = agg[fam].get("A1f-conv", (0, float("nan"), [], 0))
        total = a_n + a_ch + p_n + p_ch + c_n + c_ch
        ch_ratio = (a_ch + p_ch + c_ch) / total if total else 1.0
        checks = {
            "n≥4/臂": min(a_n, p_n, c_n) >= 4,
            "渠道死<25%": ch_ratio < 0.25,
            "A0≤0.6": a_m == a_m and a_m <= 0.6,
            "A0p≈A0": p_m == p_m and a_m == a_m and abs(p_m - a_m) <= 0.15,
            "conv≥A0+0.2": c_m == c_m and a_m == a_m and c_m >= a_m + 0.2,
        }
        ok = all(checks.values())
        verdicts.append(ok)
        mark = "✓ C7 成立" if ok else "✗ 未达线"
        detail = " ".join(f"{k}{'✓' if v else '✗'}" for k, v in checks.items())
        print(f"{fam:<12} A0={a_m:.3f} A0p={p_m:.3f} conv={c_m:.3f} "
              f"Δconv={c_m-a_m:+.3f} | {mark} | {detail}")
    print(f"\n总判定：{'C7 知识缺口处为正（三族齐证）' if all(verdicts) else 'C7 未证实（见各族细项）'}")


if __name__ == "__main__":
    main()
