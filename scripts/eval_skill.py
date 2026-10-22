"""eval_skill 一命令调度器：放 Skill 进去，报告自己出来（成本侧 ~99% 无人值守）。

流水线（每一步都是实战教训的代码化）：
  0 预检：Skill 结构 + docker daemon + 渠道探测（B6，down 直接熔断不烧 run）
  1 B1.5 冒烟（6 run）：A0 真没注入 / A1f 真注入 / 判分与 trace 正常——查坑不查结论
  2 quick-lite 分诊（12 run）：符号 + 成本比 → 出局 / 补 quick / 升 standard
  3 quick 48（可选升级）
  自愈：每批后渠道死二分（usage=0 串行补跑 ≤2 轮；usage>0 合法无编辑保留）；
       maxTokens 撞顶（output=8192 且无编辑）记 artifact 不误判
  4 聚合：cli_report 出各批报告 + 总判定一句话 + verdict.json

用法：
    python scripts/eval_skill.py skills/tdd-v1
    python scripts/eval_skill.py skills/tdd-v1 --tier quick      # 升到 48 封顶
    python scripts/eval_skill.py skills/tdd-v1 --dev             # 管线自检（2 任务）
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PY = sys.executable
MAXTOK_CAP = 8192

# 状态机（前端轮询用）：每阶段写 status.json
_WORK: Path | None = None
_STATUS: dict = {}


def set_status(stage: str, **extra) -> None:
    if _WORK is None:
        return
    # STOP 旗标：用户点了停止——阶段切换时优雅退出（硬杀之外的第二道）
    if stage != "stopped" and (_WORK / "STOP").exists():
        _STATUS.update({"stage": "stopped",
                        "updated_at": time.strftime("%H:%M:%S")})
        (_WORK / "status.json").write_text(
            json.dumps(_STATUS, ensure_ascii=False, indent=1), encoding="utf-8")
        print("⏹ 收到 STOP 旗标，优雅退出")
        sys.exit(3)
    _STATUS.update({"stage": stage, "updated_at": time.strftime("%H:%M:%S"), **extra})
    (_WORK / "status.json").write_text(
        json.dumps(_STATUS, ensure_ascii=False, indent=1), encoding="utf-8")


def sh(cmd: list[str], log: Path, timeout: int = 0) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(f"\n$ {' '.join(str(c) for c in cmd)}\n")
        f.flush()
        p = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
                           timeout=timeout or None)
    return p.returncode


def load_runs(batch: Path) -> list[dict]:
    f = batch / "runs.jsonl"
    if not f.exists():
        return []
    latest: dict[str, dict] = {}
    for line in f.open(encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            latest[r.get("run_id", "?")] = r
    return list(latest.values())


def channel_dead(r: dict) -> bool:
    return not (r.get("input_tokens") or r.get("output_tokens")) and (
        "timeout" in str(r.get("error", "")) or "error" in r or r.get("dead"))


def maxtok_artifact(r: dict) -> bool:
    return r.get("output_tokens") == MAXTOK_CAP and r.get("dead")


def refill(batch: Path, preset: Path, driver: str, log: Path,
           rounds: int = 2) -> None:
    """渠道死自愈：剔除 usage=0 死跑 → 串行降速补跑（≤rounds 轮）。
    护栏（2026-10-11 事故）：同一 run_id 累计尝试 ≥2 次直接放弃——
    原逻辑删死行→补跑→又死→再删再补，r01 曾被循环 48 次。"""
    for rd in range(rounds):
        rows = load_runs(batch)
        attempts: dict[str, int] = {}
        for r in rows:
            attempts[r["run_id"]] = attempts.get(r["run_id"], 0) + 1
        dead = [r for r in rows if channel_dead(r)
                and attempts.get(r["run_id"], 0) < 2]
        if not dead:
            return
        log.open("a", encoding="utf-8").write(
            f"  自愈轮 {rd+1}：{len(dead)} 个渠道死（已达上限的跳过），串行补跑\n")
        f = batch / "runs.jsonl"
        kept = [json.dumps(r, ensure_ascii=False) + "\n" for r in rows
                if not channel_dead(r)]
        f.write_text("".join(kept), encoding="utf-8")
        for _ in dead:
            sh([PY, "-m", "backend.orchestrator.runner", str(preset),
                "--driver", driver, "--batch", batch.name, "--max-runs", "1"], log)


def pool_info() -> dict:
    """池构成快照（写进 status/verdict——池版本可观测）。"""
    import yaml
    by_diff: dict[str, list[str]] = {"D1": [], "D2": [], "D3": []}
    for meta in sorted((ROOT / "tasks/generated").glob("*/meta.yaml")):
        try:
            m = yaml.safe_load(meta.read_text(encoding="utf-8"))
            d = (m or {}).get("difficulty", "D1")
            if m.get("task_id") and d in by_diff:
                by_diff[d].append(m["task_id"])
        except Exception:  # noqa: BLE001
            continue
    total = sum(len(v) for v in by_diff.values())
    mined = sum(1 for v in by_diff.values() for t in v if t.startswith("mined"))
    return {"by_diff": {k: len(v) for k, v in by_diff.items()},
            "total": total, "mined_real": mined,
            "version": f"generated-v4(合成 {total - mined} + 真实 {mined})"}


def pick_tasks(n_per_diff: int, seed: str = "") -> list[str]:
    """按难度**随机抽样**（2026-10-10 混合池后改：确定性前 n 会让
    39 道真题永远排不上号；种子=评测戳，单次可复现、次次不同池面）。"""
    import random
    import yaml
    by_diff: dict[str, list[str]] = {"D1": [], "D2": [], "D3": []}
    for meta in sorted((ROOT / "tasks/generated").glob("*/meta.yaml")):
        try:
            m = yaml.safe_load(meta.read_text(encoding="utf-8"))
            d = (m or {}).get("difficulty", "D1")
            if m.get("task_id") and d in by_diff:
                by_diff[d].append(m["task_id"])
        except Exception:  # noqa: BLE001
            continue
    rng = random.Random(seed or time.strftime("%H%M%S"))
    out = []
    for d in ("D1", "D2", "D3"):
        pool = by_diff[d]
        out += rng.sample(pool, min(n_per_diff, len(pool)))
    return out


def write_preset(path: Path, name: str, tasks: list[str], skill: Path,
                 repeats: int, driver_model: str | None,
                 placebo: bool = False) -> None:
    only = "[" + ", ".join(tasks) + "]"
    a0p = ("  - { id: A0p, inject: forced, skill: "
           "D:/ai_project/skill-bench/skills/placebo-cooking }\n") if placebo else ""
    txt = f"""name: {name}
