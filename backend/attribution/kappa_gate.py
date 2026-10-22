"""κ 门（B3）：归因结论的采信控制，状态来自 docs/kappa_status.json。

规则（LLM-as-a-Judge 方法论 + 2026-10-03 校准结果）：
- 检测器版本过门（κ≥0.7）→ 阳性与阴性结论均直接采信；
- 未过门 → 阳性（F-ID 命中）一律标 "待复核"（不进定量结论），
  阴性按 negative_accuracy 判定（≥0.9 可采信）；
- 状态文件是人工校准的唯一事实源：κ 值由人标注产生，代码只读取不修改。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STATUS_FILE = ROOT / "docs" / "kappa_status.json"

DETECTOR_VERSION = "v2-activity-gate"  # B15+B1 后的检测器版本号


def load_status() -> dict:
    if not STATUS_FILE.exists():
        return {"current": {"version": "unknown", "pass": False,
                            "negative_accuracy": 0.0},
                "note": "kappa_status.json 缺失——全部结论按待复核处理"}
    return json.loads(STATUS_FILE.read_text(encoding="utf-8"))


def gate() -> dict:
    """返回当前 κ 门判定（供归因引擎给输出盖章）。"""
    st = load_status()
    cur = st.get("current", {})
    passed = bool(cur.get("pass"))
    neg_ok = (cur.get("negative_accuracy") or 0.0) >= 0.9
    return {
        "detector_version": DETECTOR_VERSION,
        "kappa": cur.get("kappa"),
        "pass": passed,
        "positive_status": "可信" if passed else "待复核",
        "negative_status": "可信" if (passed or neg_ok) else "待复核",
        "method": cur.get("method", ""),
    }


def stamp_hits(hits: list[dict], g: dict) -> list[dict]:
    """给每条命中盖采信章（不过门则阳性全部待复核）。"""
    for h in hits:
        h["credibility"] = g["positive_status"]
    return hits
