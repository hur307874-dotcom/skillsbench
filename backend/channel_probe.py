"""渠道健康前置探测（B6）：跑批之前先探 DIS，不再用 45 个 run 的尸体发现降级。

判级（基于 poolv3c 死亡螺旋与 deploykit 六连死的教训）：
- ok：探针全部正常（非空文本）——放行；
- degraded：部分探针空响应/异常——应等待重试或降并发；
- down：全部失败——熔断，不烧 run。

用法：
    python -m backend.channel_probe            # 打印判定，exit 0/1/2
    python -m backend.channel_probe --json
    from backend.channel_probe import probe    # ok/degraded/down + 细节
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.llm_client import chat  # noqa: E402

PROBE_MSG = [{"role": "user", "content": "回复 ok 两个字母即可。"}]


def probe(n: int = 2, timeout: int = 45, model: str | None = None) -> dict:
    """发 n 个廉价探针，返回渠道判定。

    两个实战修正（2026-10-04）：
    - 系统代理到不了中转站：必须把 r.dis.115.zone 加进 NO_PROXY（与 relay_env 同规）；
    - HTTP 429 = 渠道活着但限流，算成活（throttled），不算失败。
    """
    import os
    import urllib.error
    from backend.net_guard import install as _ng_install
    _ng_install()
    host = "api.siliconflow.cn"  # 2026-10-10 渠道迁移（DIS key 被封）
    for var in ("NO_PROXY", "no_proxy"):
        cur = os.environ.get(var, "")
        if host not in cur:
            os.environ[var] = f"{cur},{host}" if cur else host
    results = []
    for i in range(n):
        t0 = time.time()
        try:
            text = chat(PROBE_MSG, model=model, temperature=0,
                        max_tokens=8, timeout=timeout)
            ok = bool(text and text.strip())
            results.append({"i": i, "ok": ok, "wall_s": round(time.time() - t0, 1),
                            "resp": (text or "")[:40], "error": ""})
        except urllib.error.HTTPError as e:  # noqa: BLE001
            throttled = e.code == 429
            results.append({"i": i, "ok": throttled,
                            "wall_s": round(time.time() - t0, 1),
                            "resp": "", "error": f"HTTP {e.code}" + ("（限流，计成活）" if throttled else "")})
        except Exception as e:  # noqa: BLE001
            results.append({"i": i, "ok": False,
                            "wall_s": round(time.time() - t0, 1),
                            "resp": "", "error": str(e)[:120]})
        if i < n - 1:
            time.sleep(2)  # 探针间隔，避免自触发限流
    alive = sum(1 for r in results if r["ok"])
    if alive == n:
        level = "ok"
    elif alive == 0:
        level = "down"
    else:
        level = "degraded"
    return {"level": level, "alive": f"{alive}/{n}", "probes": results,
            "checked_at": time.strftime("%Y-%m-%d %H:%M:%S")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="as_json", action="store_true")
    ap.add_argument("--n", type=int, default=2)
    args = ap.parse_args()
    r = probe(n=args.n)
    if args.as_json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(f"渠道判定：{r['level']}（{r['alive']} 探针成活）")
        for p in r["probes"]:
            mark = "✓" if p["ok"] else "✗"
            detail = p["resp"] or p["error"] or "(空响应)"
            print(f"  {mark} #{p['i']} {p['wall_s']}s {detail}")
    return {"ok": 0, "degraded": 1, "down": 2}[r["level"]]


if __name__ == "__main__":
    sys.exit(main())
