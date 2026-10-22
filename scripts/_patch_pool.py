"""eval_skill 混合池三修（2026-10-10）：随机抽样 + 超时22 + 池快照。"""
from pathlib import Path
import ast

p = Path("scripts/eval_skill.py")
t = p.read_text(encoding="utf-8")

old_pick = '''def pick_tasks(n_per_diff: int) -> list[str]:
    """内置集按难度挑任务（确定性排序，D1/D2/D3 各 n_per_diff）。"""
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
    out = []
    for d in ("D1", "D2", "D3"):
        out += by_diff[d][:n_per_diff]
    return out'''

new_pick = '''def pool_info() -> dict:
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
    return out'''

assert old_pick in t, "pick_tasks not found"
t = t.replace(old_pick, new_pick)
t = t.replace("timeout_min: 12", "timeout_min: 22")
t = t.replace('_STATUS = {"eval": disp_name, "dev": args.dev, "tier": args.tier,',
              '_STATUS = {"eval": disp_name, "dev": args.dev, "tier": args.tier,\n               "pool": pool_info(),')
p.write_text(t, encoding="utf-8", newline="\n")
ast.parse(t)
print("后端三修完成")

# 验证：抽两次，池面应不同且含真题
import sys
sys.path.insert(0, "scripts")
import importlib.util
spec = importlib.util.spec_from_file_location("es", "scripts/eval_skill.py")
# 不执行 main，只调函数——直接复制函数逻辑太重，改用子进程方式测
