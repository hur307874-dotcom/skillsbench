"""dry-run 端到端管线：mock agent + 真实 pytest 判分。

用途（对应 PLAN A5 的"假 run 数据端到端"）：
不烧 API，验证 矩阵展开 → 执行 → 判分 → 汇总 全链路正确性。
mock agent 按臂模拟不同行为（确定性、可复现）：
  - A0 / A0p（无 Skill）：只修第一处（模拟 F05"修一处就收工"）
  - A1f（强制注入）：修全部处；D1 档额外记录幻影用户浪费（模拟 I1 有害）
判分走真实隐藏 pytest（复用 validators 的 _run_pytest），不是假分数。

用法：
    python -m backend.orchestrator.dryrun matrix/quick-lite.yaml
    python -m backend.orchestrator.dryrun matrix/quick.yaml --out results/dryrun-quick
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.orchestrator.matrix import expand_preset  # noqa: E402
from backend.validators.task_validator import _run_pytest  # noqa: E402

# mock agent 行为表：arm → (apply_patches, wasted_turns_on_D1, wasted_tokens_on_D1)
MOCK_BEHAVIOR = {
    "none":   ("first", 0, 0),       # 裸考：只修报错直指的第一处
    "placebo": ("first", 0, 0),      # 安慰剂：内容无效，同裸考
    "forced": ("all", 3, 2400),      # 带秘籍：改全；但 D1 上 I1 诱发幻影用户空转
    "auto":   ("all", 3, 2400),
    "forced_no_refs": ("all", 3, 2400),
}


def apply_patches(repo: Path, patches: list[Path], mode: str) -> int:
    """git apply 补丁。必须屏蔽外层 git 仓库发现（GIT_CEILING_DIRECTORIES），
    否则在 skill-bench 仓库内的工作目录中 git 会把补丁路径解析到外层仓库根，
    静默 Skip（exit=0 但没打上）。"""
    import os
    env = dict(os.environ)
    env["GIT_CEILING_DIRECTORIES"] = str(repo.parent.resolve())
    chosen = patches if mode == "all" else patches[:1]
    for p in chosen:
        proc = subprocess.run(["git", "apply", str(p.resolve())],
                              cwd=repo, capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            raise RuntimeError(f"git apply 失败 {p.name}: {proc.stderr.strip()[:200]}")
    return len(chosen)


def parse_pytest_score(summary: str) -> tuple[int, int, float]:
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", summary)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", summary)) else 0
    total = passed + failed
    return passed, failed, (passed / total if total else 0.0)


def run_one(run, task_dir: Path, python: str) -> dict:
    mode, wt_d1, wtok_d1 = MOCK_BEHAVIOR.get(run["inject"], ("first", 0, 0))
    patches = sorted((task_dir / "solution" / "sites").glob("*.patch"))
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="sb-dry-") as tmp:
        repo = Path(tmp) / "repo"
        shutil.copytree(task_dir / "fixture", repo)
        sites_fixed = apply_patches(repo, patches, mode)
        ok, summary = _run_pytest(repo, task_dir / "tests", python)
    passed, failed, score = parse_pytest_score(summary)
    wasted_turns = wt_d1 if run["difficulty"] == "D1" else 0
    wasted_tokens = wtok_d1 if run["difficulty"] == "D1" else 0
    return {
        **run, "score": score, "tests": f"{passed}/{passed+failed}",
        "sites_fixed": sites_fixed, "sites_required": len(patches),
        "wasted_turns": wasted_turns, "wasted_tokens": wasted_tokens,
        "duration_s": round(time.time() - t0, 2),
        "f_id_hits": (["F05"] if sites_fixed < len(patches) else []) +
                     (["F15"] if wasted_turns else []),
    }


def summarize(results: list[dict]) -> str:
    lines = ["# dry-run 汇总（mock agent + 真实 pytest 判分）", ""]
    arms = sorted({r["arm"] for r in results})
    lines.append("| 臂 | run 数 | 平均得分 | 通过率 | 幻影用户浪费 token（D1） |")
    lines.append("|----|--------|---------|--------|------------------------|")
    for a in arms:
        rs = [r for r in results if r["arm"] == a]
        avg = sum(r["score"] for r in rs) / len(rs)
        pr = sum(1 for r in rs if r["score"] == 1.0) / len(rs)
        wtok = sum(r["wasted_tokens"] for r in rs)
        lines.append(f"| {a} | {len(rs)} | {avg:.2f} | {pr:.0%} | {wtok} |")
    lines += ["", "## 逐任务配对（A1f − A0）", "",
              "| 任务 | 难度 | A0 得分 | A1f 得分 | 差值 | A1f 浪费轮次 |",
              "|------|------|--------|---------|------|-------------|"]
    tasks = sorted({r["task_id"] for r in results})
    for t in tasks:
        a0 = next((r for r in results if r["task_id"] == t and r["arm"] == "A0"), None)
        a1 = next((r for r in results if r["task_id"] == t and r["arm"] == "A1f"), None)
        if a0 and a1:
            lines.append(f"| {t} | {a0['difficulty']} | {a0['score']:.2f} | {a1['score']:.2f} "
                         f"| {a1['score']-a0['score']:+.2f} | {a1['wasted_turns']} |")
    lines += ["", "> mock 语义：A0 只修第一处（F05）；A1f 修全部但 D1 上 I1 诱发幻影用户（F15）。",
              "> 用于验证管线，不代表真实模型行为。"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(prog="skill-bench dryrun")
    ap.add_argument("preset")
    ap.add_argument("--tasks", default="tasks/generated")
    ap.add_argument("--out", help="输出目录（默认 results/dryrun-<preset>）")
    args = ap.parse_args()

    preset = yaml.safe_load(Path(args.preset).read_text(encoding="utf-8"))
    if "arms" not in preset:
        print("dry-run 目前只支持分诊档形态（quick-lite / quick）")
        return 1
    runs, _, warns = expand_preset(preset, Path(args.tasks))
    out_dir = Path(args.out or f"results/dryrun-{preset['name']}")
    out_dir.mkdir(parents=True, exist_ok=True)

    python = sys.executable
    results = []
    for r in runs:
        rec = run_one(r.__dict__ if hasattr(r, "__dict__") else r,
                      Path(args.tasks) / r.task_id, python)
        results.append(rec)
        print(f"[{rec['arm']:4s}] {rec['task_id']:14s} score={rec['score']:.2f} "
              f"tests={rec['tests']} sites={rec['sites_fixed']}/{rec['sites_required']} "
              f"wasted_turns={rec['wasted_turns']} f_id={rec['f_id_hits']}")

    with open(out_dir / "runs.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out_dir / "summary.md").write_text(summarize(results), encoding="utf-8")
    for w in warns:
        print(f"⚠️  {w}")
    print(f"\n输出：{out_dir}/runs.jsonl + summary.md（{len(results)} run）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
