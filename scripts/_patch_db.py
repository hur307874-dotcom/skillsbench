"""一次性补丁：db.py 补 model/dead/tps 列（含老库 ALTER 迁移与模型解析）。"""
from pathlib import Path

p = Path("backend/store/db.py")
t = p.read_text(encoding="utf-8")

t = t.replace(
    "    wall_s DOUBLE, driver VARCHAR, trace_ref VARCHAR, error VARCHAR,\n"
    "    PRIMARY KEY (batch_id, run_id)\n);",
    "    wall_s DOUBLE, driver VARCHAR, trace_ref VARCHAR, error VARCHAR,\n"
    "    model VARCHAR, dead BOOLEAN, tps DOUBLE,\n"
    "    PRIMARY KEY (batch_id, run_id)\n);")

HELPERS = '''
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


def ingest(batch_dir: Path) -> None:'''

t = t.replace("def ingest(batch_dir: Path) -> None:", HELPERS, 1)

t = t.replace(
    "    con = connect()\n    con.execute(\"DELETE FROM runs WHERE batch_id = ?\", [batch_id])",
    "    con = connect()\n    _ensure_columns(con)\n    model = _batch_model(batch_id)\n"
    "    con.execute(\"DELETE FROM runs WHERE batch_id = ?\", [batch_id])", 1)

t = t.replace(
    '            "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",',
    '            "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",')
t = t.replace(
    '             rec.get("trace_ref"), rec.get("error")])',
    '             rec.get("trace_ref"), rec.get("error"),\n'
    '             model, bool(rec.get("dead")),\n'
    '             rec.get("tps") if rec.get("tps") is not None else\n'
    '             (round(rec.get("output_tokens", 0) / rec["wall_s"], 2)\n'
    '              if rec.get("wall_s") else None)])')

p.write_text(t, encoding="utf-8")
print("db.py patched")
