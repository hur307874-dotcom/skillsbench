"""DuckDB trace 仓库：批次灌入 + 视图 + SQL 下钻入口（人/Agent 双通道）。

用法：
    python -m backend.store.db ingest results/real-q1          # 灌入批次
    python -m backend.store.db query "SELECT * FROM v_arm_stats"  # SQL 下钻
    python -m backend.store.db signals results/real-q1         # 跑行为信号并入表

幂等：同 batch_id 重复 ingest 先删后插（重灌安全）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.normalize.claude_normalize import normalize_and_check, NormalizeError  # noqa: E402
from backend.graders.behavior_signals import detect_all  # noqa: E402

DB_PATH = Path("results/traces.duckdb")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    batch_id VARCHAR, run_id VARCHAR, section VARCHAR, task_id VARCHAR,
    difficulty VARCHAR, arm VARCHAR, inject VARCHAR, rep INTEGER,
    score DOUBLE, tests VARCHAR, sites_fixed INTEGER, sites_required INTEGER,
    cost_usd DOUBLE, num_turns INTEGER, input_tokens BIGINT, output_tokens BIGINT,
    cache_creation_tokens BIGINT, wasted_turns INTEGER, wasted_tokens INTEGER,
    wall_s DOUBLE, driver VARCHAR, trace_ref VARCHAR, error VARCHAR,
    model VARCHAR, dead BOOLEAN, tps DOUBLE,
    PRIMARY KEY (batch_id, run_id)
);
CREATE TABLE IF NOT EXISTS events (
    batch_id VARCHAR, run_id VARCHAR, idx INTEGER, type VARCHAR,
    payload VARCHAR, raw_event_ref VARCHAR
);
CREATE TABLE IF NOT EXISTS attribution (
    batch_id VARCHAR, run_id VARCHAR, f_id VARCHAR, confidence VARCHAR,
    evidence_idx VARCHAR, note VARCHAR,
    PRIMARY KEY (batch_id, run_id, f_id, evidence_idx)
);
CREATE TABLE IF NOT EXISTS signals (
    batch_id VARCHAR, run_id VARCHAR, name VARCHAR, f_id VARCHAR,
    present BOOLEAN, wasted_turns INTEGER, wasted_tokens INTEGER, detail VARCHAR,
    PRIMARY KEY (batch_id, run_id, name)
);
"""

VIEWS = """
CREATE OR REPLACE VIEW v_arm_stats AS
SELECT batch_id, model, arm, difficulty,
       COUNT(*) AS n,
       SUM(CASE WHEN dead THEN 1 ELSE 0 END) AS dead,
       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) AS errors,
       AVG(score) AS avg_score,
       SUM(CASE WHEN score = 1.0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS pass_rate,
       AVG(cost_usd) AS avg_cost, SUM(cost_usd) AS total_cost,
       AVG(num_turns) AS avg_turns, AVG(tps) AS avg_tps
FROM runs WHERE error IS NULL
GROUP BY batch_id, model, arm, difficulty ORDER BY batch_id, model, arm, difficulty;

CREATE OR REPLACE VIEW v_channel_health AS
SELECT batch_id,
       MEDIAN(tps) AS median_tps,
       COUNT(*) FILTER (WHERE tps IS NOT NULL) AS n_tps
FROM runs WHERE error IS NULL
GROUP BY batch_id ORDER BY batch_id;

CREATE OR REPLACE VIEW v_paired AS
SELECT a.batch_id, a.task_id, a.difficulty,
       a.score AS a0_score, b.score AS a1f_score, b.score - a.score AS diff,
       a.cost_usd AS a0_cost, b.cost_usd AS a1f_cost,
       b.cost_usd - a.cost_usd AS cost_diff
FROM runs a JOIN runs b
  ON a.batch_id = b.batch_id AND a.task_id = b.task_id AND a.rep = b.rep
WHERE a.arm = 'A0' AND b.arm = 'A1f' AND a.error IS NULL AND b.error IS NULL;

CREATE OR REPLACE VIEW v_fid_hits AS
SELECT batch_id, f_id, name, COUNT(*) AS hits
FROM signals WHERE present GROUP BY batch_id, f_id, name ORDER BY batch_id, f_id;
"""


