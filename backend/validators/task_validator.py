"""任务校验器：四条硬检查（TASK_FORMAT.md）。

用法：
    python -m backend.validators.task_validator tasks/<dir> [-v]

四条检查：
1. meta 完整（字段、sites_required 与补丁数一致、F-ID 存在）
2. gold 跑通（fixture + 全部补丁 → 测试全过）
3. 错解判负（wrong/ 每个目录 → 测试失败）
4. 逐处漏改有测试覆盖（fixture + 除 i 外补丁 → 测试失败）
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REQUIRED_META = ["task_id", "difficulty", "targets_fids", "sites_required", "forbidden_edits", "prompt"]
DIFFICULTIES = {"D1", "D2", "D3"}


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class TaskReport:
    task_dir: Path
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name, ok, detail))


def _run_pytest(repo: Path, tests: Path, python: str) -> tuple[bool, str]:
    """以 PYTHONPATH=repo 运行隐藏测试（不复制文件，避免任何删除操作）。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo.resolve()) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.run(
            [python, "-m", "pytest", str(tests.resolve()), "-q", "--no-header",
             "-p", "no:cacheprovider"],
            cwd=repo, env=env, capture_output=True, text=True, timeout=300,
        )
        tail = (proc.stdout + proc.stderr).strip().splitlines()
        summary = tail[-1] if tail else f"exit={proc.returncode}"
        return proc.returncode == 0, summary
    except subprocess.TimeoutExpired:
        return False, "pytest timeout (300s)"


def _prepare_repo(fixture: Path, patches: list[Path], skip: Path | None, tmp: Path) -> Path:
    """复制 fixture 并应用补丁（skip 指定的那个除外）。"""
    repo = tmp / "repo"
    shutil.copytree(fixture, repo)
    for p in patches:
        if p == skip:
            continue
        proc = subprocess.run(
            ["git", "apply", "--unidiff-zero", str(p.resolve())],
            cwd=repo, capture_output=True, text=True
        )
        if proc.returncode != 0:
            raise RuntimeError(f"git apply 失败 {p.name}: {proc.stderr.strip()[:200]}")
    return repo


def validate_task(task_dir: Path, python: str, fids: set[str]) -> TaskReport:
    rep = TaskReport(task_dir)
    meta_path = task_dir / "meta.yaml"
    fixture = task_dir / "fixture"
    tests = task_dir / "tests"
    sites_dir = task_dir / "solution" / "sites"
    wrong_dir = task_dir / "wrong"

    # 0. 目录结构
    for p, label in [(meta_path, "meta.yaml"), (fixture, "fixture/"),
                     (tests, "tests/"), (sites_dir, "solution/sites/")]:
        if not p.exists():
            rep.add("结构", False, f"缺少 {label}")
            return rep
    rep.add("结构", True)

    # 1. meta 完整
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_META if k not in meta]
    if missing:
        rep.add("meta 完整", False, f"缺字段: {missing}")
        return rep
    if meta["difficulty"] not in DIFFICULTIES:
        rep.add("meta 完整", False, f"difficulty 非法: {meta['difficulty']}")
        return rep
    unknown_fids = [f for f in meta["targets_fids"] if f not in fids]
    if unknown_fids:
        rep.add("meta 完整", False, f"未知 F-ID: {unknown_fids}")
        return rep
    patches = sorted(sites_dir.glob("*.patch"))
    if meta["sites_required"] != len(patches):
        rep.add("meta 完整", False,
                f"sites_required={meta['sites_required']} 但补丁数={len(patches)}")
        return rep
    rep.add("meta 完整", True, f"{len(patches)} 处应改")

    # 2. gold 跑通
    try:
        with tempfile.TemporaryDirectory(prefix="sb-gold-") as tmp:
            repo = _prepare_repo(fixture, patches, None, Path(tmp))
            ok, out = _run_pytest(repo, tests, python)
    except RuntimeError as e:
        rep.add("gold 跑通", False, str(e))
        return rep
    rep.add("gold 跑通", ok, out)
    if not ok:
        return rep

    # 3. 错解判负
    if wrong_dir.exists():
        bad = []
        for w in sorted(wrong_dir.iterdir()):
            if not w.is_dir():
                continue
            ok, out = _run_pytest(w, tests, python)
            if ok:
                bad.append(w.name)
        rep.add("错解判负", not bad,
                f"未被判负: {bad}" if bad else f"{len(list(wrong_dir.iterdir()))} 个错解全部判负")
    else:
        rep.add("错解判负", True, "无 wrong/（可选）")

    # 4. 逐处漏改有测试覆盖
    uncovered = []
    for i, p in enumerate(patches, 1):
        with tempfile.TemporaryDirectory(prefix="sb-site-") as tmp:
            repo = _prepare_repo(fixture, patches, p, Path(tmp))
            ok, _ = _run_pytest(repo, tests, python)
        if ok:
            uncovered.append(p.name)
    rep.add("逐处漏改有测试覆盖", not uncovered,
            f"漏改仍通过: {uncovered}" if uncovered else f"{len(patches)} 处全部有测试盯着")

    return rep


def main() -> int:
    ap = argparse.ArgumentParser(prog="skill-bench validate-tasks")
    ap.add_argument("tasks", nargs="+", help="任务目录（可多个，也可为父目录）")
    ap.add_argument("--fids", default="failure_modes.yaml")
    args = ap.parse_args()

    fids_doc = yaml.safe_load(Path(args.fids).read_text(encoding="utf-8"))
    fids = {e["id"] for e in fids_doc}
    python = sys.executable

    task_dirs: list[Path] = []
    for t in args.tasks:
        p = Path(t)
        if (p / "meta.yaml").exists():
            task_dirs.append(p)
        else:
            task_dirs.extend(d for d in sorted(p.iterdir()) if (d / "meta.yaml").exists())

    all_ok = True
    for td in task_dirs:
        rep = validate_task(td, python, fids)
        all_ok &= rep.ok
        mark = "PASS" if rep.ok else "FAIL"
        print(f"[{mark}] {td}")
        for c in rep.checks:
            m = "  ✓" if c.ok else "  ✗"
            print(f"{m} {c.name}" + (f" — {c.detail}" if c.detail else ""))
    print(f"\n共 {len(task_dirs)} 个任务，{'全部通过' if all_ok else '存在不合格（拒绝入库）'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
