"""一次性补丁：db.py 视图升级（B5）+ attribution 表与入库（B4）。"""
from pathlib import Path

p = Path("backend/store/db.py")
t = p.read_text(encoding="utf-8")

# --- B5：v_arm_stats 加 model/dead/tps；新增渠道健康视图 ---
t = t.replace(
    '''CREATE OR REPLACE VIEW v_arm_stats AS
SELECT batch_id, arm, difficulty,
       COUNT(*) AS n,
       AVG(score) AS avg_score,
       SUM(CASE WHEN score = 1.0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS pass_rate,
       AVG(cost_usd) AS avg_cost, SUM(cost_usd) AS total_cost,
       AVG(num_turns) AS avg_turns
FROM runs WHERE error IS NULL
GROUP BY batch_id, arm, difficulty ORDER BY batch_id, arm, difficulty;''',
    '''CREATE OR REPLACE VIEW v_arm_stats AS
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
GROUP BY batch_id ORDER BY batch_id;''')

# --- B4：attribution 表 ---
t = t.replace(
    '''CREATE TABLE IF NOT EXISTS signals (''',
    '''CREATE TABLE IF NOT EXISTS attribution (
    batch_id VARCHAR, run_id VARCHAR, f_id VARCHAR, confidence VARCHAR,
    evidence_idx VARCHAR, note VARCHAR,
    PRIMARY KEY (batch_id, run_id, f_id, evidence_idx)
);
CREATE TABLE IF NOT EXISTS signals (''')

# --- B4：attribution 入库函数 ---
t = t.replace(
    '''def run_signals(batch_dir: Path) -> None:''',
    '''def ingest_attribution(batch_dir: Path) -> None:
    """跑机械归因并入 attribution 表（零 LLM；证据行号随行存证）。"""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from backend.attribution.engine import (attribute_run, load_events,
                                            load_fids, load_sites_required)
    batch_id = batch_dir.name
    con = connect()
    con.execute("DELETE FROM attribution WHERE batch_id = ?", [batch_id])
    fids = load_fids()
    sites = load_sites_required()
    recs = {r["run_id"]: r for r in
            [json.loads(l) for l in (batch_dir / "runs.jsonl").read_text(
                encoding="utf-8").splitlines() if l.strip()]}
    n_attr = 0
    for rid, rec in recs.items():
        evs = load_events([rid], batch_id).get(rid, [])
        if not evs:
            continue
        sr = sites.get(rec.get("task_id", ""), 1)
        attr = attribute_run(rid, evs, rec, sr, fids)
        for h in attr["hits"]:
            con.execute(
                "INSERT OR REPLACE INTO attribution VALUES (?,?,?,?,?,?)",
                [batch_id, rid, h["f_id"], h["confidence"],
                 ",".join(str(i) for i in h["evidence_idx"]), h["note"]])
            n_attr += 1
    print(f"批次 {batch_id}：{len(recs)} run → {n_attr} 条归因写入")


def run_signals(batch_dir: Path) -> None:''')

p.write_text(t, encoding="utf-8")
print("patched: 视图升级 + attribution 表/入库")
