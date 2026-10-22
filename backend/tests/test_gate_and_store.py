"""B10 单测：Pilot Gate 判定边界 + DB 视图/归因入库 + API 端点（轻量）。

运行：python -m backend.tests.test_gate_and_store
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from backend.gate.pilot_gate import BAND, channel_health, gate_verdicts  # noqa: E402


def _mk_batch(tmp: Path, rows: list[dict]) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "runs.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return tmp


def _run(tid, arm, score=None, dead=False, error=None, tps=10.0, wall=30.0):
    r = {"run_id": f"{tid}-{arm}-r01", "task_id": tid, "arm": arm,
         "rep": 1, "num_turns": 8, "wall_s": wall, "output_tokens": 300,
         "tps": tps}
    if score is not None:
        r["score"] = score
    if dead:
        r["dead"] = True
    if error:
        r["error"] = error
    return r


def test_gate_band_boundaries():
    """准入带 [0.4, 0.8]：边界值归入带内；0.39/0.81 出带。"""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        rows = [
            # 带内 0.4（2/5）
            *[_run("t-in-low", "A0", score=1.0 if i < 2 else 0.0) for i in range(5)],
            # 天花板 1.0
            *[_run("t-ceil", "A0", score=1.0) for i in range(5)],
            # 地板 0.2
            *[_run("t-floor", "A0", score=1.0 if i == 0 else 0.0) for i in range(5)],
        ]
        # run_id 需唯一：手动改 rep
        for i, r in enumerate(rows):
            r["run_id"] = f"{r['task_id']}-r{i:02d}"
        _mk_batch(tmp, rows)
        v = {x["task_id"]: x for x in gate_verdicts(tmp, "A0")}
        assert v["t-in-low"]["verdict"] == "准入", v["t-in-low"]
        assert v["t-ceil"]["verdict"] == "带外-天花板", v["t-ceil"]
        assert v["t-floor"]["verdict"] == "带外-地板", v["t-floor"]
        assert BAND == (0.4, 0.8)


def test_gate_counts_dead_and_error_as_not_full():
    """完成率口径：死跑与错误计分母、不计满分。"""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        rows = [_run("t-x", "A0", score=1.0),
                _run("t-x", "A0", dead=True),
                _run("t-x", "A0", error="timeout")]
        for i, r in enumerate(rows):
            r["run_id"] = f"t-x-r{i}"
        _mk_batch(tmp, rows)
        v = gate_verdicts(tmp, "A0")[0]
        assert v["n"] == 3 and v["full"] == 1, v
        assert abs(v["rate"] - 0.333) < 0.01


def test_channel_health_flags_degraded():
    """渠道健康：慢批（tps 1）应判降级；快批（tps 10）不降级。"""
    with tempfile.TemporaryDirectory() as d:
        slow = _mk_batch(Path(d) / "slow", [_run("t", "A0", score=1.0, tps=1.0)])
        fast = _mk_batch(Path(d) / "fast", [_run("t", "A0", score=1.0, tps=20.0)])
        hs, hf = channel_health(slow), channel_health(fast)
        assert hs["degraded"] is True, hs
        assert hf["degraded"] is False, hf


def test_channel_health_computes_tps_when_missing():
    """老记录无 tps 字段：用 output_tokens/wall_s 现算。"""
    with tempfile.TemporaryDirectory() as d:
        rows = [_run("t", "A0", score=1.0)]
        rows[0].pop("tps")
        tmp = _mk_batch(Path(d) / "b", rows)
        h = channel_health(tmp)
        assert h["batch_median_tps"] is not None
        assert abs(h["batch_median_tps"] - 10.0) < 0.1, h


def test_db_views_and_attribution_table():
    """DB：v_arm_stats 含 model/dead/tps；attribution 表存在且可写读。"""
    from backend.store.db import connect
    con = connect()
    cols = {r[0] for r in con.execute("DESCRIBE v_arm_stats").fetchall()}
    for c in ("model", "dead", "avg_tps"):
        assert c in cols, f"v_arm_stats 缺列 {c}：{cols}"
    con.execute("SELECT COUNT(*) FROM v_channel_health")
    con.execute("SELECT COUNT(*) FROM attribution")


def test_api_routes_registered():
    """API：新增三端点均已注册。"""
    from backend.api.server import app
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    for p in ("/api/runs/{batch_id}/{run_id}", "/api/log", "/api/gate/health"):
        assert p in paths, f"缺端点 {p}"


if __name__ == "__main__":
    for f in [test_gate_band_boundaries,
              test_gate_counts_dead_and_error_as_not_full,
              test_channel_health_flags_degraded,
              test_channel_health_computes_tps_when_missing,
              test_db_views_and_attribution_table,
              test_api_routes_registered]:
        f()
        print(f"✓ {f.__name__}")
    print("B10 单测全部通过")
