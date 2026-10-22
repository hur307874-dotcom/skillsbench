"""极简 orchestrator：矩阵展开 → 并发执行 → 真实判分 → jsonl 落盘。

机制：并发（线程池）/ 缓存幂等（run_id 已存在则跳过）/ 断点续跑（重跑同 batch 自动续）/
预算护栏（--max-runs / --max-cost-usd 达到即停止调度新 run）。
真实模式走 claude CLI；--mock 走 dry-run 行为表（不烧 API，用于自验）。

用法：
    python -m backend.orchestrator.runner matrix/quick-lite.yaml --skill skills/tdd-v1 --mock
    python -m backend.orchestrator.runner matrix/quick-lite.yaml --skill skills/tdd-v1 \
        --batch q1 --max-cost-usd 10
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.orchestrator.matrix import expand_preset  # noqa: E402
from backend.orchestrator.dryrun import MOCK_BEHAVIOR, apply_patches, parse_pytest_score  # noqa: E402
from backend.validators.task_validator import _run_pytest  # noqa: E402
from backend.cli_driver.claude_driver import prepare_repo, run_claude  # noqa: E402

_LOCK = threading.Lock()


def grade(repo: Path, tests: Path, python: str) -> tuple[float, str]:
    """判分纯函数。POOL_V2 §3：tests/f2p + tests/p2p 双测试集结构时——
    score = (F2P 通过率) × (P2P 全过 ? 1 : 0)；旧结构（平铺 tests/）保持原逻辑。"""
    f2p_dir, p2p_dir = tests / "f2p", tests / "p2p"
    if f2p_dir.is_dir() and p2p_dir.is_dir():
        _, sum_f = _run_pytest(repo, f2p_dir, python)
        pf, ff, _ = parse_pytest_score(sum_f)
        _, sum_p = _run_pytest(repo, p2p_dir, python)
        pp, fp, _ = parse_pytest_score(sum_p)
        total_f = pf + ff
        gate = 1.0 if fp == 0 else 0.0
        score = (pf / total_f if total_f else 0.0) * gate
        return round(score, 4), f"f2p:{pf}/{total_f},p2p:{pp}/{pp + fp}"
    ok, summary = _run_pytest(repo, tests, python)
    passed, failed, score = parse_pytest_score(summary)
    return score, f"{passed}/{passed+failed}"


def exec_mock(run: dict, task_dir: Path, work: Path, python: str) -> dict:
    mode, wt_d1, wtok_d1 = MOCK_BEHAVIOR.get(run["inject"], ("first", 0, 0))
    patches = sorted((task_dir / "solution" / "sites").glob("*.patch"))
    repo = work / "repo"
    shutil.copytree(task_dir / "fixture", repo)
    sites_fixed = apply_patches(repo, patches, mode)
    score, tests = grade(repo, task_dir / "tests", python)
    wasted = run["difficulty"] == "D1"
    return {**run, "score": score, "tests": tests,
            "sites_fixed": sites_fixed, "sites_required": len(patches),
            "wasted_turns": wt_d1 if wasted else 0,
            "wasted_tokens": wtok_d1 if wasted else 0,
            "cost_usd": 0.0, "num_turns": 0, "wall_s": 0.0, "driver": "mock"}


def exec_real(run: dict, task_dir: Path, work: Path, python: str,
              skill_dir: Path | None, model: str | None, timeout_s: int,
              driver: str = "claude") -> dict:
    import os
    meta = yaml.safe_load((task_dir / "meta.yaml").read_text(encoding="utf-8"))
    # 臂级 Skill 覆盖（消融臂 A1-x<N>）：run.arm_skill 优先于全局 --skill
    if run.get("arm_skill"):
        skill_dir = Path(run["arm_skill"])
    fixture = task_dir / "fixture"
    trace_path = work / "trace.json"
    if driver == "claude":
        repo = prepare_repo(fixture, work / "repo", run["inject"], skill_dir)
        res = run_claude(meta["prompt"], repo, run["inject"], skill_dir, model,
                         timeout_s, trace_path)
    else:
        import os as _os
        env = dict(_os.environ)
        env.setdefault("DIS_API_KEY", _os.environ.get("DIS_API_KEY", ""))
        from backend.net_guard import subprocess_env as _ng_env
        env = _ng_env(env)  # 代理免疫：剥掉 VPN 变量+白名单
        if driver == "codex":
            from backend.cli_driver.codex_driver import (
                prepare_repo as cx_prepare, run_codex)
            repo = cx_prepare(fixture, work / "repo", run["inject"], skill_dir)
            res = run_codex(meta["prompt"], repo, run["inject"], skill_dir, model,
                            timeout_s, trace_path, env)
        elif driver == "pi":
            from backend.cli_driver.pi_driver import (
                prepare_repo as pi_prepare, run_pi)
            repo = pi_prepare(fixture, work / "repo", run["inject"], skill_dir)
            res = run_pi(meta["prompt"], repo, run["inject"], skill_dir, model,
                         timeout_s, trace_path, env)
        elif driver == "pi-docker":
            from backend.cli_driver.pi_docker_driver import (
                prepare_repo as pid_prepare, run_pi_docker)
            repo = pid_prepare(fixture, work / "repo", run["inject"], skill_dir)
            res = run_pi_docker(meta["prompt"], repo, run["inject"], skill_dir,
                                model, timeout_s, trace_path, env)
        else:
            raise ValueError(f"未知 driver：{driver}")
    rec = {**run, "cost_usd": round(res.cost_usd, 4), "num_turns": res.num_turns,
           "input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
           "cache_creation_tokens": res.cache_creation_tokens,
           "wall_s": round(res.wall_s, 1), "driver": driver,
           # 渠道健康协议（2026-10-02 混淆发现后立）：token 吞吐 = 出token/墙钟
           "tps": round(res.output_tokens / res.wall_s, 2) if res.wall_s > 0 else 0.0,
           "trace_ref": str(res.trace_path)}
    try:  # B7 env 轨：环境快照（失败不阻塞主链）
        from backend.env_track import collect as _env_collect
        rec["env"] = _env_collect(driver, model)
    except Exception:
        pass
    if not res.ok:
        rec.update(score=0.0, tests="error", error=res.error)
        return rec
    score, tests = grade(repo, task_dir / "tests", python)
    rec.update(score=score, tests=tests)
    # 死跑检测（pilot-hard-1 实测发现）：agent 未修改任何文件（repo 与 fixture 逐字节一致）
    # → 基建性失败而非能力失败，标记 dead=True，统计时应与能力失败分开
    import filecmp
    def _trees_identical(a: Path, b: Path) -> bool:
        cmp = filecmp.dircmp(a, b)
        if cmp.left_only or cmp.right_only or cmp.diff_files:
            return False
        return all(_trees_identical(a / name, b / name) for name in cmp.subdirs)
    try:
        if _trees_identical(repo, task_dir / "fixture"):
            rec["dead"] = True
            rec["error"] = "dead_run: agent 未修改任何文件"
    except Exception:
        pass
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(prog="skill-bench run")
    ap.add_argument("preset")
    ap.add_argument("--skill", help="Skill 目录（forced/auto 臂需要）")
    ap.add_argument("--tasks", default=None,
                    help="任务目录（缺省用预设 tasks.source，再缺省 tasks/generated；"
                         "显式传入时若与预设 source 不同会告警——两次踩坑后的护栏）")
    ap.add_argument("--batch", default=None, help="批次名（默认 <preset>-<时间戳>）")
    ap.add_argument("--mock", action="store_true", help="不烧 API 的自验模式")
    ap.add_argument("--max-runs", type=int, default=0, help="最多执行 N 个 run（0=不限）")
    ap.add_argument("--max-cost-usd", type=float, default=0.0, help="成本上限（0=不限）")
    ap.add_argument("--driver", default="claude", choices=["claude", "codex", "pi", "pi-docker"],
                    help="执行驱动（codex/pi 走 r.dis.115.zone deepseek 线；"
                         "pi-docker = pi 跑在 WSL docker 沙箱内，答案材料物理不可达）")
    ap.add_argument("--model", default=None,
                    help="显式指定模型（codex/pi 线透传，如 glm-5.3；覆盖预设）")
    args = ap.parse_args()

    preset = yaml.safe_load(Path(args.preset).read_text(encoding="utf-8"))
    if "arms" not in preset:
        print("runner 目前支持分诊档形态（quick-lite / quick）")
        return 1
    skill_dir = Path(args.skill) if args.skill else None
    # 模型短名映射（B0 探活：新中转站 key 三档全通，2026-09-26；
    # 旧记录"haiku/sonnet 403"已失效，见 docs/EXPERIMENT_LOG.md B0 节）
    MODEL_ALIASES = {
        "haiku": "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-5",
        "opus": "claude-opus-5",
    }
    raw_model = preset.get("model")
    if args.driver != "claude":
        # codex/pi 线：--model 显式参数 > 预设 model（非 claude 别名时）> 驱动默认
        if args.model:
            model = args.model
        elif raw_model and raw_model not in MODEL_ALIASES:
            model = raw_model
        else:
            model = None  # 驱动默认（deepseek-v4.1-flash）
    else:
        model = MODEL_ALIASES.get(raw_model, raw_model)
        if model in (None, "default"):
            model = None  # None = CLI 默认模型

    # 任务目录解析优先级：显式 --tasks > 预设 tasks.source > tasks/generated
    preset_src = preset.get("tasks", {}).get("source")
    if args.tasks is None:
        args.tasks = preset_src or "tasks/generated"
    elif preset_src and Path(args.tasks).as_posix() != Path(preset_src).as_posix():
        print(f"⚠️  --tasks ({args.tasks}) 与预设 source ({preset_src}) 不一致，"
              f"以 --tasks 为准（heldout-final/forged 两次踩坑后的护栏）")
    runs, _, warns = expand_preset(preset, Path(args.tasks))
    batch = args.batch or f"{preset['name']}-{time.strftime('%m%d-%H%M')}"
    out_dir = Path("results") / batch
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = out_dir / "runs.jsonl"

    done: set[str] = set()
    spent = 0.0
    if jsonl.exists():  # 断点续跑：成功的 run 跳过；error 记录保留但允许重试
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if "error" not in rec:
                done.add(rec["run_id"])
            spent += rec.get("cost_usd", 0.0)
    todo = [r.__dict__ for r in runs if r.run_id not in done]
    if args.max_runs:
        todo = todo[: args.max_runs]
    print(f"批次 {batch}：总 {len(runs)} run，已完成 {len(done)}，本次执行 {len(todo)}"
          f"（已花费 ${spent:.2f}）模式={'mock' if args.mock else 'REAL'}")
    for w in warns:
        print(f"⚠️  {w}")
    if not todo:
        print("无待执行 run")
        return 0

    python = sys.executable
    conc = preset.get("concurrency", 4) if not args.mock else len(todo) or 1
    timeout_s = preset.get("timeout_min", 12) * 60
    results: list[dict] = []

    def work(run: dict) -> dict:
        wdir = out_dir / "work" / run["run_id"]
        wdir.mkdir(parents=True, exist_ok=True)
        if args.mock:
            return exec_mock(run, Path(args.tasks) / run["task_id"], wdir, python)
        return exec_real(run, Path(args.tasks) / run["task_id"], wdir, python,
                         skill_dir, model, timeout_s, driver=args.driver)

    with ThreadPoolExecutor(max_workers=conc) as pool, \
            open(jsonl, "a", encoding="utf-8") as f:
        futures = {}
        for r in todo:
            if args.max_cost_usd and spent >= args.max_cost_usd:
                print(f"💰 达到成本上限 ${args.max_cost_usd}，停止调度新 run")
                break
            futures[pool.submit(work, r)] = r
        for fut in as_completed(futures):
            rec = fut.result()
            with _LOCK:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                spent += rec.get("cost_usd", 0.0)
            results.append(rec)
            print(f"[{rec['arm']:4s}] {rec['task_id']:14s} score={rec.get('score')}"
                  f" tests={rec.get('tests')} cost=${rec.get('cost_usd', 0):.3f}"
                  f" turns={rec.get('num_turns')} wall={rec.get('wall_s')}s")

    ok = [r for r in results if r.get("score", 0) == 1.0]
    print(f"\n本批 {len(results)} run 完成，满分 {len(ok)}，累计花费 ${spent:.2f}，"
          f"输出 {jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
