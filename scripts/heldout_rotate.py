"""heldout 轮换工具化（B12）：dev/heldout 分离校验 + 四关 + 指针轮换。

三个子命令覆盖轮换生命周期（改名式轮换在安全沙箱下不可行——指针式替代）：
  check                dev/heldout 分离校验：族名/task_id 不重合 + heldout
                       未被任何 dev 矩阵预设引用（防"对迭代任务过拟合"）
  validate [dir]       四关校验 heldout 目录（默认 tasks/heldout）
  rotate <new_dir>     指针轮换：tasks/HELDOUT_CURRENT.txt 指向新目录
                       （当前激活集 = 指针内容；历史集自动失活，永不复用）

用法：
    python scripts/heldout_rotate.py check
    python scripts/heldout_rotate.py validate tasks/heldout-v2
    python scripts/heldout_rotate.py rotate tasks/heldout-v2
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POINTER = ROOT / "tasks" / "HELDOUT_CURRENT.txt"
PY = sys.executable


def load_task_ids(d: Path) -> set[str]:
    import yaml
    ids = set()
    for mp in d.glob("*/meta.yaml"):
        try:
            m = yaml.safe_load(mp.read_text(encoding="utf-8"))
            if m and m.get("task_id"):
                ids.add(m["task_id"])
        except Exception:  # noqa: BLE001
            continue
    return ids


def current_heldout() -> Path:
    if POINTER.exists():
        return ROOT / "tasks" / POINTER.read_text(encoding="utf-8").strip()
    return ROOT / "tasks" / "heldout"


def cmd_check() -> int:
    hdir = current_heldout()
    heldout_ids = load_task_ids(hdir)
    dev_ids: set[str] = set()
    for d in ("tasks/generated", "tasks/pool-v2", "tasks/pilot2", "tasks/families"):
        p = ROOT / d
        if p.exists():
            dev_ids |= load_task_ids(p)
    overlap = heldout_ids & dev_ids
    # 矩阵引用检查：heldout 只允许被终验类预设引用
    # （heldout-final 专用 + standard/full 的终验模块，MATRIX_TIERS 设计如此）；
    # quick/quick-lite 等迭代分诊预设引用 = 污染。
    ALLOWED_PREFIX = ("heldout",)
    ALLOWED_EXACT = {"standard.yaml", "full.yaml"}
    refs, violations = [], []
    for y in (ROOT / "matrix").glob("*.yaml"):
        txt = y.read_text(encoding="utf-8")
        if hdir.name in txt or "tasks/heldout" in txt:
            refs.append(y.name)
            if not (y.name.startswith(ALLOWED_PREFIX) or y.name in ALLOWED_EXACT):
                violations.append(y.name)
    ok = not overlap and not violations
    print(f"激活 heldout：{hdir}（{len(heldout_ids)} 实例）")
    print(f"与 dev 池 task_id 重合：{sorted(overlap) if overlap else '无 ✓'}")
    print(f"终验类引用（合规）：{refs if refs else '无'}")
    print(f"迭代预设引用（污染）：{violations if violations else '无 ✓'}")
    print(f"分离校验：{'✅ 通过' if ok else '❌ 未过——heldout 已被污染，必须轮换'}")
    return 0 if ok else 1


def cmd_validate(d: Path) -> int:
    return subprocess.run([PY, "-m", "backend.validators.task_validator", str(d)],
                          cwd=ROOT).returncode


def cmd_rotate(new_dir: Path) -> int:
    if not new_dir.exists():
        print(f"✗ 目录不存在：{new_dir}")
        return 1
    rc = cmd_validate(new_dir)
    if rc != 0:
        print("✗ 新 heldout 四关未过，不轮换")
        return rc
    old = current_heldout()
    POINTER.write_text(new_dir.name + "\n", encoding="utf-8")
    print(f"✓ 轮换完成：{old.name} → {new_dir.name}（指针 {POINTER.name}）")
    print("  旧集失活永不复用；跑 heldout 终验时 --tasks 用指针指向的目录")
    return cmd_check()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check", "validate", "rotate"])
    ap.add_argument("dir", nargs="?", default=None)
    args = ap.parse_args()
    if args.cmd == "check":
        return cmd_check()
    d = Path(args.dir) if args.dir else current_heldout()
    if args.cmd == "validate":
        return cmd_validate(d)
    return cmd_rotate(d)


if __name__ == "__main__":
    sys.exit(main())
