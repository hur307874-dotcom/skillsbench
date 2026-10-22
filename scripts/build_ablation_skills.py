"""消融 Skill 变体生成器：按 manifest 的 lines 逐条删除，产出 skills/ablation/I<N>/SKILL.md。

A1-x<N> 臂 = 强制注入"删掉第 N 条指令的 SKILL.md"（准实验：唯一变量是被删的那条）。
行号 1-indexed，与 manifest.instructions[].lines 对齐；删行后头部注明变体身份
（防止与原版混淆，注入文本里一眼可辨）。

用法：python scripts/build_ablation_skills.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "tdd-v1"
OUT = ROOT / "skills" / "ablation"


def main() -> int:
    manifest = yaml.safe_load((SKILL / "manifest.yaml").read_text(encoding="utf-8"))
    lines = (SKILL / "SKILL.md").read_text(encoding="utf-8").splitlines()
    for ins in manifest["instructions"]:
        iid = ins["id"]
        drop = set(ins["lines"])  # 1-indexed
        kept = [l for n, l in enumerate(lines, 1) if n not in drop]
        header = (f"<!-- ABLATION VARIANT {iid}: 已删除指令 {iid}（manifest lines "
                  f"{ins['lines'][0]}-{ins['lines'][-1]}），其余与 tdd-v1 一致 -->\n")
        out_dir = OUT / iid
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "SKILL.md").write_text(header + "\n".join(kept) + "\n", encoding="utf-8")
        print(f"{iid}: 删 {len(drop)} 行（{ins['text'][:40]}…）→ {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
