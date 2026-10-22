"""B0 真实纵切：d2-enum-01 × A0/A1f × claude-haiku-4-5-20251001。

验证四件事：
1. claude CLI 经中转站真实跑通（auth + NO_PROXY 生效）；
2. stream-json 事件流完整（assistant/tool_use/result），可定死 trace schema；
3. 判分器对真实 run 的 repo 状态打分正常；
4. 记录真实成本，校准 ~700 run 预算。

用法：python scripts/b0_vertical.py
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.cli_driver.claude_driver import prepare_repo, run_claude  # noqa: E402
from backend.validators.task_validator import _run_pytest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TASK = ROOT / "tasks" / "generated" / "d2-enum-01"
SKILL = ROOT / "skills" / "tdd-v1"
MODEL = "claude-haiku-4-5-20251001"
TIMEOUT_S = 600
OUT = ROOT / "results" / "b0-vertical"


def main() -> int:
    meta = yaml.safe_load((TASK / "meta.yaml").read_text(encoding="utf-8"))
    summary = []
    for inject, arm in [("none", "A0"), ("forced", "A1f")]:
        work = OUT / arm
        work.mkdir(parents=True, exist_ok=True)
        repo = prepare_repo(TASK / "fixture", work / "repo", inject, SKILL)
        print(f"[{arm}] 开跑（inject={inject}, model={MODEL}）...", flush=True)
        res = run_claude(meta["prompt"], repo, inject, SKILL, MODEL,
                         TIMEOUT_S, work / "trace.jsonl")
        ok_g, gsum = ("-", "-")
        if res.ok:
            ok_g, gsum = _run_pytest(repo, TASK / "tests", sys.executable)
        print(f"[{arm}] ok={res.ok} turns={res.num_turns} "
              f"cost=${res.cost_usd:.4f} in={res.input_tokens} "
              f"out={res.output_tokens} cache={res.cache_creation_tokens} "
              f"wall={res.wall_s:.0f}s grade={ok_g}({gsum}) err={res.error[:120]}",
              flush=True)
        summary.append((arm, res.ok, ok_g))
    failed = [a for a, ok, _ in summary if not ok]
    print("\n纵切结果：" + ("全部跑通" if not failed else f"{failed} 执行失败，先查 trace"))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
