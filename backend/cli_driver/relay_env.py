"""从项目根目录 .env 加载中转站配置，生成注入 CLI 子进程的环境变量。

要点（B0 探活登记，docs/EXPERIMENT_LOG.md）：
1. claude CLI 通过 ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN 走中转站
   （该站支持 Anthropic 原生 /v1/messages，已实测）；
2. 本机系统代理（127.0.0.1:10808）到不了中转站，必须把中转站域名加进 NO_PROXY，
   否则子进程报连接错误（HTTP 000）；
3. key 只从 .env 读（.env 已 gitignore），不硬编码、不落 trace。
"""
from __future__ import annotations

import os
from pathlib import Path


def load_relay_env(env_file: str | Path = ".env") -> dict[str, str]:
    env = dict(os.environ)
    p = Path(env_file)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()

    base = env.get("ENGINX_BASE_URL", "").rstrip("/")
    key = env.get("ENGINX_API_KEY", "")
    if base and key:
        # 本项目实验强制走中转站（覆盖用户可能存在的官方 ANTHROPIC_* 配置）
        env["ANTHROPIC_BASE_URL"] = base
        env["ANTHROPIC_AUTH_TOKEN"] = key
        env["ANTHROPIC_API_KEY"] = key
    host = base.split("://", 1)[-1].split("/")[0] if base else ""
    if host:
        existing = env.get("NO_PROXY", "")
        env["NO_PROXY"] = f"{existing},{host}" if existing else host
    return env
