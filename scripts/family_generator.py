"""family-generator 骨架：pool-v3 价值侧半自动出题机。

流水线（设计权给 LLM，验收权给机器，签字权给人）：
  1 知识提取：辅助 LLM 读 SKILL.md → 可机器校验的规则清单（JSON）
  2 约定族起草：辅助 LLM 生成 fixture/行为测试/约定测试/gold/错解/INTENT/meta
  3 机器硬检：命名黑名单 + fixture 中性扫描（规则字面量不得出现在 fixture）
  4 四关校验（task_validator）
  5 Pilot 门：A0 × 3（pi-docker）→ 均分 ≤0.6 才算真缺口，否则带反馈打回（≤3 轮）
     打回耗尽 = 合法结局"该 Skill 知识不构成缺口"（同 tdd）
  6 产出确认批预设（A0/A0p/A1f × n=5）+ 待你放行后跑批

【用户确认点】Pilot 数字过目 → 放行确认批；报告签字。
红线：生成走辅助 LLM 通道（llm_client，temp=0），与被考模型隔离。

用法：
    python scripts/family_generator.py skills/my-skill --name myconv
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.llm_client import chat  # noqa: E402

PY = sys.executable
# v3.4 命名黑名单：模型可自然猜中的字面量（命中即打回）
NAME_BLACKLIST = re.compile(
    r"(sentinel|empty_?stream|default_?value|placeholder|null_?object|"
    r"validate_?input|check_?args|missing|notfound|empty_?result)", re.I)

EXTRACT_PROMPT = """读下面的 Skill 文档，提取其中**可机器校验**的具体规则。

要求：
- 只提取有确定性可观测形式的规则（命名约定/返回值约定/错误行为/调用顺序/禁止事项），
  不要"写整洁代码"这类抽象建议；
- 每条给出：id、rule（一句话）、observable（pytest 怎么断言它）、
  token（违反时测试里会出现的字面量，用于中性扫描）；
- 输出严格 JSON 数组，不要任何其他文字。最多 6 条。

Skill 文档：
{skill_md}
"""

DRAFT_PROMPT = """为评测一个 Skill 的价值，造一道"知识缺口"编程题（Python 单包）。

该 Skill 教授的规则：
{rules}

设计铁律（违反即废卷）：
- v3.0：规则的答案/产物字面量**不得出现在 fixture**（考生无从推断才算缺口）；
- v3.1：fixture 注释必须中性，禁止任何暗示规则存在的字样；
- v3.4：测试里的断言字面量不能用行业通行命名（sentinel/default/validate 这类禁用）；
- 行为测试（test_behavior.py）：测基本功能，裸考者能过一部分；
- 约定测试（test_convention.py）：测上述规则，裸考者**不可能**全过，
  读过 Skill 文档的人能过；
- gold：把 fixture 修到全部测试通过的版本；wrong：看起来对但违反一条规则的错解；
- meta.yaml：含 task_id/prompt/forbidden_edits/sites_required=1；prompt 只说用户反馈
  的现象，不泄露规则。

按以下格式输出全部文件（不要输出其他内容）：
<<<FILE 相对路径>>>
文件内容
<<<END>>>
文件清单：fixture/<pkg>/__init__.py、tests/f2p/test_behavior.py、
tests/f2p/test_convention.py、tests/p2p/test_stable.py、gold/<pkg>/__init__.py、
wrong/<pkg>/__init__.py、meta.yaml、INTENT.md
{feedback}
"""

FILE_RE = re.compile(r"<<<FILE\s+(.+?)>>>\n(.*?)\n?<<<END>>>", re.S)


def llm_json(prompt: str, max_tokens: int = 2048) -> list[dict]:
    out = chat([{"role": "user", "content": prompt}], temperature=0,
               max_tokens=max_tokens, timeout=180)
    m = re.search(r"\[.*\]", out, re.S)
    return json.loads(m.group(0)) if m else []


def llm_files(prompt: str, max_tokens: int = 8192) -> dict[str, str]:
    out = chat([{"role": "user", "content": prompt}], temperature=0,
               max_tokens=max_tokens, timeout=600)
    return {m.group(1).strip(): m.group(2) for m in FILE_RE.finditer(out)}


def hard_check(files: dict[str, str], rules: list[dict]) -> list[str]:
    """机器硬检：命名黑名单 + fixture 中性扫描。返回违规清单（空=过）。"""
    problems = []
    fixture = "".join(v for k, v in files.items() if k.startswith("fixture/"))
    conv_test = files.get("tests/f2p/test_convention.py", "")
    if NAME_BLACKLIST.search(conv_test):
        problems.append("约定测试命中命名黑名单（可自然猜中）")
    for r in rules:
        tok = (r.get("token") or "").strip()
        if tok and len(tok) >= 3 and tok in fixture:
            problems.append(f"规则 {r.get('id')} 的字面量 {tok!r} 泄漏进 fixture")
    for bad in ("约定", "规范", "哨兵", "必须返回", "convention", "sentinel"):
        if bad in fixture:
            problems.append(f"fixture 含提示性字样 {bad!r}（v3.1 泄题）")
    return problems


def pilot_gate(task_dir: Path, name: str, log: Path) -> tuple[bool, float]:
    """Pilot 门：A0 × 3（pi-docker），均分 ≤0.6 放行。"""
    preset = task_dir / "pilot.yaml"
    preset.write_text(f"""name: fg-pilot-{name}
arms:
  - {{ id: A0, inject: none }}
tasks:
  source: {task_dir.parent.as_posix()}
  only: [{task_dir.name}]