description: "eval_skill 自动生成（{time.strftime('%m-%d %H:%M')}）"
arms:
  - {{ id: A0, inject: none }}
{a0p}  - {{ id: A1f, inject: forced, skill: {skill.as_posix()} }}
tasks:
  source: tasks/generated
  only: {only}
repeats: {repeats}
model: {driver_model or "deepseek-v4.1-flash"}
timeout_min: 22
concurrency: 4
"""
    path.write_text(txt, encoding="utf-8")


def paired_signal(rows: list[dict]) -> tuple[int, int, float, float]:
    """(正符号任务数, 配对总数, A0 均分出token, A1f 均分出token)。"""
    by_task: dict[str, dict[str, list[dict]]] = {}
    for r in rows:
        if channel_dead(r) or maxtok_artifact(r):
            continue
        by_task.setdefault(r.get("task_id", "?"), {}).setdefault(
            r.get("arm", "?"), []).append(r)
    pos = tot = 0
    a0_tok: list[float] = []
    a1_tok: list[float] = []
    for t, arms in by_task.items():
        if "A0" not in arms or "A1f" not in arms:
            continue
        a0 = sum(r["score"] for r in arms["A0"]) / len(arms["A0"])
        a1 = sum(r["score"] for r in arms["A1f"]) / len(arms["A1f"])
        tot += 1
        pos += a1 > a0
        a0_tok += [r.get("output_tokens", 0) for r in arms["A0"]]
        a1_tok += [r.get("output_tokens", 0) for r in arms["A1f"]]
    ma0 = sum(a0_tok) / len(a0_tok) if a0_tok else 0
    ma1 = sum(a1_tok) / len(a1_tok) if a1_tok else 0
    return pos, tot, ma0, ma1


# ---------- 卡点⑥：池天花板检测 + 决定性模式（2026-10-05  systematic-debugging 冤案教训） ----------

CEILING_SCORE = 0.95   # A0 均分 ≥ 此值 = 该题天花板
CEILING_RATIO = 2 / 3  # 天花板题占比 ≥ 此值 = 池天花板
BAND_LO, BAND_HI = 0.3, 0.7  # 决定性实验选题带（用户铁律：只要带头题）

DECISIVE_CANDIDATES = [  # 难题候选集（A0 探针用；heldout 永不进此表）
    "d3-state-hard", "d3-csv-01", "d3-ini-hard", "d3-mutable-01",
    "d3-round-01", "d3-bus-hard", "d3-cache-01",
    # 真实 issue 形态（2026-10-10 MINED-B1 过滤入库，37 题四关过）
    "mined2-exactly_n-1080",
    "mined2-exactly_n-1080-10",
    "mined2-exactly_n-1080-10-173557",
    "mined2-exactly_n-1080-10-174020",
    "mined2-iter_except-1080-37",
    "mined2-iter_except-1080-37-173557",
    "mined2-iter_except-1080-37-174020",
    "mined2-nth_combination-1080-41",
    "mined2-nth_combination-1080-41-173557",
    "mined2-nth_combination-1080-41-174020",
    "mined2-nth_combination_with_replacement-1080-22",
    "mined2-nth_combination_with_replacement-1080-22-173557",
    # ……其余在池内由 pick_tasks 抽样
]


def ceiling_stats(rows: list[dict]) -> tuple[int, int]:
    """(天花板任务数, A0 有分的任务总数)。"""
    by_task: dict[str, list[float]] = {}
    for r in rows:
        if r.get("arm") != "A0" or channel_dead(r) or maxtok_artifact(r):
            continue
        if isinstance(r.get("score"), (int, float)):
            by_task.setdefault(r.get("task_id", "?"), []).append(r["score"])
    tot = len(by_task)
    ceil = sum(1 for arr in by_task.values()
               if sum(arr) / len(arr) >= CEILING_SCORE)
    return ceil, tot


def decisive_mode(skill: Path, disp_name: str, stamp: str, work: Path,
                  log: Path, args) -> tuple[str, dict]:
    """决定性模式：候选集探针 → 带内选题 → A0/A1f × n=4 → 方向判定。

    返回 (decision, detail)。判词全部自带括号声明统计限制。
    """
    set_status("决定性-探针")
    print("== 决定性模式①：候选集 A0 探针 ==")
    pp = work / "probe.yaml"
    write_preset(pp, f"evalprobe-{disp_name}", DECISIVE_CANDIDATES,
                 skill, 2, args.model)
    # 探针只跑 A0：临时预设（借用 write_preset 后手动替换 arms）
    pp.write_text(pp.read_text(encoding="utf-8").replace(
        "  - { id: A1f, inject: forced, skill: " + skill.as_posix() + " }\n", ""),
        encoding="utf-8")
    b_probe = f"evalprobe-{disp_name}-{stamp}"
    sh([PY, "-m", "backend.orchestrator.runner", str(pp), "--driver", args.driver,
        "--batch", b_probe], log)
    refill(ROOT / "results" / b_probe, pp, args.driver, log, rounds=1)

    by_task: dict[str, list[float]] = {}
    for r in load_runs(ROOT / "results" / b_probe):
        if channel_dead(r):
            continue
        if isinstance(r.get("score"), (int, float)):
            by_task.setdefault(r["task_id"], []).append(r["score"])
    in_band = [t for t, arr in by_task.items()
               if BAND_LO <= sum(arr) / len(arr) <= BAND_HI]
    relaxed = ""
    if not in_band:
        # 放宽①：任一 A0 run < 0.95 且均分 ≥ 0.3（有方差=有带头——writing-plans
        # 实测：ini-hard 均分 0.875 但有 0.75 失手，均分带外但真有提升空间）
        in_band = [t for t, arr in by_task.items()
                   if min(arr) < 0.95 and sum(arr) / len(arr) >= BAND_LO]
        relaxed = "带头定义放宽：含方差题（任一 run<0.95）"
    if not in_band:
        # 放宽②：近全天花板也不停摆——取相对最难 3 题兜底（用户指令：先都跑一遍）
        by_mean = sorted(by_task.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
        in_band = [t for t, _ in by_mean[:3]]
        relaxed = "候选集近全天花板：取相对最难 3 题兜底验证"
    print(f"  入选验证题：{in_band or '无'}"
          f"{('（' + relaxed + '）') if relaxed else ''}"
          f"（探针 {sum(len(a) for a in by_task.values())} run）")

    if not in_band:  # 探针全灭（无有效 run）才是真·池枯竭
        return ("pool-exhausted",
                {"note": "探针无有效 run——渠道或任务集故障",
                 "probe_means": {t: round(sum(a)/len(a), 2)
                                 for t, a in by_task.items()}})

    set_status("决定性-验证批")
    print(f"== 决定性模式②：{in_band} × A0/A1f × n=4 ==")
    dp = work / "decisive.yaml"
    write_preset(dp, f"evaldecisive-{disp_name}", in_band, skill, 4, args.model)
    b_dec = f"evaldecisive-{disp_name}-{stamp}"
    sh([PY, "-m", "backend.orchestrator.runner", str(dp), "--driver", args.driver,
        "--batch", b_dec], log)
    refill(ROOT / "results" / b_dec, dp, args.driver, log, rounds=1)

    arm_scores: dict[str, list[float]] = {"A0": [], "A1f": []}
    for r in load_runs(ROOT / "results" / b_dec):
        if channel_dead(r) or not isinstance(r.get("score"), (int, float)):
            continue
        if r.get("arm") in arm_scores:
            arm_scores[r["arm"]].append(r["score"])
    a0, a1 = arm_scores["A0"], arm_scores["A1f"]
    m0 = sum(a0) / len(a0) if a0 else float("nan")
    m1 = sum(a1) / len(a1) if a1 else float("nan")
    fm0 = sum(1 for s in a0 if s >= 0.99)
    fm1 = sum(1 for s in a1 if s >= 0.99)
    detail = {"tasks": in_band, "a0_mean": round(m0, 3), "a1f_mean": round(m1, 3),
              "full_marks": f"A0 {fm0}/{len(a0)} vs A1f {fm1}/{len(a1)}",
              "batches": [b_probe, b_dec], "relaxed": relaxed,
              "stat_note": f"n={len(a0)}/{len(a1)} 单方向性证据，幅度需加厚"}
    if not a0 or not a1:
        # 护栏（2026-10-11 事故）：验证批有效 run 全灭（渠道死）时，
        # NaN-NaN 的比较全 False 会落进 decisive-null 出垃圾判词
        detail["stat_note"] = f"验证批有效 run 不足（A0 {len(a0)}/A1f {len(a1)}，渠道死）——不结论"
        return "inconclusive", detail
    d = m1 - m0
    if d >= 0.15:
        return "decisive-positive", detail
    if d <= -0.15:
        return "decisive-negative", detail
    return "decisive-null", detail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("skill", help="Skill 目录")
    ap.add_argument("--tier", choices=["quick-lite", "quick", "standard"],
                    default="standard", help="评测封顶档（默认 standard 全程；quick-lite/quick 备选）")
    ap.add_argument("--driver", default="pi-docker")
    ap.add_argument("--model", default=None)
    ap.add_argument("--dev", action="store_true", help="管线自检（2 任务 n=1）")
    args = ap.parse_args()

    skill = Path(args.skill).resolve()
    if not (skill / "SKILL.md").exists():
        print(f"✗ Skill 目录缺 SKILL.md：{skill}")
        return 2
    stamp = time.strftime("%m%d-%H%M")
    # 展示名去掉 API 接单时加的时间戳尾（避免 eval-<name>-<ts>-<ts> 双重戳）
    import re as _re
    disp_name = _re.sub(r"-\d{4}-\d{6}$", "", skill.name)
    work = ROOT / "results" / f"eval-{disp_name}-{stamp}"
    log = work / "eval.log"
    work.mkdir(parents=True, exist_ok=True)
    global _WORK, _STATUS
    _WORK = work
    _STATUS = {"eval": disp_name, "dev": args.dev, "tier": args.tier,
               "pool": pool_info(),
               "pid": __import__("os").getpid(),
               "started_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    set_status("预检")
    print(f"== eval_skill：{disp_name} → {work}")

    # ---- 0 预检 ----
    from backend.channel_probe import probe
    p = probe(n=2)
    if p["level"] == "down":
        print("✗ 渠道熔断（探测 0 成活）——不烧 run，渠道恢复后重跑")
        set_status("failed", reason="渠道熔断（探测 0 成活）")
        return 2
    if p["level"] == "degraded":
        print("⚠ 渠道降级（部分探针失败）——继续但补跑策略收紧")
    dk = subprocess.run(["wsl", "-d", "Ubuntu", "-u", "root", "--",
                         "docker", "info", "--format", "{{.ServerVersion}}"],
                        capture_output=True, timeout=60)
    if dk.returncode != 0:
        print("✗ docker daemon 不可用（wsl docker info 失败）")
        set_status("failed", reason="docker daemon 不可用")
        return 2
    print(f"✓ 预检：渠道 {p['level']}，docker {dk.stdout.decode('utf-8','replace').strip()}")
    set_status("冒烟", channel=p["level"])

    # ---- 1 B1.5 冒烟 ----
    smoke_tasks = pick_tasks(1)[:2] if args.dev else pick_tasks(1)
    sp = work / "smoke.yaml"
    write_preset(sp, f"evalsmoke-{disp_name}", smoke_tasks, skill, 1, args.model)
    print(f"== 冒烟（{len(smoke_tasks) * 2} run）==")
    sh([PY, "-m", "backend.orchestrator.runner", str(sp), "--driver", args.driver,
        "--batch", f"evalsmoke-{disp_name}-{stamp}"], log)
    sb = ROOT / "results" / f"evalsmoke-{disp_name}-{stamp}"
    rows = load_runs(sb)
    if not rows or all(channel_dead(r) for r in rows):
        print("✗ 冒烟全军覆没（渠道/驱动问题），终止。查 eval.log")
        set_status("failed", reason="冒烟全军覆没")
        return 2
    refill(sb, sp, args.driver, log, rounds=1)
    print(f"✓ 冒烟过（{len(load_runs(sb))} run）")
    set_status("分诊", smoke_runs=len(load_runs(sb)))

    # ---- 2 quick-lite 分诊 ----
    lite_tasks = smoke_tasks if args.dev else pick_tasks(2)
    lp = work / "quicklite.yaml"
    write_preset(lp, f"evallite-{disp_name}", lite_tasks, skill, 1, args.model)
    b_lite = f"evallite-{disp_name}-{stamp}"
    print(f"== quick-lite 分诊（{len(lite_tasks) * 2} run）==")
    sh([PY, "-m", "backend.orchestrator.runner", str(lp), "--driver", args.driver,
        "--batch", b_lite], log)
    refill(ROOT / "results" / b_lite, lp, args.driver, log)
    rows = load_runs(ROOT / "results" / b_lite)
    pos, tot, tok0, tok1 = paired_signal(rows)
    ratio = tok1 / tok0 if tok0 else 0
    print(f"分诊信号：正符号 {pos}/{tot}，成本比 ×{ratio:.2f}")
    set_status("聚合", signal=f"{pos}/{tot}", cost_ratio=round(ratio, 2))

    decision = "out"
    if args.dev:
        decision = "dev-stop"
    elif tot >= 3 and pos >= max(2, tot // 2):
        decision = "upgrade" if args.tier != "quick-lite" else "suspect"
    elif pos <= max(1, tot // 4):
        # 零增益：成本正常=出局；成本异常(>1.5)=出局但记成本异常（TDD 实测踩坑：
        # 0/6+×1.57 曾被错路由到"模糊"——零增益时成本异常是更坏的出局，不是模糊）
        decision = "out-cost-anomaly" if ratio > 1.5 else "out"
    else:
        decision = "suspect"

    # ---- 卡点⑥：零信号判词（出局/成本异常/低符号模糊）+ 池天花板 → 决定性模式 ----
    batches = [f"evalsmoke-{disp_name}-{stamp}", b_lite]
    decisive_detail: dict = {}
    zero_signal = decision in ("out", "out-cost-anomaly") or \
        (decision == "suspect" and pos <= 1)
    if zero_signal and not args.dev:
        ceil, ctot = ceiling_stats(rows)
        print(f"池天花板检测：{ceil}/{ctot} 题 A0≥{CEILING_SCORE}")
        if ctot and ceil / ctot >= CEILING_RATIO:
            print("⚠ 池天花板检出——零信号判词不成立，自动进入决定性模式")
            set_status("决定性模式", ceiling=f"{ceil}/{ctot}")
            decision, decisive_detail = decisive_mode(
                skill, disp_name, stamp, work, log, args)
            batches.extend(decisive_detail.get("batches", []))

    if decision == "upgrade" and args.tier in ("quick", "standard"):
        qp = work / "quick.yaml"
        # standard 档：quick 批带 A0p 安慰剂臂（排除长度/注意力效应——题目消融要求）
        write_preset(qp, f"evalquick-{disp_name}", pick_tasks(4), skill, 2,
                     args.model, placebo=(args.tier == "standard"))
        b_q = f"evalquick-{disp_name}-{stamp}"
        print(f"== 升级 quick 复测（{'带安慰剂臂' if args.tier == 'standard' else '双臂'}）==")
        set_status("升级quick")
        sh([PY, "-m", "backend.orchestrator.runner", str(qp), "--driver", args.driver,
            "--batch", b_q], log)
        refill(ROOT / "results" / b_q, qp, args.driver, log)
        batches.append(b_q)
        rows = load_runs(ROOT / "results" / b_q)
        pos, tot, tok0, tok1 = paired_signal(rows)
        decision = "confirmed-positive" if pos >= max(2, tot // 2) else "weak"
        set_status("聚合", decision=decision)

    # standard 档的确诊批：confirmed-positive 后再上 n=2 三臂确认（默认档必达）
    if decision == "confirmed-positive" and args.tier == "standard":
        sp2 = work / "standard.yaml"
        write_preset(sp2, f"evalstd-{disp_name}", pick_tasks(4), skill, 2,
                     args.model, placebo=True)
        b_s = f"evalstd-{disp_name}-{stamp}"
        print("== standard 确诊批（三臂 n=2）==")
        set_status("standard确诊批")
        sh([PY, "-m", "backend.orchestrator.runner", str(sp2), "--driver", args.driver,
            "--batch", b_s], log)
        refill(ROOT / "results" / b_s, sp2, args.driver, log)
        batches.append(b_s)
        rows = load_runs(ROOT / "results" / b_s)
        pos, tot, tok0, tok1 = paired_signal(rows)
        decision = ("standard-positive" if pos >= max(2, tot // 2)
                    else "standard-inconclusive")
        set_status("聚合", decision=decision)

    # ---- 4 聚合 ----
    print("== 聚合 ==")
    _rlx = f"（{decisive_detail['relaxed']}）" if decisive_detail.get("relaxed") else ""
    verdict_map = {
        "out": "分诊出局：在本任务池上看不到值得深测的信号（零增益且成本正常）",
        "out-cost-anomaly": f"零增益且成本异常（×{round(ratio, 2)}）：不推荐（仪式开销显著）",
        "suspect": "信号模糊：建议人工复核或换任务域复测",
        "weak": "quick 档复测后增益仍弱",
        "standard-positive": "standard 确诊：三臂复测仍显著为正（含安慰剂对照）",
        "standard-inconclusive": "standard 确诊批未复现正信号：降级为弱证据",
        "confirmed-positive": "分诊为正：值得进 standard 确诊档",
        "dev-stop": "管线自检完成（--dev）",
        "pool-exhausted": "池枯竭：探针无有效 run（渠道或任务集故障）",
        "decisive-positive": f"决定性为正：带头题上 Skill 臂显著高（{decisive_detail.get('full_marks','')}）——值得升级 standard{_rlx}",
        "decisive-negative": f"带头上强方向性负信号（{decisive_detail.get('full_marks','')}；n 小，幅度需加厚）{_rlx}",
        "decisive-null": f"带头上亦零增益：饱和判定坐实（裸考做不对的题，读了文档也做不对）{_rlx}",
    }
    for b in batches:
        sh([PY, "-m", "backend.analysis.cli_report", str(ROOT / "results" / b)], log)
    v = {"skill": disp_name, "decision": decision,
         "verdict": verdict_map[decision],
         "signal": {"positive_pairs": f"{pos}/{tot}", "cost_ratio": round(ratio, 2)},
         "batches": batches, "channel": p["level"],
         "decisive": decisive_detail,
         "finished_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    (work / "verdict.json").write_text(json.dumps(v, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    set_status("done", decision=decision, verdict=v["verdict"],
               signal=v["signal"]["positive_pairs"],
               cost_ratio=v["signal"]["cost_ratio"])
    print(f"\n===== 判定：{v['verdict']} =====")
    print(f"产物：{work}（verdict.json + eval.log + 各批 report.md）")
    print("提示：归因阳性结论在 κ 过门前标'待复核'；价值侧（pool-v3 族）需 family-generator")
    return 0


if __name__ == "__main__":
    sys.exit(main())
