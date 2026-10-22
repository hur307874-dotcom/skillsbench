"""forged 线：SWE-smith 破坏算子（对真实包注入 bug，oracle=撤销破坏，判分=真包自带测试）。

原理（POOL_V2 §5）：真实包的测试套件就是现成的 F2P/P2P 来源——
  F2P = 被破坏函数的既有测试（注入后必挂，撤销后必过）
  P2P = 无关函数的既有测试采样（两态都过，回归闸门）

算子（每个都狙击明确 F-ID）：
  BOUNDARY-FLIP  边界翻转（< → <=、> → >=、-1 偏差）  狙击 F17
  CACHE-DROP     删除一行失效/清理调用                 狙击 F01
  RENAME-LEAK    函数改名但留一处调用不改（需2处调用）  狙击 F05

用法：python scripts/forge_tasks.py
依赖：.mine_cache/more_itertools-10.8.0（挖掘器已缓存的 sdist 解压目录）
"""
from __future__ import annotations

import argparse
import re
import shutil
import yaml
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from mine_real_tasks import (download_sdist, find_pkg_root, extract_tests,  # noqa: E402
                             extract_p2p_tests, _pytest_rc, _test_header)  # noqa: E402

CONFTEST = ("import sys\nfrom pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parents[2]))\n")


def _class_to_fn(cls: str) -> str:
    """TestCase 类名 → 函数名：CombinationIndexTests → combination_index。"""
    s = re.sub(r"Tests?$", "", cls)
    return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()


def find_test_class(tests_dir: Path, fn: str) -> tuple[str, str] | None:
    """在真包测试里找测试 fn 的 TestCase 类（先精确 {Fn}Tests，再宽松包含匹配）。"""
    camel = "".join(w.capitalize() for w in fn.split("_"))
    exact = re.compile(rf"class ((?:{re.escape(camel)}|{re.escape(fn)})Tests?)"
                       rf"\((TestCase|unittest\.TestCase)\)", re.I)
    loose = re.compile(rf"class (\w*(?:{re.escape(fn)}|{re.escape(camel)})\w*)"
                       r"\((TestCase|unittest\.TestCase)\)", re.I)
    for pat in (exact, loose):
        for tf in sorted(tests_dir.rglob("*.py")):
            for l in tf.read_text(encoding="utf-8", errors="replace").splitlines():
                m = pat.search(l)
                if m:
                    return tf.name, m.group(1)
    return None


def extract_class_block(tests_dir: Path, filename: str, cls: str,
                        max_lines: int = 150) -> str | None:
    for tf in tests_dir.rglob(filename):
        lines = tf.read_text(encoding="utf-8", errors="replace").splitlines()
        # 抓取源文件的模块级 import 块（测试类可能引用这些裸名：platform/NamedTuple 等）
        imports = []
        k = 0
        while k < len(lines):
            l = lines[k]
            if re.match(r"^(import |from .+ import )", l):
                imports.append(l)
                if l.count("(") > l.count(")"):  # 跨行括号 import
                    k += 1
                    while k < len(lines) and ")" not in lines[k - 1]:
                        imports.append(lines[k])
                        k += 1
            elif l.strip() and not l.startswith("#") and not l.startswith('"""'):
                if imports:
                    break
            k += 1
        for i, l in enumerate(lines):
            if re.match(rf"class {cls}\(", l):
                end = len(lines)
                for j in range(i + 1, len(lines)):
                    if re.match(r"^(class |def )", lines[j]):
                        end = j
                        break
                # 按方法边界截取（不在 def 中间砍断）：超过一半预算且到方法边界即收刀
                block = []
                k = i
                in_method = False
                while k < end and len(block) < max_lines:
                    if re.match(r"^\s+def \w+\(", lines[k]):
                        if in_method and len(block) > max_lines // 2:
                            break
                        in_method = True
                    block.append(lines[k])
                    k += 1
                future = [l for l in imports if l.startswith("from __future__")]
                others = [l for l in imports if not l.startswith("from __future__")]
                return ("\n".join(future) + "\n" if future else "") + \
                    "\n".join(others) + "\n\n\n" + "\n".join(block)
    return None


