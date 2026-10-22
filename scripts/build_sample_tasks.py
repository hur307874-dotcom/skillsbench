"""构造样例任务（d1-typo-01、d2-enum-01），补丁由 git diff 生成保证可复现 apply。

用法：python scripts/build_sample_tasks.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "tasks" / "generated"

CONFTEST = '''import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
'''


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.email=sb@local", "-c", "user.name=sb",
         "-c", "core.autocrlf=false", *args],
        cwd=repo, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()[:300]}")
    return proc.stdout


def make_patches(fixture_dir: Path, steps: list[tuple[str, list[tuple[str, str]]]], sites_out: Path) -> None:
    """把 fixture 复制到临时构建仓，按 steps 逐步修改并 git diff 生成 site-NN.patch。"""
    build = Path(tempfile.mkdtemp(prefix="sb-build-")) / "repo"
    shutil.copytree(fixture_dir, build)
    git(build, "init", "-q")
    git(build, "add", "-A")
    git(build, "commit", "-qm", "fixture")
    sites_out.mkdir(parents=True, exist_ok=True)
    for i, (rel, replacements) in enumerate(steps, 1):
        f = build / rel
        text = f.read_text(encoding="utf-8")
        for old, new in replacements:
            assert old in text, f"{rel} 中找不到: {old!r}"
            text = text.replace(old, new, 1)
        f.write_text(text, encoding="utf-8", newline="\n")
        diff = git(build, "diff", "--", rel)
        (sites_out / f"site-{i:02d}.patch").write_text(diff, encoding="utf-8", newline="\n")
        git(build, "add", "-A")
        git(build, "commit", "-qm", f"site-{i:02d}")
    shutil.rmtree(build.parent, ignore_errors=True)


def build_d1() -> None:
    t = GEN / "d1-typo-01"
    write(t / "fixture" / "calc.py", '''def average(nums):
    """Return the arithmetic mean of nums."""
    return sum(nums) / (len(nums) - 1)
''')
    write(t / "fixture" / "README.md", "# d1-typo-01\n一个小型计算库。\n")
    write(t / "tests" / "conftest.py", CONFTEST)
    write(t / "tests" / "test_calc.py", '''from calc import average


def test_average_typical():
    assert average([2, 4, 6]) == 4


def test_average_single():
    assert average([5]) == 5
''')
    # 错解：把结果四舍五入（没修根因）
    write(t / "wrong" / "wrong_01" / "calc.py", '''def average(nums):
    """Return the arithmetic mean of nums."""
    return round(sum(nums) / (len(nums) - 1), 2)
''')
    write(t / "wrong" / "wrong_01" / "README.md", "# d1-typo-01\n一个小型计算库。\n")
    write(t / "meta.yaml", '''task_id: d1-typo-01
difficulty: D1
targets_fids: [F17]
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  当前仓库 calc.py 里的 average 函数结果不对：
  用户报告 average([2, 4, 6]) 期望 4 但实际得到 6，average([5]) 直接报错。
  请定位并修复这个 bug。
''')
    write(t / "INTENT.md", '''# 出题意图（d1-typo-01）

- 预设陷阱：报错直接指向 len(nums)-1，但模型可能"顺手"加 try/except 或改返回类型而不修根因（F17 治症状）。
- 狙击 F-ID：F17（误读报错治症状）。
- 预期 Skill 作用点：diagnose 类流程（先复现）在本任务应无显著差异——D1 档存在的意义是测 I1 的负收益（琐碎任务不需要确认流程）。
''')
    make_patches(t / "fixture", [("calc.py", [("len(nums) - 1", "len(nums)")])],
                 t / "solution" / "sites")


def build_d2() -> None:
    t = GEN / "d2-enum-01"
    write(t / "fixture" / "lib.py", '''def fetch(url):
    raise RuntimeError("fetch() has been removed; use fetch_v2(url, timeout)")


def fetch_v2(url, timeout=5):
    """Fetch data from url with timeout (seconds)."""
    return {"url": url, "timeout": timeout, "data": f"payload:{url}"}
''')
    write(t / "fixture" / "services" / "__init__.py", "")
    write(t / "fixture" / "services" / "users.py", '''from lib import fetch


def get_user(user_id):
    return fetch(f"https://api.internal/users/{user_id}")
''')
    write(t / "fixture" / "services" / "orders.py", '''from lib import fetch


def get_order(order_id):
    return fetch(f"https://api.internal/orders/{order_id}")


def list_orders():
    return fetch("https://api.internal/orders")
''')
    write(t / "fixture" / "cli.py", '''from lib import fetch


def status():
    return fetch("https://api.internal/status")
''')
    write(t / "fixture" / "README.md", "# d2-enum-01\n内部服务调用库。\n")
    write(t / "tests" / "conftest.py", CONFTEST)
    write(t / "tests" / "test_users.py", '''from services.users import get_user


def test_get_user():
    r = get_user(1)
    assert r["url"] == "https://api.internal/users/1"
    assert r["timeout"] == 5
''')
    write(t / "tests" / "test_orders.py", '''from services.orders import get_order, list_orders


def test_get_order():
    assert get_order(7)["url"] == "https://api.internal/orders/7"


def test_list_orders():
    assert list_orders()["url"] == "https://api.internal/orders"
''')
    write(t / "tests" / "test_cli.py", '''from cli import status


def test_status():
    assert status()["url"] == "https://api.internal/status"
''')
    # 错解：只修了 users.py（只改报错处，漏掉其余 3 处）
    for rel in ["lib.py", "services/__init__.py", "services/orders.py", "cli.py", "README.md"]:
        src = t / "fixture" / rel
        dst = t / "wrong" / "wrong_01" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    write(t / "wrong" / "wrong_01" / "services" / "users.py", '''from lib import fetch_v2


def get_user(user_id):
    return fetch_v2(f"https://api.internal/users/{user_id}", timeout=5)
''')
    write(t / "meta.yaml", '''task_id: d2-enum-01
difficulty: D2
targets_fids: [F05, F09]
sites_required: 4
forbidden_edits: [tests/, _tests/]
prompt: |
  当前仓库里旧 API fetch() 已废弃（调用即抛 RuntimeError），
  新 API 是 fetch_v2(url, timeout)。
  请把仓库中所有调用点迁移到新 API，保证所有功能恢复。
''')
    write(t / "INTENT.md", '''# 出题意图（d2-enum-01）

- 预设陷阱：4 个调用点分布在 3 个文件（users.py ×1、orders.py ×2、cli.py ×1），
  报错只暴露第一个被触碰的位置；模型容易"修一处就收工"（F05）。
- 狙击 F-ID：F05（漏改同模式调用点）、F09（旧签名）。
- 预期 Skill 作用点：I2（最小化修改）与本任务"改全 N 处"直接冲突——H2 的主战场；
  I1（枚举后再改）应显著降低漏改率。
- 每处漏改都有对应测试盯着（orders.py 两处各有一个测试函数）。
''')
    make_patches(t / "fixture", [
        ("services/users.py", [
            ("from lib import fetch", "from lib import fetch_v2"),
            ('return fetch(f"https://api.internal/users/{user_id}")',
             'return fetch_v2(f"https://api.internal/users/{user_id}", timeout=5)'),
        ]),
        ("services/orders.py", [
            ("from lib import fetch", "from lib import fetch, fetch_v2"),
            ('return fetch(f"https://api.internal/orders/{order_id}")',
             'return fetch_v2(f"https://api.internal/orders/{order_id}", timeout=5)'),
        ]),
        ("services/orders.py", [
            ('return fetch("https://api.internal/orders")',
             'return fetch_v2("https://api.internal/orders", timeout=5)'),
        ]),
        ("cli.py", [
            ("from lib import fetch", "from lib import fetch_v2"),
            ('return fetch("https://api.internal/status")',
             'return fetch_v2("https://api.internal/status", timeout=5)'),
        ]),
    ], t / "solution" / "sites")


if __name__ == "__main__":
    build_d1()
    build_d2()
    print("样例任务已生成：d1-typo-01, d2-enum-01")
    sys.exit(0)
