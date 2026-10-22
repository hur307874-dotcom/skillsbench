"""一次性修复：清掉坏 baseline 行，按正确 YAML 重填。"""
from pathlib import Path

baselines = {
    "forged-boundary-allequal": ("0.90", "天花板侧（成本区分用）"),
    "forged-cachedrop-sieve": ("1.00", "天花板侧（成本区分用）"),
    "forged-argswap-sieve": ("1.00", "天花板侧（成本区分用）"),
    "forged-renameleak-islice": ("1.00", "天花板侧（成本区分用）"),
    "forged-multi-sieve": ("0.33", "带内（分数区分主力）"),
    "forged-multi-dual": ("0.97", "天花板侧偏带内（方差大）"),
    "forged-multi-crossfile": ("1.00", "天花板侧（成本区分用）"),
    "forged-multi-taketail": ("1.00", "天花板侧（成本区分用）"),
    "forged-multi-triple": ("0.33", "地板（双臂 0/3 超时，登记为边界样本，不入主矩阵）"),
}
base = Path("tasks/pool-v2/forged-final")
for tid, (rate, role) in baselines.items():
    mp = base / tid / "meta.yaml"
    lines = mp.read_text(encoding="utf-8").splitlines()
    # 剔除坏行（含 /n 的行、旧 baseline 块）
    cleaned = []
    skip = False
    for l in lines:
        if l.startswith("baseline:"):
            skip = True
            continue
        if skip and (l.startswith("  ") or not l.strip()):
            continue
        skip = False
        if "/n" in l:
            continue
        cleaned.append(l)
    cleaned.append("baseline:")
    cleaned.append(f"  deepseek-v4.1-flash-A0: {rate}  # pilot 实测完成率")
    cleaned.append(f'  role: "{role}"')
    mp.write_text("\n".join(cleaned) + "\n", encoding="utf-8")
    print("fixed:", tid)
