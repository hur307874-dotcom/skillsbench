"""诊断 pool-v3 A0 死跑：agent 到底做了什么（一次性）。"""
import json
from pathlib import Path

base = Path("results/poolv3c-deploykit")
recs = {}
for line in (base / "runs.jsonl").open(encoding="utf-8"):
    r = json.loads(line)
    recs[r["run_id"]] = r

dead_a0 = [r for r in recs.values() if r["arm"] == "A0" and r.get("dead")]
print("A0 死跑：", [r["run_id"] for r in dead_a0])

for r in dead_a0[:2]:
    tp = base / "work" / r["run_id"] / "trace.json"
    if not tp.exists():
        print(r["run_id"], "无 trace"); continue
    cmds, says = [], []
    for line in tp.open(encoding="utf-8"):
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("type") == "tool_execution_start":
            cmds.append(f"{e.get('toolName')}: {str(e.get('args'))[:130]}")
        if e.get("type") == "message_end":
            m = e.get("message", {})
            if m.get("role") == "assistant":
                for c in m.get("content", []):
                    if c.get("type") == "text" and c.get("text", "").strip():
                        says.append(c["text"].strip()[:200])
    print(f"\n--- {r['run_id']}（turns={r.get('num_turns')} wall={r.get('wall_s')}s）"
          f"工具 {len(cmds)} 次，发言 {len(says)} 段 ---")
    for c in cmds[:10]:
        print("  工具 |", c)
    for s in says[-2:]:
        print("  发言 |", s.replace("\n", " "))
