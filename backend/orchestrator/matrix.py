"""矩阵展开器：把 matrix/*.yaml 预设展开成 run 清单 + 时间/成本估算。

用法：
    python -m backend.orchestrator.matrix matrix/quick-lite.yaml
    python -m backend.orchestrator.matrix matrix/standard.yaml --out runs.jsonl

预设两种形态：
1. 分诊档（quick-lite / quick）：顶层 arms + tasks + repeats；
2. 确诊档（standard / full）：分节（main_matrix / a1_noref / ablation / ...），
   manifest 驱动的节（ablation）在 manifest 缺失时只给数量估算。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DIFFICULTIES = ("D1", "D2", "D3")
DEFAULT_MIN_PER_RUN = {"D1": 3.5, "D2": 10.0, "D3": 20.0}
DEFAULT_TOK_PER_RUN = {"D1": 40_000, "D2": 150_000, "D3": 400_000}


@dataclass
class Task:
    task_id: str
    difficulty: str
    path: Path


@dataclass
class Run:
    run_id: str
    section: str
    task_id: str
    difficulty: str
    arm: str
    inject: str
    rep: int
    arm_skill: str = ""  # 臂级 Skill 目录（消融臂用），空 = 用全局 --skill


def scan_tasks(tasks_dir: Path) -> list[Task]:
    out = []
    for meta_path in sorted(tasks_dir.glob("*/meta.yaml")):
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
        out.append(Task(meta["task_id"], meta["difficulty"], meta_path.parent))
    return out


def select_tasks(tasks: list[Task], per_difficulty: int | None = None,
                 cap: dict | None = None, total: int | None = None,
                 dev_subset: int | None = None,
                 only: list[str] | None = None) -> tuple[list[Task], list[str]]:
    """按难度档配额选取；返回（选中任务, 告警列表）。dev_subset = 前 N 个（模拟 dev 子集）。
    only = 显式 task_id 清单（优先于其他选择方式，保持清单顺序）。"""
    warns: list[str] = []
    if only is not None:
        by_id = {t.task_id: t for t in tasks}
        missing = [i for i in only if i not in by_id]
        if missing:
            warns.append(f"only 清单中的任务不存在: {missing}")
        return [by_id[i] for i in only if i in by_id], warns
    if dev_subset is not None:
        return tasks[:dev_subset], warns
    if per_difficulty is not None:
        picked: list[Task] = []
        for d in DIFFICULTIES:
            pool = [t for t in tasks if t.difficulty == d]
            n = per_difficulty
            if cap and d in cap:
                n = min(n, cap[d])
            if len(pool) < n:
                warns.append(f"{d} 档只有 {len(pool)} 个任务（配额 {n}），按现有数量取")
            picked.extend(pool[:n])
        return picked, warns
    if total is not None:
        if len(tasks) < total:
            warns.append(f"任务总数 {len(tasks)} < 预设 {total}，按现有数量取")
        return tasks[:total], warns
    return tasks, warns


def expand(section: str, arms: list[dict], tasks: list[Task], repeats: int) -> list[Run]:
    runs = []
    for t in tasks:
        for a in arms:
            for r in range(1, repeats + 1):
                runs.append(Run(
                    run_id=f"{t.task_id}-{a['id']}-r{r:02d}",
                    section=section, task_id=t.task_id, difficulty=t.difficulty,
                    arm=a["id"], inject=a.get("inject", ""), rep=r,
                    arm_skill=a.get("skill", "")))
    return runs


def estimate(runs: list[Run], min_per: dict, tok_per: dict, concurrency: int) -> dict:
    minutes = sum(min_per.get(r.difficulty, 10.0) for r in runs)
    tokens = sum(tok_per.get(r.difficulty, 150_000) for r in runs)
    return {
        "runs": len(runs),
        "agent_minutes": round(minutes, 1),
        "wall_clock_min": math.ceil(minutes / max(concurrency, 1)),
        "tokens_est": tokens,
    }


def expand_preset(preset: dict, tasks_dir: Path) -> tuple[list[Run], dict, list[str]]:
    all_tasks = scan_tasks(tasks_dir)
    warns: list[str] = []
    runs: list[Run] = []
    section_est: dict = {}

    min_per = (preset.get("estimate", {}) or {}).get("minutes_per_run", DEFAULT_MIN_PER_RUN)
    tok_per = (preset.get("estimate", {}) or {}).get("token_per_run", DEFAULT_TOK_PER_RUN)
    conc = preset.get("concurrency", 10)

    if "arms" in preset:  # 分诊档形态
        sel, w = select_tasks(
            all_tasks,
            per_difficulty=preset["tasks"].get("per_difficulty"),
            only=preset["tasks"].get("only"),
            cap=preset["tasks"].get("per_difficulty_cap"))
        warns += w
        runs = expand("main", preset["arms"], sel, preset.get("repeats", 1))
        section_est["main"] = estimate(runs, min_per, tok_per, conc)
        return runs, section_est, warns

    # 确诊档形态：分节
    mm = preset["main_matrix"]
    sel, w = select_tasks(all_tasks, total=mm["tasks"].get("total"))
    warns += w
    r = expand("main_matrix", mm["arms"], sel, mm.get("repeats", 1))
    runs += r
    section_est["main_matrix"] = estimate(r, min_per, tok_per, conc)

    for name in ("a1_noref", "a2_loop", "model_gradient", "codex_matrix", "generality"):
        sec = preset.get(name)
        if not sec:
            continue
        tsel = sel if sec.get("tasks") == "all_main" else select_tasks(
            sel, dev_subset=(sec.get("tasks") or {}).get("dev_subset"))[0]
        r = expand(name, sec["arms"], tsel, sec.get("repeats", 1))
        runs += r
        section_est[name] = estimate(r, min_per, tok_per, conc)

    abl = preset.get("ablation")
    if abl:
        # manifest 缺失时按 7 条指令估算（PLAN §4.3 的 tdd manifest 规模）
        n_instr = abl.get("instructions_est", 7)
        n_vt = abl.get("verify_tasks_per_instruction", 4)
        rep = abl.get("repeats", 2)
        n = n_instr * n_vt * rep
        section_est["ablation"] = {"runs": n, "note": f"估算：{n_instr} 指令 × {n_vt} verify_tasks × n={rep}（待 manifest 展开）"}
        warns.append("ablation 节按指令数估算，未逐条展开（需 manifest）")

    needle = preset.get("needle_calibration")
    if needle:
        section_est["needle_calibration"] = {"runs": needle.get("runs", 20), "note": "埋针校准小矩阵"}

    return runs, section_est, warns


def main() -> int:
    ap = argparse.ArgumentParser(prog="skill-bench matrix")
    ap.add_argument("preset", help="matrix/*.yaml 预设")
    ap.add_argument("--tasks", default="tasks/generated", help="任务目录")
    ap.add_argument("--out", help="导出 run 清单 jsonl")
    args = ap.parse_args()

    preset = yaml.safe_load(Path(args.preset).read_text(encoding="utf-8"))
    runs, section_est, warns = expand_preset(preset, Path(args.tasks))

    total_runs = sum(v["runs"] for v in section_est.values())
    print(f"预设：{preset['name']} — {preset.get('description', '')}")
    print(f"任务目录：{args.tasks}\n")
    for name, est in section_est.items():
        line = f"  {name:22s} {est['runs']:>4d} run"
        if "wall_clock_min" in est:
            line += f"   墙钟 ~{est['wall_clock_min']} min（agent 时 {est['agent_minutes']} min / 并发 {preset.get('concurrency', 10)}）"
        if "note" in est:
            line += f"   [{est['note']}]"
        print(line)
    print(f"\n合计 ≈ {total_runs} run")
    for w in warns:
        print(f"⚠️  {w}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for r in runs:
                f.write(json.dumps(r.__dict__, ensure_ascii=False) + "\n")
        print(f"\nrun 清单已导出：{args.out}（{len(runs)} 条）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
