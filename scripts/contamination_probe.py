"""N1 训练污染探针（2026-10-05）：扰动变体对照。

原理（SWE-bench 金丝雀思想的 lite 版）：
- 把模型已满分的任务做"行为等价但表面扰动"的变体（重命名内部标识符，
  公共 API 冻结——测试只引用公共面）；
- A0 跑变体：分数若与原体持平 → 满分是真能力（饱和，设计预期）；
  若显著塌落 → 存在"认出熟悉形状"的成分（背题/模式记忆，池被污染）。
- 注意：内置题是合成的（不在公开语料），逐字背题先验不可能；
  本探针测的是"模式记忆/形状识别"这一弱形态。

用法：python scripts/contamination_probe.py  （生成变体 +  sanity 校验 + 打印跑批命令）
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / "tasks" / "probe-contam"
PY = sys.executable

# 任务 → 标识符重命名表（公共 API 不动；fixture 内全局替换）
RENAMES = {
    "d3-state-hard": {
        "_cache": "_kv_store",
        "_DB": "_PRICE_DB",
        "cached_price": "read_through",
        "invalidate": "evict_entry",
    },
    "d2-config-hard": {
        "get_timeout": "fetch_timeout_ms",
    },
}


def build_variants() -> list[str]:
    made = []
    for task, table in RENAMES.items():
        src = ROOT / "tasks" / "generated" / task
        dst = DST / f"{task}-p"
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True)
        # fixture 全文重命名
        fx_dst = dst / "fixture"
        shutil.copytree(src / "fixture", fx_dst)
        for f in fx_dst.rglob("*.py"):
            t = f.read_text(encoding="utf-8")
            for old, new in table.items():
                t = t.replace(old, new)
            f.write_text(t, encoding="utf-8", newline="\n")
        # tests 原样（公共面未动，行为等价）
        shutil.copytree(src / "tests", dst / "tests")
        # meta：task_id 换名
        meta = (src / "meta.yaml").read_text(encoding="utf-8")
        meta = meta.replace(task, f"{task}-p")
        (dst / "meta.yaml").write_text(meta, encoding="utf-8", newline="\n")
        made.append(f"{task}-p")
        print(f"  ✓ 变体 {task}-p（重命名 {list(table)}）")
    return made


def sanity(tasks: list[str]) -> bool:
    """变体的 bug 必须还在（fixture 直接跑 pytest 应当失败）。"""
    ok = True
    for t in tasks:
        d = DST / t
        p = subprocess.run([PY, "-m", "pytest", str(d / "tests"), "-x", "-q"],
                           cwd=d / "fixture", capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        failed = "failed" in (p.stdout + p.stderr)
        print(f"  {t}: fixture 上测试{'如期失败 ✓' if failed else '❌ 竟然通过（扰动破坏了 bug）'}")
        ok = ok and failed
    return ok


def main() -> int:
    print("== 1. 生成扰动变体 ==")
    tasks = build_variants()
    print("== 2. sanity（bug 必须还在）==")
    if not sanity(tasks):
        return 1
    preset = ROOT / "matrix" / "probe-contam.yaml"
    preset.write_text(f"""name: probe-contam
description: "N1 污染探针：扰动变体 A0 对照"
arms:
  - {{ id: A0, inject: none }}
tasks:
  source: tasks/probe-contam
  only: [{", ".join(tasks)}]
repeats: 2
model: deepseek-v4.1-flash
timeout_min: 12
concurrency: 4
""", encoding="utf-8")
    print(f"== 3. 跑批 ==\n  python -m backend.orchestrator.runner {preset} --driver pi-docker --batch probe-contam")
    return 0


if __name__ == "__main__":
    sys.exit(main())