repeats: 3
model: deepseek-v4.1-flash
timeout_min: 12
concurrency: 3
""", encoding="utf-8")
    batch = f"fg-pilot-{name}-{int(time.time())}"
    with log.open("a", encoding="utf-8") as f:
        subprocess.run([PY, "-m", "backend.orchestrator.runner", str(preset),
                        "--driver", "pi-docker", "--batch", batch],
                       cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
    scores = []
    f = ROOT / "results" / batch / "runs.jsonl"
    if f.exists():
        latest: dict[str, dict] = {}
        for line in f.open(encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                latest[r.get("run_id", "?")] = r
        scores = [r["score"] for r in latest.values()
                  if isinstance(r.get("score"), (int, float))
                  and (r.get("input_tokens") or r.get("output_tokens"))]
    mean = sum(scores) / len(scores) if scores else 1.0  # 全死=无法证明缺口，压线不放行
    return mean <= 0.6 and len(scores) >= 2, round(mean, 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("skill", help="Skill 目录（含 SKILL.md）")
    ap.add_argument("--name", required=True, help="任务族名（如 myconv-api）")
    ap.add_argument("--rounds", type=int, default=3)
    args = ap.parse_args()
    skill = Path(args.skill).resolve()
    skill_md = (skill / "SKILL.md").read_text(encoding="utf-8") if (skill / "SKILL.md").exists() else ""
    if not skill_md:
        print(f"✗ 缺 SKILL.md：{skill}")
        return 2
    work = ROOT / "results" / f"family-gen-{args.name}-{int(time.time())}"
    work.mkdir(parents=True, exist_ok=True)
    log = work / "gen.log"
    task_dir = ROOT / "tasks" / "family-gen" / args.name

    print("== 1/5 知识提取 ==")
    rules = llm_json(EXTRACT_PROMPT.format(skill_md=skill_md[:6000]))
    if not rules:
        print("✗ 未能从 Skill 提取可校验规则（可能全是抽象建议——"
          "这本身就是'无知识缺口价值'的合法结论）")
        return 2
    (work / "rules.json").write_text(json.dumps(rules, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    print(f"  提取 {len(rules)} 条规则：" + "、".join(r.get("id", "?") for r in rules))

    feedback = ""
    for rd in range(1, args.rounds + 1):
        print(f"== 2/5 约定族起草（第 {rd} 轮）==")
        files = llm_files(DRAFT_PROMPT.format(
            rules=json.dumps(rules, ensure_ascii=False, indent=1),
            feedback=feedback))
        need = {"fixture", "tests/f2p/test_behavior.py", "tests/f2p/test_convention.py",
                "tests/p2p/test_stable.py", "gold", "wrong", "meta.yaml", "INTENT.md"}
        have = set()
        for k in files:
            for n in need:
                if k.startswith(n) or k == n:
                    have.add(n)
        missing = need - have
        if missing:
            feedback = f"\n上一轮缺文件：{sorted(missing)}，本轮必须全部产出。"
            print(f"  缺文件 {sorted(missing)}，打回重造")
            continue
        problems = hard_check(files, rules)
        if problems:
            feedback = "\n上一轮机器硬检未过：" + "；".join(problems) + "。本轮必须修复。"
            print("  硬检打回：" + "；".join(problems))
            continue

        print("== 3/5 落盘 + 四关校验 ==")
        for rel, content in files.items():
            rel_fixed = rel.replace("gold/", "solution_tmp/") if rel.startswith("gold/") else rel
            p = task_dir / rel_fixed
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8", newline="\n")
        # gold → solution patch（用校验器认的格式：先放 solution_tmp，gold 校验由 validator 处理）
        rc = subprocess.run([PY, "-m", "backend.validators.task_validator", str(task_dir)],
                            cwd=ROOT, capture_output=True, text=True).returncode
        if rc != 0:
            feedback = "\n上一轮四关校验未过（见 log），本轮修复后重出。"
            print("  四关未过，打回（详见 gen.log）")
            log.open("a", encoding="utf-8").write(f"第{rd}轮四关未过\n")
            continue

        print("== 4/5 Pilot 门（A0 × 3，沙箱）==")
        ok, mean = pilot_gate(task_dir, args.name, log)
        print(f"  Pilot A0 均分 {mean}（门槛 ≤0.6）")
        if ok:
            print("== 5/5 过门：产出确认批预设 ==")
            preset = ROOT / "matrix" / f"familygen-{args.name}.yaml"
            placebo = "D:/ai_project/skillbench-v3-secure/skills/placebo-cooking"
            preset.write_text(f"""name: familygen-{args.name}
description: "family-generator 产出：{args.name} 确认批（待用户放行）"
arms:
  - {{ id: A0, inject: none }}
  - {{ id: A0p, inject: forced, skill: {placebo} }}
  - {{ id: A1f, inject: forced, skill: {skill.as_posix()} }}
tasks:
  source: tasks/family-gen
  only: [{task_dir.name}]
repeats: 5
model: deepseek-v4.1-flash
timeout_min: 12
concurrency: 4
""", encoding="utf-8")
            print(f"  ✅ 任务族建成：{task_dir}")
            print(f"  确认批预设：{preset}")
            print("\n【用户确认点】Pilot 数字如上。放行跑批：")
            print(f"  python -m backend.orchestrator.runner {preset} --driver pi-docker --batch familygen-{args.name}-confirm")
            return 0
        feedback = (f"\n上一轮 Pilot A0 均分 {mean}（>0.6）——裸考能猜到约定。"
                    "分析 A0 猜中的路径，本轮约定改得更反直觉/更不可猜（v3.3/v3.4）。")
        print("  未过门，带反馈打回重造")

    print("\n===== 打回耗尽 =====")
    print("合法结局：该 Skill 的知识对当前模型不构成缺口（或需人工介入设计）。")
    print("这不是流程失败——与 tdd 的饱和区结论同型，可写进该 Skill 的体检报告。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
