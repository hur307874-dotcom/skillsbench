"""真实任务挖掘器（任务池 v2 路径 A）：PyPI 版本对 → bugfix hunk → 任务候选。

原理：纯 Python 包的相邻小版本 diff 里，"只改已有函数体、不新增顶层定义"的
hunk 大概率是 bugfix——以旧版完整包为 fixture、bugfix hunk 为 gold、
新版测试中与该函数相关的测试为判分（判分标准来自真实开发者）。

用法：
    python scripts/mine_real_tasks.py more-itertools 11.0.1 11.0.2
    python scripts/mine_real_tasks.py cachetools 6.2.1 6.2.2 --out tasks/pool-v2

输出：tasks/pool-v2/<pkg>-<fn>-<oldver>/ 候选目录 + 终端打印评审摘要（prompt 需人工确认）。
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".mine_cache"
NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def download_sdist(pkg: str, ver: str) -> Path:
    dest_dir = CACHE / f"{pkg}-{ver}"
    if dest_dir.exists():
        return dest_dir
    data = json.load(NO_PROXY_OPENER.open(f"https://pypi.org/pypi/{pkg}/json", timeout=30))
    files = data["releases"].get(ver, [])
    urls = [f["url"] for f in files if f["packagetype"] == "sdist"]
    if not urls:
        raise SystemExit(f"{pkg} {ver} 无 sdist")
    tgz = CACHE / f"{pkg}-{ver}.tar.gz"
    req = urllib.request.Request(urls[0], headers={"User-Agent": "skill-bench-miner/1.0"})
    with NO_PROXY_OPENER.open(req, timeout=120) as r, open(tgz, "wb") as f:
        f.write(r.read())
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tgz) as t:
        t.extractall(dest_dir, filter="data")
    return dest_dir


def find_pkg_root(sdist_dir: Path) -> Path:
    """sdist 解压后定位包源码目录（src/ 或扁平布局）。"""
    subs = [p for p in sdist_dir.iterdir() if p.is_dir()]
    base = subs[0] if len(subs) == 1 else sdist_dir
    for cand in ("src",):
        if (base / cand).is_dir():
            inner = [p for p in (base / cand).iterdir() if p.is_dir()]
            if inner:
                return base / cand
    return base


def norm_ver(v: str) -> str:
    return v.replace(".", "").replace("-", "")


def diff_py_files(old_root: Path, new_root: Path) -> dict[str, list[str]]:
    """返回 {相对路径: unified diff 行}（仅 .py，仅两边都存在的文件）。"""
    diffs = {}
    old_map = {p.relative_to(old_root): p for p in old_root.rglob("*.py")}
    new_map = {p.relative_to(new_root): p for p in new_root.rglob("*.py")}
    for rel in sorted(old_map.keys() & new_map.keys()):
        old_lines = old_map[rel].read_text(encoding="utf-8", errors="replace").splitlines()
        new_lines = new_map[rel].read_text(encoding="utf-8", errors="replace").splitlines()
        if old_lines == new_lines:
            continue
        d = list(difflib.unified_diff(old_lines, new_lines, lineterm="",
                                      fromfile=f"a/{rel.as_posix()}",
                                      tofile=f"b/{rel.as_posix()}"))
        diffs[rel.as_posix()] = d  # 统一 POSIX 分隔符（git apply 不认 Windows 反斜杠）
    return diffs


def split_hunks(diff_lines: list[str]) -> list[list[str]]:
    hunks, cur = [], []
    for l in diff_lines:
        if l.startswith("@@"):
            if cur:
                hunks.append(cur)
            cur = [l]
        elif cur:
            cur.append(l)
    if cur:
        hunks.append(cur)
    return hunks


def hunk_is_bugfix(hunk: list[str]) -> bool:
    """不含新增顶层 def/class/__all__ 的 hunk 视为 bugfix 候选。"""
    for l in hunk:
        if l.startswith("+") and not l.startswith("+++"):
            body = l[1:]
            if re.match(r"^(def |class |async def )", body):
                return False
            if "__all__" in body:
                return False
    changed = sum(1 for l in hunk if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))
    return 0 < changed <= 40


def enclosing_func(old_lines: list[str], hunk: list[str]) -> str | None:
    m = re.match(r"@@ -(\d+)", hunk[0])
    if not m:
        return None
    start = int(m.group(1)) - 1
    for i in range(start, max(start - 200, -1), -1):
        fm = re.match(r"def (\w+)\(", old_lines[i])
        if fm:
            return fm.group(1)
    return None


def _pkg_import_name(new_root: Path) -> str:
    """从源码树推断包导入名（取含 __init__.py 的最浅目录名）。"""
    for p in sorted(new_root.rglob("__init__.py"), key=lambda x: len(x.parts)):
        return p.parent.name
    return new_root.name.split("-")[0]


def _test_header(new_root: Path) -> str:
    pkg = _pkg_import_name(new_root)
    return ("import unittest\nfrom unittest import TestCase  # noqa: F401\n"
            "from unittest.mock import patch  # noqa: F401\n"
            "import platform  # noqa: F401\n"
            "from itertools import *  # noqa: F401,F403\n"
            f"import {pkg} as mi  # noqa: F401\n"
            f"from {pkg} import *  # noqa: F401,F403\n\n\n")


def extract_tests(new_root: Path, func: str, max_lines: int = 120) -> str | None:
    """在新版 tests/ 里找与函数名相关的测试（TestCase 类优先，其次引用该函数的 test 函数）。"""
    tests_dir = None
    for cand in ("tests", "test"):
        for p in new_root.rglob(cand):
            if p.is_dir():
                tests_dir = p
                break
        if tests_dir:
            break
    if not tests_dir:
        return None
    pkg_name = _pkg_import_name(new_root)
    alias_line = f"import {pkg_name} as mi" if pkg_name != "mi" else ""
    header = ("import unittest\nfrom unittest import TestCase  # noqa: F401\n"
              + (alias_line + "\n" if alias_line else "") + "\n\n")
    cls_pat = re.compile(rf"class (\w*{func}\w*)\((TestCase|unittest\.TestCase)\)", re.I)
    for tf in sorted(tests_dir.rglob("*.py")):
        lines = tf.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, l in enumerate(lines):
            if cls_pat.search(l):
                end = len(lines)
                for j in range(i + 1, len(lines)):
                    if re.match(r"^(class |def )", lines[j]):
                        end = j
                        break
                block = lines[i:end]
                if len(block) <= max_lines:
                    header = _test_header(new_root)
                    return header + "\n".join(block) + \
                        "\n\n\nif __name__ == '__main__':\n    unittest.main()\n"
    # 次选：收集引用该函数的独立 test 函数（缩进方法或顶层函数都算）
    fn_pat = re.compile(rf"\b{re.escape(func)}\b")
    collected = []
    for tf in sorted(tests_dir.rglob("*.py")):
        lines = tf.read_text(encoding="utf-8", errors="replace").splitlines()
        i = 0
        while i < len(lines):
            m = re.match(r"^(\s*)def (test_\w+)\(", lines[i])
            if m:
                indent = m.group(1)
                j = i + 1
                while j < len(lines) and (lines[j].startswith(indent + " ") or
                                          lines[j].startswith(indent + "\t") or
                                          not lines[j].strip()):
                    j += 1
                block = lines[i:j]
                if any(fn_pat.search(b) for b in block):
                    collected.extend(block + [""])
                i = j
            else:
                i += 1
    if collected and len(collected) <= max_lines:
        header = _test_header(new_root)
        # 包进合成 TestCase（收集到的多是类内方法，4 空格缩进，直接嵌套即合法）
        return (header + "class GeneratedTests(TestCase):\n" +
                "\n".join(collected) +
                "\n\nif __name__ == '__main__':\n    unittest.main()\n")
    return None


def _pytest_rc(tests_path: Path, pythonpath: Path, timeout: int = 120) -> int:
    """内部验证：PYTHONPATH=pythonpath 跑 pytest，返回退出码（0=全过）。"""
    import os
    import subprocess
    env = dict(os.environ)
    env["PYTHONPATH"] = str(pythonpath)
    p = subprocess.run([sys.executable, "-m", "pytest", str(tests_path), "-q",
                        "--no-header", "-p", "no:cacheprovider"],
                       capture_output=True, text=True, timeout=timeout, env=env,
                       encoding="utf-8", errors="replace")
    return p.returncode


def extract_p2p_tests(new_root: Path, func: str, max_lines: int = 60) -> str | None:
    """P2P 回归闸门采样：找与 func 无关的 TestCase（不同功能区的稳定测试）。"""
    tests_dir = None
    for cand in ("tests", "test"):
        for p in new_root.rglob(cand):
            if p.is_dir():
                tests_dir = p
                break
        if tests_dir:
            break
    if not tests_dir:
        return None
    cls_pat = re.compile(r"class (\w+)\((TestCase|unittest\.TestCase)\)")
    for tf in sorted(tests_dir.rglob("*.py")):
        lines = tf.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, l in enumerate(lines):
            m = cls_pat.search(l)
            if m and func.lower() not in m.group(1).lower():
                end = len(lines)
                for j in range(i + 1, len(lines)):
                    if re.match(r"^(class |def )", lines[j]):
                        end = j
                        break
                block = lines[i:min(end, i + max_lines)]
                header = _test_header(new_root)
                return header + "\n".join(block) + \
                    "\n\n\nif __name__ == '__main__':\n    unittest.main()\n"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("package")
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--out", default="tasks/pool-v2")
    args = ap.parse_args()

    print(f"[1/4] 下载 {args.package} {args.old} / {args.new} …")
    old_dir = download_sdist(args.package, args.old)
    new_dir = download_sdist(args.package, args.new)
    old_root, new_root = find_pkg_root(old_dir), find_pkg_root(new_dir)

    print("[2/4] diff 源码并按 hunk 分类 …")
    diffs = diff_py_files(old_root, new_root)
    candidates = []
    for rel, dlines in diffs.items():
        if "test" in rel.lower():
            continue
        old_file = (old_root / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        for h in split_hunks(dlines):
            if hunk_is_bugfix(h):
                fn = enclosing_func(old_file, h)
                candidates.append((rel, fn, h))

    print(f"[3/4] 发现 {len(candidates)} 个 bugfix hunk 候选，F2P/P2P 分离验证中 …")
    out_base = ROOT / args.out
    made, skipped = 0, 0
    import time as _time
    suffix = _time.strftime("%H%M%S")
    for rel, fn, h in candidates:
        fn = fn or "unknown"
        if fn == "unknown":
            continue  # 模块级 hunk（__all__/import 调整），非函数 bugfix
        test_src = extract_tests(new_root, fn)
        if not test_src:
            skipped += 1
            continue
        seq = getattr(main, "_seq", 0)
        main._seq = seq + 1
        tid = f"{args.package.replace('-', '')}-{fn}-{norm_ver(args.old)}-{seq:02d}"
        tdir = out_base / tid
        if tdir.exists():
            tdir = out_base / f"{tid}-{suffix}"  # 沙箱禁 rmtree，改时间戳目录
        # fixture = 旧版完整包源码（真实规模）
        pkg_src = next((p for p in old_root.rglob("*.py")), None)
        pkg_dir = pkg_src.parent if pkg_src else old_root
        shutil.copytree(pkg_dir, tdir / "fixture")
        (tdir / "solution" / "sites").mkdir(parents=True, exist_ok=True)
        patch = ["--- a/" + rel, "+++ b/" + rel] + h
        (tdir / "solution" / "sites" / "site-01.patch").write_text(
            "\n".join(patch) + "\n", encoding="utf-8")
        # --- F2P 验证：新版相关测试在旧版上必须挂 ---
        (tdir / "tests" / "f2p").mkdir(parents=True, exist_ok=True)
        (tdir / "tests" / "f2p" / f"test_{fn}.py").write_text(test_src, encoding="utf-8")
        if _pytest_rc(tdir / "tests" / "f2p", tdir / "fixture") == 0:
            print(f"  ✗ {fn}：fixture 不挂（非行为 bugfix），废弃")
            skipped += 1
            continue
        # --- oracle 验证：打补丁后 F2P 必须过 ---
        patched = tdir / ".verify-patched"
        shutil.copytree(tdir / "fixture", patched)
        import subprocess as _sp
        _sp.run(["git", "apply", "--directory", str(patched),
                 str(tdir / "solution" / "sites" / "site-01.patch")], capture_output=True)
        if _pytest_rc(tdir / "tests" / "f2p", patched) != 0:
            print(f"  ✗ {fn}：oracle 不救，废弃")
            skipped += 1
            continue
        # --- P2P 采样：无关测试在新旧两版都必须过 ---
        (tdir / "tests" / "p2p").mkdir(exist_ok=True)
        p2p_src = extract_p2p_tests(new_root, fn)
        p2p_ok = False
        if p2p_src:
            (tdir / "tests" / "p2p" / "test_stable.py").write_text(p2p_src, encoding="utf-8")
            p2p_ok = (_pytest_rc(tdir / "tests" / "p2p", tdir / "fixture") == 0 and
                      _pytest_rc(tdir / "tests" / "p2p", patched) == 0)
        if not p2p_ok:
            (tdir / "tests" / "p2p" / "test_stable.py").write_text(
                "# P2P 待人工补充（自动采样未通过两版验证）\n", encoding="utf-8")
        (tdir / "tests" / "conftest.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parents[2]))\n",
            encoding="utf-8")
        (tdir / "INTENT.md").write_text(
            f"# 候选：{args.package} {args.old}→{args.new} :: {fn}\n\n"
            f"来源文件：{rel}\n\n```diff\n" + "\n".join(h) + "\n```\n\n"
            f"F2P：fixture 已验证挂、oracle 已验证救 ✓\n"
            f"P2P：{'自动采样两版验证 ✓' if p2p_ok else '⚠️ 待人工补充'}\n"
            f"**prompt 与 wrong 解需人工确认后补 meta.yaml。**\n", encoding="utf-8")
        print(f"  ✓ {fn}（F2P 挂/救验证通过，P2P {'✓' if p2p_ok else '待补'}）")
        made += 1
    print(f"[4/4] 产出 {made} 个验证通过的任务（另 {skipped} 个废弃/跳过）→ {out_base}")
    print("下一步：人工评审 INTENT.md，补 meta.yaml 与 wrong 解，过 task_validator。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
