"""MINED-B1：mined 池全量逐测试过滤器（2026-10-10）。

病因（10-09 验尸）：f2p 文件是整个测试文件，gold 只修一处回归，
挖掘器四关被"坏收集"骗过。

过滤工艺（exactly_n/substrings2 手工验证过的路径）：
1. 逐测试跑 fixture 态：挂的才是候选回归测试（PYTHONPATH=fixture 保证包解析）；
2. gold 双向尝试（原方向 / -R）：哪边能让挂的翻绿定 A/B 类；
   B 类归一：bug 态=fixture+patch，gold=git diff --no-index 正向生成；
3. 新 f2p 只留翻转测试的文件（其余为环境/版本噪声，剔除）；
4. 产出 tasks/mined-v2/（不碰 tasks/generated，审查后合流）。

注意：git apply 一律 bytes stdin（text-stdin 被 CRLF 污染，10-09 踩坑）。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POOL = ROOT / "tasks" / "pool-v2-mined"
OUT = ROOT / "tasks" / "mined-v2"
REPORT = ROOT / "results" / "mined-b1-screen.json"
PY = sys.executable
BS = chr(92)
WORKERS = 14  # 全资源模式（用户立规 10-10）


def git_apply(cwd: Path, txt: str, reverse: bool = False) -> subprocess.CompletedProcess:
    cmd = ["git", "apply", "-"] + (["-R"] if reverse else [])
    return subprocess.run(cmd, cwd=cwd, input=txt.encode("utf-8"),
                          capture_output=True)


def pytest_env(fx: Path) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(fx)
    return env


def list_tests(fx: Path, tests_dir: Path) -> list[str]:
    """收集节点 id，统一为绝对路径形式 <abs_file>::<node>。"""
    r = subprocess.run([PY, "-m", "pytest", str(tests_dir), "--co", "-q",
                        "--import-mode=importlib"],
                       cwd=fx, env=pytest_env(fx),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    ids = []
    for ln in r.stdout.splitlines():
        ln = ln.strip()
        if "::" not in ln or ln.startswith(("ERROR", "error", "<")):
            continue
        file_part, node_part = ln.split("::", 1)
        fp = Path(file_part)
        if not fp.is_absolute():
            # 相对路径相对 tests_dir 的上一级（形如 tests/f2p/x.py 或 f2p/x.py）
            cand = tests_dir.parent / file_part
            if not cand.exists():
                cand = tests_dir / file_part
            fp = cand
        if fp.exists():
            ids.append(f"{fp}::{node_part}")
    return ids


def run_one(fx: Path, abs_node: str) -> bool:
    r = subprocess.run([PY, "-m", "pytest", abs_node, "-q", "--no-header",
                        "--import-mode=importlib"],
                       cwd=fx, env=pytest_env(fx),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    return r.returncode == 0


def func_name(dirname: str) -> str:
    m = re.match(r"moreitertools-([a-z_]+?)(?:-\d.*)?$", dirname)
    return m.group(1) if m else "相关"


def forward_gold(bug_fx: Path, fixed_fx: Path) -> str:
    rel = "more_itertools/more.py"
    diff = subprocess.run(
        ["git", "diff", "--no-index", "--src-prefix=a/", "--dst-prefix=b/",
         str(bug_fx / rel), str(fixed_fx / rel)],
        capture_output=True, text=True).stdout
    lines = []
    for ln in diff.splitlines():
        if ln.startswith("--- "):
            ln = "--- a/" + rel
        elif ln.startswith("+++ "):
            ln = "+++ b/" + rel
        lines.append(ln)
    return "\n".join(lines) + "\n"


def process_task(d: Path) -> dict:
    name = d.name
    rec = {"task": name, "status": "fail", "kind": "", "kept": 0, "note": ""}
    if (OUT / name / "meta.yaml").exists():
        rec.update(status="ok", kind="skip", note="已产出（跳过）")
        return rec
    tests_dir = (d / "tests").resolve()
    patch_file = next((d / "solution" / "sites").glob("*.patch"), None)
    if not patch_file:
        rec["note"] = "无 gold patch"
        return rec
    ptxt = patch_file.read_text(encoding="utf-8").replace(
        "more_itertools" + BS, "more_itertools/")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Path(tmp) / "fx"
            shutil.copytree(d / "fixture", fx)
            nodes = list_tests(fx, tests_dir)
            if not nodes:
                rec["note"] = "收集为空"
                return rec
            failing = [nd for nd in nodes if not run_one(fx, nd)]

            kind, gold_txt, bug_fx = "", "", None
            # A 向：fixture 即 bug 态，原 patch 为 gold
            if failing:
                fxA = Path(tmp) / "fxA"
                shutil.copytree(d / "fixture", fxA)
                if git_apply(fxA, ptxt).returncode == 0 and all(
                        run_one(fxA, nd) for nd in failing):
                    kind, gold_txt, bug_fx = "A", ptxt, fx
            # B 向：fixture 是修复态，patch 注入 bug，-R 为解
            if not kind:
                fxB = Path(tmp) / "fxB"
                shutil.copytree(d / "fixture", fxB)
                if git_apply(fxB, ptxt).returncode == 0:
                    failingB = [nd for nd in nodes if not run_one(fxB, nd)]
                    if failingB:
                        fxR = Path(tmp) / "fxR"
                        shutil.copytree(fxB, fxR)
                        if git_apply(fxR, ptxt, reverse=True).returncode == 0 and all(
                                run_one(fxR, nd) for nd in failingB):
                            kind = "B"
                            gold_txt = forward_gold(fxB, d / "fixture")
                            bug_fx, failing = fxB, failingB
            if not kind:
                rec["note"] = (f"A向不成立（{len(failing)} 挂）且 B向不成立"
                               if failing else f"fixture 全过且注入失败（{len(nodes)} 测试）")
                return rec

            # 组装产出
            dst = OUT / name
            shutil.copytree(bug_fx, dst / "fixture")
            kept_files = sorted({nd.split("::")[0] for nd in failing})
            n_kept = 0
            (dst / "tests" / "f2p").mkdir(parents=True, exist_ok=True)
            for kf in kept_files:
                src_tf = Path(kf)
                if src_tf.exists():
                    shutil.copy2(src_tf, dst / "tests" / "f2p" / src_tf.name)
                    n_kept += 1
            (dst / "solution" / "sites").mkdir(parents=True, exist_ok=True)
            (dst / "solution" / "sites" / "site-01.patch").write_text(
                gold_txt, encoding="utf-8", newline="\n")
            (dst / "meta.yaml").write_text(f"""task_id: mined2-{name[15:]}
