"""process_judge：LLM 过程判分件（MT-Bench 红线全守：仅辅助、带校准门、双人复核）。

使用约束（写死在本模块 docstring，违反即设计错误）：
1. 主判分永远是机械 pytest；本模块只产出辅助信号（过程质量描述）；
2. 输出必须过 κ 校准门（与人工标注 κ≥0.7 才可自动采信，否则只定性披露）；
3. 判分输入只许读归因器的违规日志（带证据行号），不许读原始轨迹全文
   （AgenTracer 警示：LLM 直接判轨迹归因准确率 <10%）；
4. 位置偏倚缓解：维度打分时顺序随机化，且每个维度独立调用。

用法：
    python -m backend.graders.process_judge --run <run_id> --batch <batch>
    （dry-run 模式：不调用 LLM，只组装 prompt 并打印，供校准审查）
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

DIMENSIONS = [
    ("recon", "侦察质量：修改前是否先定位/复现（读代码、跑失败用例）"),
    ("verification", "验证质量：修改后是否运行了测试并依据结果迭代"),
    ("scope", "范围纪律：改动是否限于任务必要范围（无顺手重构/投机新增）"),
    ("efficiency", "过程效率：是否存在明显空转/重复劳动"),
]

PROMPT_TMPL = """你是过程质量评审员。以下是一次代码修复任务的【违规与行为日志】
（带事件编号证据，已经机械检测器预处理——不要臆造日志外的事实）。

任务：{task_id}
最终机器判分：{score}（{tests}）

日志：
{log}

请只评估维度「{dim_name}」：{dim_desc}
输出 JSON：{{"score": 1-5 整数, "evidence": ["#事件号", ...], "note": "<=40字"}}
"""


def build_judge_prompts(run_id: str, task_id: str, score, tests: str,
                        violation_log: list[str], seed: int = 42) -> list[dict]:
    """组装逐维度 prompt（顺序随机化 = 位置偏倚缓解）。"""
    dims = DIMENSIONS[:]
    random.Random(seed).shuffle(dims)
    log_text = "\n".join(violation_log) if violation_log else "（无违规记录）"
    return [{"dimension": name,
             "prompt": PROMPT_TMPL.format(task_id=task_id, score=score,
                                          tests=tests, log=log_text,
                                          dim_name=name, dim_desc=desc)}
            for name, desc in dims]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--score", default="?")
    ap.add_argument("--tests", default="")
    ap.add_argument("--judge", action="store_true",
                    help="实调辅助 LLM（backend.llm_client，DIS relay）；"
                         "默认 dry-run 只组装 prompt")
    args = ap.parse_args()

    # dry-run：从归因器拉违规日志（机械预处理），组装 prompt 供审查
    from backend.attribution.engine import (attribute_run, load_events,
                                            load_fids, load_run_records,
                                            load_sites_required)
    fids = load_fids()
    evs = load_events([args.run], args.batch).get(args.run, [])
    rec = load_run_records(args.batch).get(args.run, {})
    sr = load_sites_required().get(rec.get("task_id", ""), 1)
    attr = attribute_run(args.run, evs, rec, sr, fids)
    log = [f"#{i} [{h['f_id']}] {h['note']}（置信 {h['confidence']}）"
           for h in attr["hits"] for i in (h["evidence_idx"] or ["-"])]
    prompts = build_judge_prompts(args.run, rec.get("task_id", "?"),
                                  args.score or rec.get("score", "?"),
                                  args.tests or rec.get("tests", ""), log)
    print(f"process_judge：{args.run}（维度 {len(prompts)} 个，顺序已随机化；"
          f"仅辅助信号，不过 κ 门不入主报告）")
    if not args.judge:
        for p in prompts:
            print(f"\n===== 维度 {p['dimension']} =====")
            print(p["prompt"][:400])
        return 0
    # 实调路径：辅助 LLM（DIS relay，backend.llm_client——评测对象不走这里）
    from backend.llm_client import chat
    for p in prompts:
        out = chat([{"role": "user", "content": p["prompt"]}], max_tokens=256)
        print(f"\n===== 维度 {p['dimension']} =====")
        print(out.strip()[:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
