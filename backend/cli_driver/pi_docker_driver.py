"""Pi Agent 的 docker 沙箱驱动：agent 在容器内跑，只挂 /repo。

与 pi_driver 的差异：
- 宿主机命令换成 `wsl -d Ubuntu -u root -- docker run --rm ...`，
  容器内只有 /repo（fixture 副本）和（注入臂时）/skill 只读挂载——
  工作区 skills/、tasks/ 答案材料、其他 run 的 work 目录物理不可达；
- Windows 路径 → WSL 路径翻译（D:\\x → /mnt/d/x）；
- 超时用容器名强杀（docker rm -f），不留僵尸容器；
- DIS_API_KEY 兜底走 backend.llm_client 的内置默认（与辅助 LLM 同一通道约定）。

镜像：skillbench-sandbox:0.74.0（docker/Dockerfile，node22+pytest+pi 同版本）。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from backend.cli_driver.claude_driver import CliResult

IMAGE = "skillbench-sandbox:0.74.1"

MODEL_ALIAS = {"deepseek-v4.1-flash": "deepseek-ai/DeepSeek-V4-Flash"}
PI_CLI = "/usr/local/lib/node_modules/@mariozechner/pi-coding-agent/dist/cli.js"
PROVIDER = "/opt/pi-dis-provider.ts"
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4-Flash"
WSL_PREFIX = ["wsl", "-d", "Ubuntu", "-u", "root", "--"]


def _mnt(p: Path) -> str:
    """Windows 路径 → WSL /mnt 路径。"""
    s = str(p.resolve()).replace("\\", "/")
    if len(s) >= 2 and s[1] == ":":
        s = f"/mnt/{s[0].lower()}{s[2:]}"
    return s


# 调度通道默认 key（agent 跑批/选手线）——与辅助通道（裁判线）物理分账
def _agent_key() -> str:
    import os as _os
    key = _os.environ.get("AGENT_API_KEY", "")
    if not key:
        try:
            from backend.local_secrets import AGENT_API_KEY  # 本地文件（gitignore）
            key = AGENT_API_KEY
        except Exception:
            key = ""
    return key


AGENT_CHANNEL_API_KEY = _agent_key()


def _dis_key(env: dict) -> str:
    return (env or {}).get("DIS_API_KEY", "") or AGENT_CHANNEL_API_KEY


def prepare_repo(fixture: Path, dest: Path, inject: str, skill_dir: Path | None) -> Path:
    if dest.exists():
        dest = dest.with_name(f"{dest.name}-retry{int(time.time())}")
    shutil.copytree(fixture, dest)
    return dest


def build_command(prompt: str, repo: Path, inject: str, skill_dir: Path | None,
                  model: str | None, key: str, name: str) -> list[str]:
    flat = " ".join(prompt.split())
    cmd = WSL_PREFIX + [
        "docker", "run", "--rm", "--name", name,
        "-v", f"{_mnt(repo)}:/repo", "-w", "/repo",
        "-e", f"DIS_API_KEY={key}",
        "-e", "NO_PROXY=r.dis.115.zone,api.siliconflow.cn,localhost,127.0.0.1",
    ]
    if inject != "none" and skill_dir:
        cmd += ["-v", f"{_mnt(skill_dir)}:/skill:ro"]
    cmd += [IMAGE, "node", PI_CLI, "-e", PROVIDER,
            "--provider", "dis", "--model", MODEL_ALIAS.get(model, model) if model else DEFAULT_MODEL,
            "--no-session", "--mode", "json", "-p", flat]
    if inject == "none":
        cmd += ["--no-skills"]
    elif inject == "auto":
        cmd += ["--skill", "/skill"]
    elif inject in ("forced", "forced_no_refs", "placebo"):
        cmd += ["--append-system-prompt", "/skill/SKILL.md"]
    else:
        raise ValueError(f"未知 inject 类型：{inject}")
    return cmd


def run_pi_docker(prompt: str, repo: Path, inject: str, skill_dir: Path | None,
                  model: str | None, timeout_s: int, trace_path: Path,
                  env: dict) -> CliResult:
    key = _dis_key(env)
    if not key:
        return CliResult(ok=False, trace_path=trace_path, wall_s=0.0,
                         error="DIS_API_KEY 缺失（env 与 llm_client 兜底均为空）")
    name = f"sb-{repo.parent.name}-{int(time.time())}"
    cmd = build_command(prompt, repo, inject, skill_dir, model, key, name)
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout_s,
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        subprocess.run(WSL_PREFIX + ["docker", "rm", "-f", name],
                       capture_output=True, timeout=60)
        trace_path.write_text(json.dumps({"error": f"timeout {timeout_s}s"}),
                              encoding="utf-8")
        return CliResult(ok=False, trace_path=trace_path, wall_s=time.time() - t0,
                         error=f"timeout {timeout_s}s")
    wall = time.time() - t0
    raw_text = (proc.stdout or "").strip()
    trace_path.write_text(raw_text or json.dumps({"stderr": (proc.stderr or "")[:2000]}),
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
