"""claude CLI 驱动：臂注入 + 原始输出留存（raw_event_ref 第一层防线）。

臂 → claude CLI 实现（参数拼写经 `claude --help` 核实，2026-09-24）：
  none           A0 裸考：--disable-slash-commands（禁用全部 Skill）
  forced         A1f 强制注入：--append-system-prompt-file <SKILL.md>
  auto           A1 自主触发：Skill 复制到 <repo>/.claude/skills/<name>/（由调用方准备）
  forced_no_refs A1-noref：同 forced（引用文件不落盘，MVP 阶段与 forced 等价，TODO）
  placebo        A0p：注入安慰剂 Skill 的 SKILL.md

⚠️ B1.5 冒烟必须人工验证 A0 确实未加载 Skill（PLAN §11），不能信任 flag 语义。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from backend.cli_driver.relay_env import load_relay_env


@dataclass
class CliResult:
    ok: bool
    trace_path: Path
    num_turns: int = 0
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    duration_api_ms: int = 0
    wall_s: float = 0.0
    error: str = ""
    raw: dict = field(default_factory=dict)


def build_command(prompt: str, inject: str, skill_dir: Path | None,
                  model: str | None) -> list[str]:
    exe = shutil.which("claude") or "claude"  # Windows 下必须解析全名（claude.cmd），否则 WinError 2
    # meta.yaml 的 prompt 是块标量含换行；经 .CMD 批处理垫片传参时换行会截断命令行，
    # 导致 prompt 之后的全部 flag 丢失（实测：--output-format 与 skip-permissions 同时失效）
    flat_prompt = " ".join(prompt.split())
    # stream-json + verbose：原生输出完整事件流（init/assistant/tool_use/result），
    # 归一化层解析末行 result 取汇总，全部行原样留存（raw_event_ref）
    cmd = [exe, "-p", flat_prompt, "--output-format", "stream-json", "--verbose",
           "--dangerously-skip-permissions"]
    if inject == "none":
        cmd += ["--disable-slash-commands"]
    elif inject in ("forced", "forced_no_refs", "placebo"):
        if not skill_dir or not (skill_dir / "SKILL.md").exists():
            raise ValueError(f"臂 {inject} 需要 Skill 目录且含 SKILL.md：{skill_dir}")
        cmd += ["--append-system-prompt-file", str((skill_dir / "SKILL.md").resolve())]
    elif inject == "auto":
        pass  # Skill 已由 prepare_repo 挂载到 .claude/skills/
    else:
        raise ValueError(f"未知 inject 类型：{inject}")
    if model:
        cmd += ["--model", model]
    return cmd


def prepare_repo(fixture: Path, dest: Path, inject: str, skill_dir: Path | None) -> Path:
    """复制 fixture 到工作目录；auto 臂把 Skill 挂进 .claude/skills/。
    沙箱禁止 rmtree（safe-delete），重试时不删除旧目录，
    改用带时间戳的新目录，返回实际使用的目录。"""
    if dest.exists():
        dest = dest.with_name(f"{dest.name}-retry{int(time.time())}")
    shutil.copytree(fixture, dest)
    if inject == "auto":
        if not skill_dir:
            raise ValueError("auto 臂需要 Skill 目录")
        target = dest / ".claude" / "skills" / skill_dir.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill_dir, target)
    return dest


def run_claude(prompt: str, repo: Path, inject: str, skill_dir: Path | None,
               model: str | None, timeout_s: int, trace_path: Path) -> CliResult:
    cmd = build_command(prompt, inject, skill_dir, model)
    env = load_relay_env(Path.cwd() / ".env")
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True,
                              timeout=timeout_s, encoding="utf-8", errors="replace",
                              env=env)
    except subprocess.TimeoutExpired:
        trace_path.write_text(json.dumps({"error": f"timeout {timeout_s}s"}),
                              encoding="utf-8")
        return CliResult(ok=False, trace_path=trace_path, wall_s=time.time() - t0,
                         error=f"timeout {timeout_s}s")
    wall = time.time() - t0

    raw_text = proc.stdout.strip()
    trace_path.write_text(raw_text or json.dumps({"stderr": proc.stderr[:2000]}),
                          encoding="utf-8")
    # stream-json：逐行 JSON，末行是 type=result 的汇总对象
    raw = None
    for line in reversed(raw_text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "result":
            raw = obj
            break
        if "is_error" in obj and raw is None:  # 兼容 summary 单对象格式
            raw = obj
            break
    if raw is None:
        return CliResult(ok=False, trace_path=trace_path, wall_s=wall,
                         error=f"未找到 result 事件（exit={proc.returncode}）: {proc.stderr[:300]}")
    u = raw.get("usage", {}) or {}
    return CliResult(
        ok=not raw.get("is_error", False), trace_path=trace_path, wall_s=wall,
        num_turns=raw.get("num_turns", 0),
        cost_usd=raw.get("total_cost_usd", 0.0),
        input_tokens=u.get("input_tokens", 0),
        output_tokens=u.get("output_tokens", 0),
        cache_creation_tokens=u.get("cache_creation_input_tokens", 0),
        duration_api_ms=raw.get("duration_api_ms", 0),
        error="" if not raw.get("is_error") else str(raw.get("result", ""))[:300],
        raw=raw)