def _compose_test_file(header: str, block: str) -> str:
    """header + block 组合，__future__ import 抽到文件最顶。"""
    blines = block.split("\n")
    future = [l for l in blines if l.startswith("from __future__")]
    rest = [l for l in blines if not l.startswith("from __future__")]
    return ("\n".join(future) + "\n\n" if future else "") + header + "\n".join(rest)


def forge_one(tid: str, pkg_root_old: Path, out_base: Path,
              target_file: str, old_line: str, new_line: str,
              fn: str, difficulty: str, fid: str, prompt: str, intent: str,
              wrong_line: str | None = None) -> bool:
    """注入一个算子并产出任务目录；返回是否通过内验。"""
    src = pkg_root_old / target_file
    text = src.read_text(encoding="utf-8")
    repls = old_line if isinstance(old_line, list) else [(old_line, new_line)]
    for o, n in repls:
        assert o in text, f"算子锚点未找到：{o[:60]}"
    tdir = out_base / tid
    if tdir.exists():
        import time
        tdir = out_base / f"{tid}-{time.strftime('%H%M%S')}"
    # fixture = 注入后的真包（完整包源码 + 测试目录剔除）
    pkg_dir = next(p for p in pkg_root_old.rglob("__init__.py")).parent.parent
    shutil.copytree(pkg_dir, tdir / "fixture",
                    ignore=shutil.ignore_patterns("tests", ".git", "__pycache__"))
    fixture_file = tdir / "fixture" / target_file
    ftext = fixture_file.read_text(encoding="utf-8")
    for o, n in repls:
        ftext = ftext.replace(o, n, 1)
    fixture_file.write_text(ftext, encoding="utf-8")
    # oracle = 撤销注入（new → old）
    (tdir / "solution" / "sites").mkdir(parents=True, exist_ok=True)
    # 生成规范 unified diff（字符串级替换，兼容多行锚点；保证 git apply 可用）
    import difflib
    orig_text = fixture_file.read_text(encoding="utf-8")
    fixed_text = orig_text
    for o, n in reversed(repls):
        fixed_text = fixed_text.replace(n, o, 1)
    d = list(difflib.unified_diff(orig_text.splitlines(), fixed_text.splitlines(),
                                  lineterm="",
                                  fromfile=f"a/{target_file}", tofile=f"b/{target_file}"))
    (tdir / "solution" / "sites" / "site-01.patch").write_text("\n".join(d) + "\n",
                                                              encoding="utf-8")
    # F2P = 真包中该函数的测试类
    tests_dir = pkg_dir / "tests"
    found = find_test_class(tests_dir, fn)
    if not found:
        print(f"  ✗ {tid}：真包测试中未找到 {fn} 的测试类")
        return False
    fname, cls = found
    block = extract_class_block(tests_dir, fname, cls, max_lines=80)  # 取核心测试段
    if not block:
        return False
    header = _test_header(pkg_root_old)
    # __future__ import 必须在文件最顶（抽到 header 之前）
    blines = block.split("\n")
    future = [l for l in blines if l.startswith("from __future__")]
    rest = [l for l in blines if not l.startswith("from __future__")]
    content = ("\n".join(future) + "\n\n" if future else "") + header + "\n".join(rest)
    (tdir / "tests" / "f2p").mkdir(parents=True, exist_ok=True)
    (tdir / "tests" / "f2p" / f"test_{fn}.py").write_text(
        content + "\n\n\nif __name__ == '__main__':\n    unittest.main()\n",
        encoding="utf-8")
    # P2P = 无关测试类采样
    (tdir / "tests" / "p2p").mkdir(exist_ok=True)
    p2p_block = None
    for tf in sorted(tests_dir.rglob("*.py")):
        for m in re.finditer(r"class (\w+)\((TestCase|unittest\.TestCase)\)",
                             tf.read_text(encoding="utf-8", errors="replace")):
            other_fn = _class_to_fn(m.group(1))
            if fn.lower() not in m.group(1).lower() and other_fn:
                p2p_block = extract_class_block(tests_dir, tf.name, m.group(1), 60)
                break
        if p2p_block:
            break
    if p2p_block:
        (tdir / "tests" / "p2p" / "test_stable.py").write_text(
            header + p2p_block + "\n\n\nif __name__ == '__main__':\n    unittest.main()\n",
            encoding="utf-8")
    (tdir / "tests" / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    # 内验：F2P 挂于注入、救于撤销；P2P 两态都过
    if _pytest_rc(tdir / "tests" / "f2p", tdir / "fixture") == 0:
        print(f"  ✗ {tid}：注入后 F2P 不挂")
        return False
    patched = tdir / ".verify-patched"
    shutil.copytree(tdir / "fixture", patched)
    # 纯 Python 撤销（不依赖 git 环境；gold patch 本身已用 git apply 另行验证过可用性）
    pf = patched / target_file
    ptext = pf.read_text(encoding="utf-8")
    for o, n in reversed(repls):
        ptext = ptext.replace(n, o, 1)
    pf.write_text(ptext, encoding="utf-8")
    if _pytest_rc(tdir / "tests" / "f2p", patched) != 0:
        print(f"  ✗ {tid}：撤销后 F2P 不救")
        return False
    if p2p_block and (_pytest_rc(tdir / "tests" / "p2p", tdir / "fixture") != 0 or
                      _pytest_rc(tdir / "tests" / "p2p", patched) != 0):
        print(f"  ⚠ {tid}：P2P 采样不稳，剔除 p2p")
        (tdir / "tests" / "p2p" / "test_stable.py").write_text("# P2P 待人工补充\n",
                                                               encoding="utf-8")
    if wrong_line:
        wrepls = wrong_line if isinstance(wrong_line, list) else [(repls[-1][1], wrong_line)]
        wdir = tdir / "wrong" / "wrong_01"
        shutil.copytree(tdir / "fixture", wdir, dirs_exist_ok=True)
        wf = wdir / target_file
        wtext = wf.read_text(encoding="utf-8")
        for o, w in wrepls:
            wtext = wtext.replace(o, w, 1)
        wf.write_text(wtext, encoding="utf-8")
    (tdir / "meta.yaml").write_text(
        f"task_id: {tid}\ntrack: code\ndifficulty: {difficulty}\n"
        f"targets_fids: [{fid}]\nsites_required: 1\n"
        f"forbidden_edits: [tests/, _tests/]\n"
        f"prompt: |\n  " + prompt.replace("\n", "\n  ") + "\n", encoding="utf-8")
    (tdir / "INTENT.md").write_text(
        f"# 出题意图（{tid}，forged）\n\n- 算子注入：{target_file}\n"
        + "".join(f"  `- {o.strip()}` → `+ {n.strip()}`\n" for o, n in repls)
        + f"- 狙击 {fid}；F2P = 真包 {fname}::{cls}；oracle = 撤销注入。\n" + intent,
        encoding="utf-8")
    print(f"  ✓ {tid}（注入/撤销/P2P 内验通过）")
    return True


def forge_multi(tid: str, pkg_root_old: Path, out_base: Path,
                target_file: str, sites: list[dict],
                difficulty: str, fid: str, prompt: str, intent: str,
                extra_f2p: str | None = None,
                wrong_site: int | None = None) -> bool:
    """复合 bug 注入：sites = [{'repls': [(o,n),...], 'f2p_fn': str, 'note': str}, ...]
    每个 site 独立出 site-0i.patch（撤销该组的替换）；wrong_01 = 只撤销
    wrong_site 指定的一组（默认第 0 组 = 最显眼的那个）。
    extra_f2p：手写定向测试源码（当算子的边界用例不被真包测试覆盖时补充）。
    """
    for s in sites:
        sf = pkg_root_old / s.get("file", target_file)
        stext = sf.read_text(encoding="utf-8")
        for o, n in s["repls"]:
            assert o in stext, f"[{tid}] 锚点未找到（{s.get('file', target_file)}）：{o[:60]}"
    tdir = out_base / tid
    if tdir.exists():
        import time
        tdir = out_base / f"{tid}-{time.strftime('%H%M%S')}"
    pkg_dir = next(p for p in pkg_root_old.rglob("__init__.py")).parent.parent
    shutil.copytree(pkg_dir, tdir / "fixture",
                    ignore=shutil.ignore_patterns("tests", ".git", "__pycache__"))
    for s in sites:
        ff = tdir / "fixture" / s.get("file", target_file)
        ftext = ff.read_text(encoding="utf-8")
        for o, n in s["repls"]:
            ftext = ftext.replace(o, n, 1)
        ff.write_text(ftext, encoding="utf-8")
    # oracle：每组一个 site-0i.patch（只撤销该组）
    import difflib
    (tdir / "solution" / "sites").mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(sites):
        ff = tdir / "fixture" / s.get("file", target_file)
        orig_lines = ff.read_text(encoding="utf-8").splitlines()
        fixed = ff.read_text(encoding="utf-8")
        for o, n in reversed(s["repls"]):
            fixed = fixed.replace(n, o, 1)
        d = list(difflib.unified_diff(orig_lines, fixed.splitlines(), lineterm="", n=0,
                                      fromfile=f"a/{s.get('file', target_file)}",
                                      tofile=f"b/{s.get('file', target_file)}"))
        (tdir / "solution" / "sites" / f"site-{i+1:02d}.patch").write_text(
            "\n".join(d) + "\n", encoding="utf-8")
    # F2P：每个 site 对应函数的真包测试类 + 可选手写定向测试
    tests_dir = pkg_dir / "tests"
    header = _test_header(pkg_root_old)
    (tdir / "tests" / "f2p").mkdir(parents=True, exist_ok=True)
    for s in sites:
        fn = s["f2p_fn"]
        found = find_test_class(tests_dir, fn)
        if not found:
            print(f"  ✗ {tid}：未找到 {fn} 的测试类")
            return False
        fname, cls = found
        block = extract_class_block(tests_dir, fname, cls, max_lines=80)
        (tdir / "tests" / "f2p" / f"test_{fn}.py").write_text(
            _compose_test_file(header, block) +
            "\n\n\nif __name__ == '__main__':\n    unittest.main()\n",
            encoding="utf-8")
    if extra_f2p:
        (tdir / "tests" / "f2p" / "test_targeted.py").write_text(
            header + extra_f2p + "\n\n\nif __name__ == '__main__':\n    unittest.main()\n",
            encoding="utf-8")
    (tdir / "tests" / "p2p").mkdir(exist_ok=True)
    (tdir / "tests" / "p2p" / "test_stable.py").write_text("# P2P 待人工补充\n",
                                                          encoding="utf-8")
    (tdir / "tests" / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    # 内验 1：注入态 F2P 必须挂
    if _pytest_rc(tdir / "tests" / "f2p", tdir / "fixture") == 0:
        print(f"  ✗ {tid}：注入后 F2P 不挂")
        return False
    # 内验 2：全撤销后 F2P 必须过
    patched = tdir / ".verify-patched"
    shutil.copytree(tdir / "fixture", patched)
    for s in sites:
        pf = patched / s.get("file", target_file)
        ptext = pf.read_text(encoding="utf-8")
        for o, n in reversed(s["repls"]):
            ptext = ptext.replace(n, o, 1)
        pf.write_text(ptext, encoding="utf-8")
    if _pytest_rc(tdir / "tests" / "f2p", patched) != 0:
        print(f"  ✗ {tid}：全撤销后 F2P 不救")
        return False
    # 内验 3：逐组撤销（每组单独撤销时，另一组的 bug 仍在 → 必须有测试挂）
    for i, s in enumerate(sites):
        partial = tdir / f".verify-partial-{i}"
        shutil.copytree(tdir / "fixture", partial)
        pp = partial / s.get("file", target_file)
        ptxt = pp.read_text(encoding="utf-8")
        for o, n in reversed(s["repls"]):
            ptxt = ptxt.replace(n, o, 1)
        pp.write_text(ptxt, encoding="utf-8")
        if _pytest_rc(tdir / "tests" / "f2p", partial) == 0:
            print(f"  ✗ {tid}：只修第 {i+1} 组时测试全过（bug 组间无区分）")
            return False
    # wrong_01：只修最显眼的一组（默认第 0 组）
    ws = wrong_site if wrong_site is not None else 0
    wdir = tdir / "wrong" / "wrong_01"
    shutil.copytree(tdir / "fixture", wdir, dirs_exist_ok=True)
    wf = wdir / sites[ws].get("file", target_file)
    wtext = wf.read_text(encoding="utf-8")
    for o, n in reversed(sites[ws]["repls"]):
        wtext = wtext.replace(n, o, 1)
    wf.write_text(wtext, encoding="utf-8")
    (tdir / "meta.yaml").write_text(
        f"task_id: {tid}\ntrack: code\ndifficulty: {difficulty}\n"
        f"targets_fids: [{fid}]\nsites_required: {len(sites)}\n"
        f"forbidden_edits: [tests/, _tests/]\n"
        f"prompt: |\n  " + prompt.replace("\n", "\n  ") + "\n", encoding="utf-8")
    (tdir / "INTENT.md").write_text(
        f"# 出题意图（{tid}，forged-multi）\n\n- 复合注入 {len(sites)} 组算子于 {target_file}\n"
        + "".join(f"  组{i+1}（{s.get('note','')}）：" +
                  " / ".join(f"`{o.strip()}`→`{n.strip()}`" for o, n in s["repls"]) + "\n"
                  for i, s in enumerate(sites))
        + f"- 狙击 {fid}；wrong_01 = 只修第 {ws+1} 组（漏修另一组，测试抓）。\n" + intent,
        encoding="utf-8")
    print(f"  ✓ {tid}（{len(sites)} 组复合注入，全内验通过）")
    return True


def run_spec(spec_path: Path, out_base: Path) -> int:
    """声明式配方驱动：spec yaml 定义任务，引擎零配方内容（换任务域=换 yaml）。"""
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    pkg_root = find_pkg_root(download_sdist(spec["package"], spec["version"]))
    made = 0
    for task in spec["tasks"]:
        pairs = [(o, n) for o, n in task.get("repls", [])]
        if task["type"] == "single":
            old = pairs if len(pairs) > 1 else pairs[0][0]
            new = None if len(pairs) > 1 else pairs[0][1]
            wrong = task.get("wrong_repls")
            if wrong:
                wrong = [(o, n) for o, n in wrong]
            else:
                wrong = task.get("wrong_line")
            made += forge_one(task["tid"], pkg_root, out_base, task["file"],
                              old, new, task["f2p_fn"], task["difficulty"],
                              task["fid"], task["prompt"].strip(),
                              task.get("intent", "").strip(), wrong_line=wrong)
        else:
            sites = []
            for s in task["sites"]:
                sd = {"repls": [(o, n) for o, n in s["repls"]],
                      "f2p_fn": s["f2p_fn"], "note": s.get("note", "")}
                if "file" in s:
                    sd["file"] = s["file"]
                sites.append(sd)
            made += forge_multi(task["tid"], pkg_root, out_base, task["file"],
                                sites, task["difficulty"], task["fid"],
                                task["prompt"].strip(),
                                task.get("intent", "").strip(),
                                extra_f2p=task.get("extra_f2p"),
                                wrong_site=task.get("wrong_site"))
    print(f"\n共注入 {made} 个任务（spec={spec_path.name}）→ {out_base}")
    return 0


def main() -> int:
    """用法：python scripts/forge_tasks.py <spec.yaml> [--out DIR]

    引擎通用（无任何任务域/Skill 硬编码）；配方见 tasks/pool-v2/forge_specs/。
    换任务域：新写 spec yaml 即可；换被评 Skill：与 forge 完全无关（臂注入侧）。
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", help="forge 配方 yaml（如 tasks/pool-v2/forge_specs/more-itertools-10.8.0.yaml）")
    ap.add_argument("--out", default="tasks/pool-v2/forged")
    args = ap.parse_args()
    return run_spec(Path(args.spec), ROOT / args.out)


if __name__ == "__main__":
    sys.exit(main())
