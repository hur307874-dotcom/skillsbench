"""一次性补丁：process_judge 接入辅助 LLM 客户端（--judge 实调路径）。"""
from pathlib import Path

p = Path("backend/graders/process_judge.py")
t = p.read_text(encoding="utf-8")

t = t.replace(
    '''    ap.add_argument("--score", default="?")
    ap.add_argument("--tests", default="")
    args = ap.parse_args()''',
    '''    ap.add_argument("--score", default="?")
    ap.add_argument("--tests", default="")
    ap.add_argument("--judge", action="store_true",
                    help="实调辅助 LLM（backend.llm_client，DIS relay）；"
                         "默认 dry-run 只组装 prompt")
    args = ap.parse_args()''')

t = t.replace(
    '''    print(f"process_judge dry-run：{args.run}（维度 {len(prompts)} 个，"
          f"顺序已随机化；仅辅助信号，不过 κ 门不入主报告）")
    for p in prompts:
        print(f"\\n===== 维度 {p['dimension']} =====")
        print(p["prompt"][:400])
    return 0''',
    '''    print(f"process_judge：{args.run}（维度 {len(prompts)} 个，顺序已随机化；"
          f"仅辅助信号，不过 κ 门不入主报告）")
    if not args.judge:
        for p in prompts:
            print(f"\\n===== 维度 {p['dimension']} =====")
            print(p["prompt"][:400])
        return 0
    # 实调路径：辅助 LLM（DIS relay，backend.llm_client——评测对象不走这里）
    from backend.llm_client import chat
    for p in prompts:
        out = chat([{"role": "user", "content": p["prompt"]}], max_tokens=256)
        print(f"\\n===== 维度 {p['dimension']} =====")
        print(out.strip()[:300])
    return 0''')

p.write_text(t, encoding="utf-8")
print("patched")
