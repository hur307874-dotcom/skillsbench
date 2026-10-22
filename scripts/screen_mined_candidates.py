"""挖掘候选筛子：对每个候选跑"fixture 裸测 / fixture+gold"两组 pytest，
直接报告哪些满足 任务必要条件（fixture 挂、gold 过）。

用法：python scripts/screen_mined_candidates.py [tasks/pool-v2]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def fix_test_header(test_file: Path, pkg_import: str) -> None:
    """补齐提取测试的 import（TestCase + 包导入）。"""
    src = test_file.read_text(encoding="utf-8")
    if "from unittest import" not in src:
        src = src.replace("import unittest", "import unittest\nfrom unittest import TestCase  # noqa: F401", 1)
    if pkg_import not in src:
        src = src.replace("import unittest", f"import unittest\nimport {pkg_import}", 1)
    test_file.write_text(src, encoding="utf-8")


def run_pytest(tests_dir: Path, cwd: Path) -> tuple[int, str]:
    p = subprocess.run([PY, "-m", "pytest", str(tests_dir), "-q", "--no-header",
                        "-p", "no:cacheprovider", "--import-mode=importlib"],
                       capture_output=True, text=True, cwd=cwd, timeout=120,
                       encoding="utf-8", errors="replace")
    tail = (p.stdout + p.stderr).strip().splitlines()
    return p.returncode, (tail[-1] if tail else "")


def main() -> int:
    base = (ROOT / (sys.argv[1] if len(sys.argv) > 1 else "tasks/pool-v2")).resolve()
    rows = []
    for cand in sorted(base.iterdir()):
        tests = cand / "tests"
        fixture = cand / "fixture"
        gold_dir = cand / "solution" / "sites"
        if not tests.is_dir() or not fixture.is_dir() or not gold_dir.is_dir():
            continue
        test_files = [f for f in tests.glob("test_*.py")]
        if not test_files:
            rows.append((cand.name, "无测试", ""))
            continue
        pkg_dir_name = fixture.name
        for tf in test_files:
            src = tf.read_text(encoding="utf-8")
            import re
            m = re.search(r"\bmi\.|\bmore_itertools\b", src)
            pkg_import = "import more_itertools as mi" if m else ""
            if pkg_import:
                fix_test_header(tf, pkg_import.replace("import ", "").replace(" as mi", ""))
        # 1) fixture 裸测
        rc1, tail1 = run_pytest(tests, cand)
        # 2) fixture + gold
        import shutil
        patched = cand.parent / f".patched-{cand.name}"
        if patched.exists():
            shutil.copytree(fixture, patched, dirs_exist_ok=True)
        else:
            shutil.copytree(fixture, patched)
        import subprocess as sp
        sp.run(["git", "apply", "--directory", str(patched), str(gold_dir / "site-01.patch")],
               capture_output=True)
        rc2, tail2 = run_pytest(tests, cand)
        verdict = "✅ 可用" if (rc1 != 0 and rc2 == 0) else \
                  ("❌ fixture 不挂" if rc1 == 0 else "❌ gold 不救")
        rows.append((cand.name, verdict, f"裸:{tail1[:40]} | gold:{tail2[:40]}"))
    for name, verdict, detail in rows:
        print(f"{verdict}  {name:44s} {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
