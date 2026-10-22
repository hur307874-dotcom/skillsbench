"""辅助 LLM 统一客户端（项目约定 2026-10-02，用户立规）。

【用途边界】本模块**只**服务于"非评测对象"的 LLM 调用：
  - process_judge（过程质量辅助判分）
  - 归因器 LLM 辅助件（L4 反事实/摘要，如启用）
  - 任务/内容生成辅助（pool-v3 扩族自动化的 LLM 环节）
  - κ 校准的机器标注员

【红线】评测对象模型（被考的 agent）**不走这里**——
  评测 run 的模型由 matrix 预设的 model 参数决定（runner/drivers），
  与辅助调用物理隔离，防止"裁判和选手同一通道"的污染。

端点：DIS relay（OpenAI 兼容）。
"""
from __future__ import annotations

import json
import os
import urllib.request

# 代理免疫（2026-10-10 net_guard）：全栈直连，不受 VPN 死活影响
from backend.net_guard import install as _ng_install
_ng_install()

AUX_LLM_BASE_URL = os.environ.get("AUX_LLM_BASE_URL", "https://api.siliconflow.cn/")
def _aux_key() -> str:
    key = os.environ.get("DIS_API_KEY", "")
    if not key:
        try:
            from backend.local_secrets import DIS_API_KEY  # 本地文件（gitignore）
            key = DIS_API_KEY
        except Exception:
            key = ""
    return key


AUX_LLM_API_KEY = _aux_key()
AUX_LLM_MODEL = os.environ.get("AUX_LLM_MODEL", "deepseek-ai/DeepSeek-V4-Flash")


def chat(messages: list[dict], model: str | None = None,
         temperature: float = 0.0, max_tokens: int = 1024,
         timeout: int = 120) -> str:
    """OpenAI 兼容 chat 调用（辅助用途专用；temperature 默认 0 保可复现）。"""
    url = AUX_LLM_BASE_URL.rstrip("/") + "/v1/chat/completions"
    body = json.dumps({
        "model": model or AUX_LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        **({"enable_thinking": False} if "siliconflow" in AUX_LLM_BASE_URL else {}),
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {AUX_LLM_API_KEY}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]
