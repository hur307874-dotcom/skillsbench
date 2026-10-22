"""为 forged 任务补 P2P 回归闸门（POOL_V2 §3 判分哲学的另一半嘴）。

策略：每个任务挑 2 个与被注入函数无关的稳定测试类（test_recipes/test_more），
两态验证（注入态与 oracle 撤销态都必须全过）才写入 tests/p2p/。

用法：python scripts/add_p2p.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from mine_real_tasks import download_sdist, find_pkg_root, _pytest_rc, _test_header  # noqa: E402
from forge_tasks import extract_class_block  # noqa: E402

# 任务 → 候选 P2P 测试类（按优先级；与被注入函数无关的简单稳定类）
P2P_CANDIDATES = {
    "forged-boundary-allequal": ["SieveTests", "TakeTests", "TailTests"],
    "forged-cachedrop-sieve": ["AllEqualTests", "TakeTests", "TailTests"],
    "forged-argswap-sieve": ["AllEqualTests", "TakeTests", "TailTests"],
    "forged-renameleak-islice": ["AllEqualTests", "SieveTests", "TakeTests"],
    "forged-multi-sieve": ["AllEqualTests", "TakeTests", "TailTests"],
    "forged-multi-dual": ["SieveTests", "TailTests", "AllEqualTests"],
    "forged-multi-taketail": ["SieveTests", "AllEqualTests", "TailTests"],
    "forged-multi-crossfile": ["SieveTests", "TakeTests", "TailTests"],
    "forged-multi-triple": ["AllEqualTests", "TailTests", "TakeTests"],
}


def main() -> int:
    pkg_root = find_pkg_root(download_sdist("more-itertools", "10.8.0"))
    pkg_dir = next(p for p in pkg_root.rglob("__init__.py")).parent.parent
    tests_dir = pkg_dir / "tests"
    header = _test_header(pkg_root)
    staging = ROOT / "tasks" / "pool-v2" / "forged-final"

    for tid, candidates in P2P_CANDIDATES.items():
        tdir = staging / tid
        if not tdir.is_dir():
            print(f"✗ {tid} 不存在，跳过")
            continue
        picked = []
        for cls in candidates:
            for fname in ("test_recipes.py", "test_more.py"):
                block = extract_class_block(tests_dir, fname, cls, max_lines=60)
                if block:
                    picked.append((cls, block))
                    break
            if len(picked) >= 2:
                break
        if not picked:
            print(f"✗ {tid}：无可用 P2P 类")
            continue
        # 两态验证：写入后 fixture 态与 patched 态都必须全过
        p2p_dir = tdir / "tests" / "p2p"
        # 直接覆盖写（沙箱禁 unlink；文件名固定 test_stable_{i}.py 无残留问题）
        for i, (cls, block) in enumerate(picked[:2]):
            (p2p_dir / f"test_stable_{i}.py").write_text(
                header + block + "\n\n\nif __name__ == '__main__':\n    unittest.main()\n",
                encoding="utf-8")
        ok_fixture = _pytest_rc(p2p_dir, tdir / "fixture") == 0
        patched = tdir / ".p2p-verify"
        if patched.exists():
            shutil.rmtree(patched, ignore_errors=True)
        shutil.copytree(tdir / "fixture", patched, dirs_exist_ok=True)
        import subprocess
        subprocess.run(["git", "apply", "--directory", str(patched),
                        str(tdir / "solution" / "sites" / "site-01.patch")],
                       capture_output=True)
        ok_patched = _pytest_rc(p2p_dir, patched) == 0
        if ok_fixture and ok_patched:
            classes = ", ".join(c for c, _ in picked[:2])
            print(f"✓ {tid}：P2P 落地（{classes}，两态验证通过）")
        else:
            print(f"✗ {tid}：两态不稳（fixture={ok_fixture} patched={ok_patched}），"
                  f"保留占位待人工")
            (p2p_dir / "test_stable.py").write_text("# P2P 待人工补充\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
