"""eval_skill 双保险补丁（2026-10-11 凌晨，48×r01 死循环 + NaN 判词事故）。"""
from pathlib import Path
import ast

p = Path("scripts/eval_skill.py")
t = p.read_text(encoding="utf-8")

# ① refill：同一 run_id 最多尝试 2 次（原逻辑删掉死行再补跑，死行复活循环无上限）
old_refill = '''def refill(batch: Path, preset: Path, driver: str, log: Path,
           rounds: int = 2) -> None:
    """渠道死自愈：剔除 usage=0 死跑 → 串行降速补跑（≤rounds 轮）。"""
    for rd in range(rounds):
        rows = load_runs(batch)
        dead = [r for r in rows if channel_dead(r)]
        if not dead:
            return
        log.open("a", encoding="utf-8").write(
            f"  自愈轮 {rd+1}：{len(dead)} 个渠道死，串行补跑\\n")
        f = batch / "runs.jsonl"
        kept = [json.dumps(r, ensure_ascii=False) + "\\n" for r in rows
                if not channel_dead(r)]
        f.write_text("".join(kept), encoding="utf-8")
        for _ in dead:
            sh([PY, "-m", "backend.orchestrator.runner", str(preset),
                "--driver", driver, "--batch", batch.name, "--max-runs", "1"], log)'''
new_refill = '''def refill(batch: Path, preset: Path, driver: str, log: Path,
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
            f"  自愈轮 {rd+1}：{len(dead)} 个渠道死（已达上限的跳过），串行补跑\\n")
        f = batch / "runs.jsonl"
        kept = [json.dumps(r, ensure_ascii=False) + "\\n" for r in rows
                if not channel_dead(r)]
        f.write_text("".join(kept), encoding="utf-8")
        for _ in dead:
            sh([PY, "-m", "backend.orchestrator.runner", str(preset),
                "--driver", driver, "--batch", batch.name, "--max-runs", "1"], log)'''
assert old_refill in t, "refill not found"
t = t.replace(old_refill, new_refill)

# ② 判定块：有效 run 不足 → inconclusive（原逻辑 NaN-NaN 落入 decisive-null 垃圾判词）
old_dec = '''    d = m1 - m0
    if d >= 0.15:
        return "decisive-positive", detail
    if d <= -0.15:
        return "decisive-negative", detail
    return "decisive-null", detail'''
new_dec = '''    if not a0 or not a1:
        # 护栏（2026-10-11 事故）：验证批有效 run 全灭（渠道死）时，
        # NaN-NaN 的比较全 False 会落进 decisive-null 出垃圾判词
        detail["stat_note"] = f"验证批有效 run 不足（A0 {len(a0)}/A1f {len(a1)}，渠道死）——不结论"
        return "inconclusive", detail
    d = m1 - m0
    if d >= 0.15:
        return "decisive-positive", detail
    if d <= -0.15:
        return "decisive-negative", detail
    return "decisive-null", detail'''
assert old_dec in t, "decision block not found"
t = t.replace(old_dec, new_dec)

p.write_text(t, encoding="utf-8", newline="\n")
ast.parse(t)
print("双保险已上：①refill run_id 尝试上限 ×2 ②空数据→inconclusive")
