"""net_guard：全栈代理免疫（2026-10-10 用户立规——系统不受 VPN 干扰）。

背景：本机 v2ray（127.0.0.1:10808）半死不活时，shell 环境变量
HTTP_PROXY/HTTPS_PROXY 会把 Python urllib 全部引向死代理（SSL EOF/10061），
浏览器 fetch 也被劫持挂死。我们的目标端点（硅基流动/GitHub/本地服务）
国内全部直连可达——所以本栈**一律不走代理**。

用法：在入口模块顶部 `from backend.net_guard import install; install()`。
效果：
1. NO_PROXY 覆盖白名单（双写大小写变量）；
2. 进程内 urllib 默认 opener 换成空 ProxyHandler（= 全部直连）；
3. subprocess_env() 返回剥掉代理变量的环境副本（给 runner/容器用）。

注意：若未来有需要代理才能到的端点（如 huggingface 境外域），
请在该调用点显式 build_opener(ProxyHandler({...})) 自行绕回本层。
"""
from __future__ import annotations

import os
import urllib.request

DIRECT_HOSTS = [
    "localhost", "127.0.0.1", "::1",
    "api.siliconflow.cn", "r.dis.115.zone",
    "github.com", "raw.githubusercontent.com", "codeload.github.com",
    "objects.githubusercontent.com", "api.github.com",
]

_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
               "http_proxy", "https_proxy", "all_proxy")


def install() -> None:
    np = ",".join(DIRECT_HOSTS)
    os.environ["NO_PROXY"] = np
    os.environ["no_proxy"] = np
    urllib.request.install_opener(
        urllib.request.build_opener(urllib.request.ProxyHandler({})))


def subprocess_env(base: dict | None = None) -> dict:
    """剥掉代理变量的子进程环境（runner/容器/驱动用）。"""
    env = dict(base if base is not None else os.environ)
    for v in _PROXY_VARS:
        env.pop(v, None)
    env["NO_PROXY"] = ",".join(DIRECT_HOSTS)
    env["no_proxy"] = env["NO_PROXY"]
    return env