def connect() -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute(SCHEMA)
    for stmt in VIEWS.split(";"):
        if stmt.strip():
            con.execute(stmt)
    return con



_MODEL_MAP = {  # 批次 → 模型（--model 覆盖批；其余从 matrix yaml 补）
    "gradient-glm": "glm-5.1/5.2/5.3", "ablation-glm52": "glm-5.2",
    "forged-glm52": "glm-5.2", "pool-v20-glm52": "glm-5.2",
    "real-q1": "claude-opus", "b1-pilot": "claude-haiku",
}


def _batch_model(batch_id: str) -> str:
    import glob as _g
    import yaml as _y
    if batch_id in _MODEL_MAP:
        return _MODEL_MAP[batch_id]
    for yf in _g.glob("matrix/*.yaml"):
        try:
            y = _y.safe_load(open(yf, encoding="utf-8"))
            if y and y.get("name") and batch_id.startswith(y["name"]) and y.get("model"):
                return y["model"]
        except Exception:
            continue
    return "unknown"


def _ensure_columns(con) -> None:
    """老库迁移：缺列则 ALTER（幂等）。"""
    cols = {r[1] for r in con.execute("PRAGMA table_info(runs)").fetchall()}
    for col, typ in (("model", "VARCHAR"), ("dead", "BOOLEAN"), ("tps", "DOUBLE")):
        if col not in cols:
            con.execute(f"ALTER TABLE runs ADD COLUMN {col} {typ}")


def ingest(batch_dir: Path) -> None:
    batch_id = batch_dir.name
    runs_file = batch_dir / "runs.jsonl"
    # runs.jsonl 可能含失败重试的历史记录（同 run_id 多条），以最后一条为准
    by_id: dict[str, dict] = {}
    for l in runs_file.read_text(encoding="utf-8").splitlines():
        if l.strip():
            rec = json.loads(l)
            by_id[rec["run_id"]] = rec
    records = list(by_id.values())
    con = connect()
    _ensure_columns(con)
    model = _batch_model(batch_id)
    con.execute("DELETE FROM runs WHERE batch_id = ?", [batch_id])
    con.execute("DELETE FROM events WHERE batch_id = ?", [batch_id])
    con.execute("DELETE FROM signals WHERE batch_id = ?", [batch_id])

    n_events = 0
    for rec in records:
        con.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [batch_id, rec.get("run_id"), rec.get("section"), rec.get("task_id"),
             rec.get("difficulty"), rec.get("arm"), rec.get("inject"), rec.get("rep"),
             rec.get("score"), rec.get("tests"), rec.get("sites_fixed"),
             rec.get("sites_required"), rec.get("cost_usd"), rec.get("num_turns"),
             rec.get("input_tokens"), rec.get("output_tokens"),
             rec.get("cache_creation_tokens"), rec.get("wasted_turns"),
             rec.get("wasted_tokens"), rec.get("wall_s"), rec.get("driver"),
             rec.get("trace_ref"), rec.get("error"),
             model, bool(rec.get("dead")),
             rec.get("tps") if rec.get("tps") is not None else
             (round(rec.get("output_tokens", 0) / rec["wall_s"], 2)
              if rec.get("wall_s") else None)])

        trace_ref = rec.get("trace_ref")
        trace_path = Path(trace_ref) if trace_ref else batch_dir / "work" / rec["run_id"] / "trace.json"
        if trace_path.exists():
            try:
                events = normalize_and_check(trace_path, rec["run_id"])
            except NormalizeError as e:
                print(f"⚠️  {rec['run_id']}: 归一化跳过（{e}）")
                continue
            for idx, ev in enumerate(events):
                con.execute("INSERT INTO events VALUES (?,?,?,?,?,?)",
                            [batch_id, rec["run_id"], idx, ev.get("type"),
                             json.dumps(ev, ensure_ascii=False), ev.get("raw_event_ref")])
            n_events += len(events)
    print(f"批次 {batch_id}：{len(records)} run + {n_events} 事件已灌入 {DB_PATH}")


