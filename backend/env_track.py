"""env 轨协议（B7）：每个 run 记录环境元数据，结论可回溯到环境。

原则：采集轻量（lru_cache 每进程一次）、不阻塞主链、失败静默降级为缺省值。
字段：driver / model / cli 版本 / 沙箱镜像（digest）/ 渠道 / 采集时间。
"""
from __future__ import annotations

import json
import subprocess
import time
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def pi_version() -> str:
    pkg = (ROOT.parent / ".workbuddy" / "binaries" / "node" / "versions" / "22.22.2"
           / "node_modules" / "@mariozechner" / "pi-coding-agent" / "package.json")
    pkg = Path(r"C:\Users\17664\.workbuddy\binaries\node\versions\22.22.2"
               r"\node_modules\@mariozechner\pi-coding-agent\package.json")
    try:
        return json.loads(pkg.read_text(encoding="utf-8"))["version"]
    except Exception:  # noqa: BLE001
        return "unknown"


@lru_cache(maxsize=1)
def sandbox_image_digest() -> str:
    try:
        p = subprocess.run(
            ["wsl", "-d", "Ubuntu", "-u", "root", "--",
             "docker", "images", "--digests", "--format",
             "{{.Repository}}:{{.Tag}}@{{.Digest}}", "skillbench-sandbox:0.74.1"],
            capture_output=True, timeout=30)
        text = p.stdout.decode("utf-8", "replace").strip()
        return text.splitlines()[0] if text else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def collect(driver: str, model: str | None) -> dict:
    """一次 run 的环境快照（ driver 相关字段按驱动裁剪）。"""
    env = {"driver": driver, "model": model or "default",
           "channel": "api.siliconflow.cn" if driver in ("pi", "pi-docker", "codex") else "enginx/claude",
           "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    if driver in ("pi", "pi-docker"):
        env["pi_version"] = pi_version()
    if driver == "pi-docker":
        env["sandbox_image"] = sandbox_image_digest()
    return env
