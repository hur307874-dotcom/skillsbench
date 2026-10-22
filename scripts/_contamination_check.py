"""越界访问检测器：扫描批次 trace，找出 agent 读取 run repo 以外路径的行为。

用途：
1) docker 沙箱落地前，审计历史批次是否被搜盘泄题污染（pool-v2/v3 都查）；
2) docker 沙箱落地后，作为冒烟测试的一部分（容器内应 0 命中）。

用法：python scripts/_contamination_check.py <batch_dir> [<batch_dir2> ...]
输出：每个 run 的越界工具调用数 + 前几条例证；末尾给批次汇总。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SENSITIVE = ("skills/", "tasks/", "docs/", ".workbuddy", "skillbench-v3-secure",
             "results/", "solution", "test_convention", "INTENT.md", "/tmp/skillbench",
             "AppData")


def scan_trace(tp: Path, repo_marker: str) -> list[str]:
    hits = []
    try:
        for line in tp.open(encoding="utf-8", errors="replace"):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") != "tool_execution_start":
                continue
            args = str(e.get("args", "")).replace("\\", "/")
            for pat in SENSITIVE:
                if pat in args and repo_marker not in args:
                    hits.append(f"{e.get('toolName')}: {args[:130]}")
                    break
            else:
                # 绝对路径跳出 repo（D:/、C:/、/d/、/c/ 开头但不含 repo 标记）
                for tok in ("D:/", "C:/", "/d/", "/c/"):
                    if tok in args and repo_marker not in args:
                        hits.append(f"{e.get('toolName')}: {args[:130]}")
                        break
    except FileNotFoundError:
        pass
    return hits


def scan_batch(batch: Path) -> tuple[int, int, list[str]]:
    work = batch / "work"
    runs = contaminated = 0
    samples: list[str] = []
    if not work.exists():
        return 0, 0, [f"{batch.name}: 无 work 目录"]
    for rd in sorted(work.iterdir()):
        if not rd.is_dir():
            continue
        runs += 1
        hits = scan_trace(rd / "trace.json", rd.name)
        if hits:
            contaminated += 1
            samples.append(f"  {rd.name}: {len(hits)} 次越界 | 例: {hits[0]}")
    return runs, contaminated, samples


def main() -> None:
    for arg in sys.argv[1:]:
        b = Path(arg)
        runs, bad, samples = scan_batch(b)
        print(f"== {b.name}: {runs} runs, {contaminated} 个越界 ==" if False
              else f"== {b.name}: {runs} runs, {bad} 个越界 ==")
        for s in samples[:8]:
            print(s)
        if len(samples) > 8:
            print(f"  ... 另 {len(samples)-8} 个")


if __name__ == "__main__":
    main()
