"""Pi Agent 驱动（r.dis.115.zone 线，deepseek 后端）。

臂 → pi 实现（@mariozechner/pi-coding-agent，参数经 `pi --help` 核实，2026-09-27）：
  none    A0：--no-skills（禁用 skills 发现与加载）
  auto    A1：--skill <skill_dir>（原生 skill 加载，模型自主决定读不读）
  forced  A1f：--append-system-prompt <SKILL.md 路径>（支持文件内容内联）
  placebo A0p：注入安慰剂 Skill 同 forced

provider 由 scripts/pi-dis-provider.ts 扩展注册（api: openai-completions）。
输出 --mode json：JSONL 事件流（session/agent_start/turn_start/message_*），
usage 在 assistant message_end 上。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from backend.cli_driver.claude_driver import CliResult

NODE = r"C:\Users\17664\.workbuddy\binaries\node\versions\22.22.2\node.exe"
PI_JS = r"C:\Users\17664\.workbuddy\binaries\node\versions\22.22.2\node_modules\@mariozechner\pi-coding-agent\dist\cli.js"
PROVIDER_EXT = r"D:\ai_project\skill-bench\scripts\pi-dis-provider.ts"
DEFAULT_MODEL = "deepseek-v4.1-flash"


def build_command(prompt: str, inject: str, skill_dir: Path | None,
                  model: str | None) -> list[str]:
    flat = " ".join(prompt.split())
    cmd = [NODE, PI_JS, "-e", PROVIDER_EXT, "--provider", "dis",
           "--model", model or DEFAULT_MODEL, "--no-session",
           "--mode", "json", "-p", flat]
    if inject == "none":
        cmd += ["--no-skills"]
    elif inject == "auto":
        if not skill_dir:
            raise ValueError("auto 臂需要 Skill 目录")
        cmd += ["--skill", str(skill_dir.resolve())]
    elif inject in ("forced", "forced_no_refs", "placebo"):
        if not skill_dir or not (skill_dir / "SKILL.md").exists():
            raise ValueError(f"臂 {inject} 需要 Skill 目录且含 SKILL.md：{skill_dir}")
        cmd += ["--append-system-prompt", str((skill_dir / "SKILL.md").resolve())]
    else:
        raise ValueError(f"未知 inject 类型：{inject}")
    return cmd


def prepare_repo(fixture: Path, dest: Path, inject: str, skill_dir: Path | None) -> Path:
    """pi 的 skill 注入全部走命令行，repo 只需复制 fixture。"""
    if dest.exists():
        dest = dest.with_name(f"{dest.name}-retry{int(time.time())}")
    shutil.copytree(fixture, dest)
    return dest


def run_pi(prompt: str, repo: Path, inject: str, skill_dir: Path | None,
           model: str | None, timeout_s: int, trace_path: Path,
           env: dict) -> CliResult:
    cmd = build_command(prompt, inject, skill_dir, model)
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True,
                              timeout=timeout_s, env=env,
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        trace_path.write_text(json.dumps({"error": f"timeout {timeout_s}s"}),
                              encoding="utf-8")
        return CliResult(ok=False, trace_path=trace_path, wall_s=time.time() - t0,
                         error=f"timeout {timeout_s}s")
    wall = time.time() - t0
    raw_text = proc.stdout.strip()
    trace_path.write_text(raw_text or json.dumps({"stderr": proc.stderr[:2000]}),
                          encoding="utf-8")

    usage: dict = {}
    n_turns = 0
    final_text = ""
    seen_session = False
    for line in raw_text.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type", "")
        if t == "session":
            seen_session = True
        elif t == "turn_start":
            n_turns += 1
        elif t == "message_end":
            msg = ev.get("message", {}) or {}
            if msg.get("role") == "assistant":
                usage = msg.get("usage", usage) or usage
                for block in msg.get("content", []) or []:
                    if block.get("type") == "text":
                        final_text = block.get("text", final_text)
    if not seen_session:
        return CliResult(ok=False, trace_path=trace_path, wall_s=wall,
                         error=f"无 session 事件（exit={proc.returncode}）: "
                               f"{(proc.stderr or raw_text)[:300]}")
    cost = (usage.get("cost", {}) or {}).get("total", 0.0)
    return CliResult(
        ok=True, trace_path=trace_path, wall_s=wall,
        num_turns=max(n_turns, 1), cost_usd=cost,
        input_tokens=usage.get("input", 0),
        output_tokens=usage.get("output", 0),
        cache_creation_tokens=usage.get("cacheWrite", 0),
        duration_api_ms=0,
        raw={"final_text": final_text[:2000], "usage": usage})