def ingest_attribution(batch_dir: Path) -> None:
    """跑机械归因并入 attribution 表（零 LLM；证据行号随行存证）。"""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from backend.attribution.engine import (attribute_run, load_events,
                                            load_fids, load_sites_required)
    batch_id = batch_dir.name
    fids = load_fids()
    sites = load_sites_required()
    recs = {r["run_id"]: r for r in
            [json.loads(l) for l in (batch_dir / "runs.jsonl").read_text(
                encoding="utf-8").splitlines() if l.strip()]}
    # 先只读拉事件（DuckDB 同文件读写/只读连接不可共存），再开写连接
    all_events = load_events(list(recs.keys()), batch_id)
    rows = []
    for rid, rec in recs.items():
        evs = all_events.get(rid, [])
        if not evs:
            continue
        sr = sites.get(rec.get("task_id", ""), 1)
        for h in attribute_run(rid, evs, rec, sr, fids)["hits"]:
            rows.append([batch_id, rid, h["f_id"], h["confidence"],
                         ",".join(str(i) for i in h["evidence_idx"]), h["note"]])
    con = connect()
    con.execute("DELETE FROM attribution WHERE batch_id = ?", [batch_id])
    for r in rows:
        con.execute("INSERT OR REPLACE INTO attribution VALUES (?,?,?,?,?,?)", r)
    print(f"批次 {batch_id}：{len(recs)} run → {len(rows)} 条归因写入")


def run_signals(batch_dir: Path) -> None:
    """对已灌事件跑行为信号检测器，写入 signals 表。"""
    batch_id = batch_dir.name
    con = connect()
    con.execute("DELETE FROM signals WHERE batch_id = ?", [batch_id])
    runs = con.execute("SELECT run_id, sites_fixed, sites_required FROM runs WHERE batch_id = ?",
                       [batch_id]).fetchall()
    n = 0
    for run_id, sites_fixed, sites_required in runs:
        rows = con.execute(
            "SELECT payload FROM events WHERE batch_id = ? AND run_id = ? ORDER BY idx",
            [batch_id, run_id]).fetchall()
        events = [json.loads(r[0]) for r in rows]
        record = {"sites_fixed": sites_fixed, "sites_required": sites_required}
        for sig in detect_all(events, record):
            con.execute("INSERT INTO signals VALUES (?,?,?,?,?,?,?,?)",
                        [batch_id, run_id, sig["name"], sig["f_id"], sig["present"],
                         sig.get("wasted_turns"), sig.get("wasted_tokens"),
                         sig.get("detail")])
            n += 1
    print(f"批次 {batch_id}：{n} 条信号记录（{len(runs)} run × 检测器）")


def main() -> int:
    ap = argparse.ArgumentParser(prog="skill-bench store")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_ing = sub.add_parser("ingest")
    p_ing.add_argument("batch_dir")
    p_sig = sub.add_parser("signals")
    p_sig.add_argument("batch_dir")
    p_q = sub.add_parser("query")
    p_q.add_argument("sql")
    args = ap.parse_args()

    if args.cmd == "ingest":
        ingest(Path(args.batch_dir))
    elif args.cmd == "signals":
        run_signals(Path(args.batch_dir))
    else:
        con = connect()
        cur = con.execute(args.sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        print(" | ".join(cols))
        print("-+-".join("-" * len(c) for c in cols))
        for r in rows:
            print(" | ".join(str(x) for x in r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