difficulty: D3
sites_required: 1
forbidden_edits: [tests/, _tests/]
prompt: |
  more_itertools 包的 `{func_name(name)}` 功能在某些输入上行为不符合预期
  （维护者收到的回归报告）。请复现问题、定位根因并修复，
  保持包内其他 API 行为不变。
""", encoding="utf-8", newline="\n")
            rec.update(status="ok", kind=kind, kept=len(failing),
                       note=f"{len(nodes)} 测试→翻转 {len(failing)}（文件 {n_kept}）")
            return rec
    except Exception as e:  # noqa: BLE001
        rec["note"] = f"异常: {str(e)[:80]}"
        return rec


def main() -> int:
    OUT.mkdir(exist_ok=True)
    dirs = sorted(d for d in POOL.iterdir() if d.is_dir())
    print(f"待筛 {len(dirs)} 题，{WORKERS} 线程……", flush=True)
    recs = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, rec in enumerate(ex.map(process_task, dirs), 1):
            recs.append(rec)
            if i % 10 == 0 or rec["status"] == "ok":
                mark = "✓" if rec["status"] == "ok" else "✗"
                print(f"[{i}/{len(dirs)}] {mark} {rec['task'][15:44]} {rec['kind']} {rec['note'][:56]}", flush=True)
    ok = [r for r in recs if r["status"] == "ok"]
    REPORT.write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n合格 {len(ok)}/{len(recs)}（A={sum(1 for r in ok if r['kind']=='A')} "
          f"B={sum(1 for r in ok if r['kind']=='B')}）→ {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
