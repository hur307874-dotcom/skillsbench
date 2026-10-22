"""修 mined-v2 的 task_id（name[15:] 切片丢首字母 bug）+ 合流 tasks/generated。"""
import re
import shutil
from pathlib import Path

V2 = Path("tasks/mined-v2")
GEN = Path("tasks/generated")
PREFIX = "moreitertools-"

fixed = merged = 0
for d in sorted(V2.iterdir()):
    mf = d / "meta.yaml"
    if not mf.exists():
        continue
    correct_tid = "mined2-" + d.name[len(PREFIX):]
    c = mf.read_text(encoding="utf-8")
    c2 = re.sub(r"task_id:\s*\S+", f"task_id: {correct_tid}", c, count=1)
    if c2 != c:
        mf.write_text(c2, encoding="utf-8", newline="\n")
        fixed += 1
    shutil.copytree(d, GEN / correct_tid, dirs_exist_ok=True)
    merged += 1
print(f"task_id 修正 {fixed}，合流 {merged} → tasks/generated")

# 更新决定性候选池：加入全部合格真题（替换昨晚的 2 题引用为全量）
eval_skill = Path("scripts/eval_skill.py")
t = eval_skill.read_text(encoding="utf-8")
ids = sorted(p.name for p in GEN.iterdir() if p.name.startswith("mined2-"))
block = "    # 真实 issue 形态（2026-10-09 归一入库，四关过）\n    \"mined-exactly_n\", \"mined-substrings2\","
new_block = ("    # 真实 issue 形态（2026-10-10 MINED-B1 过滤入库，37 题四关过）\n"
             + "".join(f'    "{i}",\n' for i in ids[:12]) + "    # ……其余在池内由 pick_tasks 抽样")
assert block in t
t = t.replace(block, new_block.rstrip("\n"))
eval_skill.write_text(t, encoding="utf-8", newline="\n")
import ast
ast.parse(t)
print(f"候选池 +{min(12, len(ids))} 真题（全池 pick_tasks 可用 {len(ids)} 题）")
