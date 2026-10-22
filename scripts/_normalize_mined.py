"""把方向检测合格/可归一的 mined 任务规范化进 tasks/generated（2026-10-09）。

- exactly_n（A 类合格）：整目录复制，补 meta。
- substrings（B 类方向反）：bug 态 = fixture+patch；gold = 用 git diff --no-index
  生成的"bug→fix"正向 patch；四关验证（bug 态挂 + 正向 patch 后过）再入库。
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PY = sys.executable
BS = chr(92)
GEN = Path("tasks/generated")


def counts(cwd, tests):
    r = subprocess.run([PY, "-m", "pytest", str(tests), "-q", "--no-header"],
                       cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    out = r.stdout + r.stderr
    f = re.search(r"(\d+) failed", out)
    p = re.search(r"(\d+) passed", out)
    return (int(f.group(1)) if f else 0), (int(p.group(1)) if p else 0)


def norm_patch_text(p: Path) -> str:
    return p.read_text(encoding="utf-8").replace("more_itertools" + BS, "more_itertools/")


def meta_for(name: str, func: str) -> str:
    return f"""task_id: {name}
difficulty: D3
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  more_itertools 包的 `{func}` 功能在某些输入上行为不符合预期
  （维护者收到的回归报告）。请复现问题、定位根因并修复，
  保持包内其他 API 行为不变。
"""


def copy_in(src: Path, name: str, func: str) -> None:
    dst = GEN / name
    shutil.copytree(src, dst, dirs_exist_ok=True)
    (dst / "meta.yaml").write_text(meta_for(name, func), encoding="utf-8", newline="\n")
    print(f"  ✓ 入库 {name}")


def main() -> int:
    # ① exactly_n（A 类）：直接入库
    src = Path("tasks/pool-v2-mined/moreitertools-exactly_n-1080-10-174020")
    copy_in(src, "mined-exactly_n", "exactly_n")

    # ② substrings（B 类）：归一后入库
    src2 = Path("tasks/pool-v2-mined/moreitertools-substrings-1080-01-173557").resolve()
    ptxt = norm_patch_text(next((src2 / "solution" / "sites").glob("*.patch")))
    with tempfile.TemporaryDirectory() as tmp:
        bugfx = Path(tmp) / "bugfx"
        shutil.copytree(src2 / "fixture", bugfx)
        (bugfx / "_b.patch").write_text(ptxt, encoding="utf-8", newline="\n")
        ap = subprocess.run(["git", "apply", "_b.patch"], cwd=bugfx,
                            capture_output=True, text=True)
        assert ap.returncode == 0, f"bug 注入失败: {ap.stderr[:80]}"
        ff, _ = counts(bugfx, src2 / "tests")
        assert ff > 0, f"归一后 fixture 不挂，归一失败"

        # 正向 gold：bug 态 vs 修复态（原 fixture）的 diff
        rel = "more_itertools/more.py"
        diff = subprocess.run(
            ["git", "diff", "--no-index", "--src-prefix=a/", "--dst-prefix=b/",
             str(bugfx / rel), str(src2 / "fixture" / rel)],
            capture_output=True, text=True).stdout
        assert diff.strip(), "正向 diff 为空"
        # git diff --no-index 输出的路径是绝对路径，改写成 a/more_itertools/more.py 形式
        lines = []
        for ln in diff.splitlines():
            if ln.startswith("--- ") or ln.startswith("+++ "):
                ln = ("--- a/" + rel) if ln.startswith("---") else ("+++ b/" + rel)
            lines.append(ln)
        forward = "\n".join(lines) + "\n"

        # 四关：bug 态 + 正向 patch → 必须全过
        (bugfx / "_f.patch").write_text(forward, encoding="utf-8", newline="\n")
        ap2 = subprocess.run(["git", "apply", "_f.patch"], cwd=bugfx,
                             capture_output=True, text=True)
        assert ap2.returncode == 0, f"正向 patch 不适用: {ap2.stderr[:80]}"
        gf, gp = counts(bugfx, src2 / "tests")
        assert gf == 0 and gp > 0, f"正向 patch 后仍挂（{gf}F/{gp}P）"

        dst = GEN / "mined-substrings"
        # 重新造 bug 态（bugfx 已被正向 patch 修复，重来）
        shutil.copytree(src2 / "fixture", dst, ignore=shutil.ignore_patterns("_*.patch"), dirs_exist_ok=True)
        (dst / "_b.patch").write_text(ptxt, encoding="utf-8", newline="\n")
        subprocess.run(["git", "apply", "_b.patch"], cwd=dst,
                       capture_output=True, text=True, check=True)
        (dst / "_b.patch").unlink()
        shutil.copytree(src2 / "tests", dst / "tests", dirs_exist_ok=True)
        (dst / "solution" / "sites").mkdir(parents=True, exist_ok=True)
        (dst / "solution" / "sites" / "site-01.patch").write_text(
            forward, encoding="utf-8", newline="\n")
        (dst / "meta.yaml").write_text(
            meta_for("mined-substrings", "substrings"), encoding="utf-8", newline="\n")
        print(f"  ✓ 入库 mined-substrings（归一：bug 态 {ff}F → 正向 gold 后 {gp}P）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
