"""codex CLI 驱动（r.dis.115.zone 线，deepseek 后端）。

臂 → codex exec 实现（0.147.0，参数经 `codex exec --help` 核实，2026-09-27）：
  none    A0：--ignore-user-config --ignore-rules + CODEX_HOME 指向空目录
             （抑制用户级 skills/规则，临时 repo 内无 AGENTS.md 即无指令）
  forced  A1f：SKILL.md 内容写入 repo/AGENTS.md（codex 原生指令文件，强制生效）
  auto    A1：Skill 复制到 repo/.codex/skills/<name>/（尽力而为，B1.5 需人工验证）
  placebo A0p：写入安慰剂 AGENTS.md

成本口径：deepseek 后端计费远低于 claude，cost_usd 记 0 并以 token 数为主指标
（relay 不回传价格；与 haiku 线不可直接比，报告须标注"deepseek 线"）。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from backend.cli_driver.claude_driver import CliResult

NODE = r"C:\Users\17664\.workbuddy\binaries\node\versions\22.22.2\node.exe"
CODEX_JS = r"C:\Users\17664\.workbuddy\binaries\node\versions\22.22.2\node_modules\@openai\codex\bin\codex.js"
PROVIDER_CONFIG = ('model_providers.dis={name="dis",'
                   'base_url="https://api.siliconflow.cn/v1",'
                   'env_key="DIS_API_KEY",wire_api="responses"}')
DEFAULT_MODEL = "deepseek-v4.1-flash"


def build_command(prompt: str, inject: str, skill_dir: Path | None,
                  model: str | None, repo: Path) -> tuple[list[str], dict]:
    """返回 (cmd, env_extra)。"""
    flat = " ".join(prompt.split())  # 防 .CMD/垫片截断（同 claude 线教训）
    cmd = [NODE, CODEX_JS, "exec", "--json", "--skip-git-repo-check",
           "--sandbox", "workspace-write",
           "-c", PROVIDER_CONFIG, "-c", "model_provider=dis",
           "-c", f"model={model or DEFAULT_MODEL}", flat]
    env_extra: dict[str, str] = {}
    if inject == "none":
        cmd += ["--ignore-user-config", "--ignore-rules"]
        empty_home = repo.parent / ".codex-home-empty"
        empty_home.mkdir(parents=True, exist_ok=True)
        env_extra["CODEX_HOME"] = str(empty_home)
    elif inject == "auto":
        pass  # Skill 已由 prepare_repo 挂到 repo/.codex/skills/
    elif inject in ("forced", "forced_no_refs", "placebo"):
        pass  # AGENTS.md 已由 prepare_repo 写入
    else:
        raise ValueError(f"未知 inject 类型：{inject}")
    return cmd, env_extra


def prepare_repo(fixture: Path, dest: Path, inject: str, skill_dir: Path | None) -> Path:
    """复制 fixture；forced 臂写 AGENTS.md，auto 臂挂 .codex/skills/。"""
    if dest.exists():
        dest = dest.with_name(f"{dest.name}-retry{int(time.time())}")
    shutil.copytree(fixture, dest)
    if inject in ("forced", "forced_no_refs", "placebo"):
        if not skill_dir or not (skill_dir / "SKILL.md").exists():
            raise ValueError(f"臂 {inject} 需要 Skill 目录且含 SKILL.md：{skill_dir}")
        (dest / "AGENTS.md").write_text(
            (skill_dir / "SKILL.md").read_text(encoding="utf-8"), encoding="utf-8")
    elif inject == "auto":
        if not skill_dir:
            raise ValueError("auto 臂需要 Skill 目录")
        target = dest / ".codex" / "skills" / skill_dir.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill_dir, target)
    return dest


def run_codex(prompt: str, repo: Path, inject: str, skill_dir: Path | None,
              model: str | None, timeout_s: int, trace_path: Path,
              env: dict) -> CliResult:
    cmd, env_extra = build_command(prompt, inject, skill_dir, model, repo)
    env.update(env_extra)
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
    for line in raw_text.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type", "")
        if t == "turn.completed":
            n_turns += 1
            usage = ev.get("usage", usage) or usage
        elif t == "item.completed":
            item = ev.get("item", {}) or {}
            if item.get("type") in ("agent_message", "assistant_message"):
                final_text = item.get("text", final_text)
    if n_turns == 0 and not usage:
        return CliResult(ok=False, trace_path=trace_path, wall_s=wall,
                         error=f"无 turn 事件（exit={proc.returncode}）: {proc.stderr[:300]}")
    return CliResult(
        ok=True, trace_path=trace_path, wall_s=wall,
        num_turns=n_turns, cost_usd=0.0,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_creation_tokens=usage.get("cached_input_tokens", 0),
        duration_api_ms=0,
        raw={"final_text": final_text[:2000], "usage": usage})
