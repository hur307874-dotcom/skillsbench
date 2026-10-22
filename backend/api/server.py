"""Skill-Bench API 服务（FastAPI）。

为前端与外部工具提供只读数据接口；数据源自 results/*/runs.jsonl（唯一事实源）、
任务 meta.yaml、docs/EXPERIMENT_LOG。写操作（启动批次）走 CLI，不经 API
（保持"实验发起必须显式命令"的纪律）。

用法：
    python -m uvicorn backend.api.server:app --port 8321 --app-dir .
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.net_guard import install as _ng_install
_ng_install()

app = FastAPI(title="Skill-Bench API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"])


# ---------- 数据加载（runs.jsonl 为唯一事实源；小数据量，实时聚合秒级） ----------

def _batch_model_map() -> dict[str, str]:
    """批次 → 模型解析：显式覆盖表（--model 覆盖批）+ matrix yaml 预设扫描。"""
    overrides = {  # 历史上用 --model 覆盖预设的批次
        "gradient-glm": "glm-5.1/5.2/5.3", "ablation-glm52": "glm-5.2",
        "forged-glm52": "glm-5.2", "pool-v20-glm52": "glm-5.2",
        "real-q1": "claude-opus", "b1-pilot": "claude-haiku",
    }
    m = dict(overrides)
    for yf in glob.glob(str(ROOT / "matrix" / "*.yaml")):
        try:
            y = yaml.safe_load(open(yf, encoding="utf-8"))
            if y and y.get("name") and y.get("model"):
                m.setdefault(y["name"], y["model"])
        except Exception:
            continue
    return m


def _all_runs() -> list[dict]:
    """全量 run 记录（带 batch 归属与模型解析；run_id 去重，后写覆盖先写）。"""
    out: dict[str, dict] = {}
    bmm = _batch_model_map()
    for f in sorted(glob.glob(str(ROOT / "results" / "*" / "runs.jsonl"))):
        batch = Path(f).parent.name
        model = bmm.get(batch) or next(
            (v for k, v in bmm.items() if batch.startswith(k)), "unknown")
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            r["batch"] = batch
            r["model"] = model
            out[f"{batch}/{r['run_id']}"] = r
    return list(out.values())


def _status(r: dict) -> str:
    if r.get("dead"):
        return "dead"
    if "error" in r:
        return "error"
    return "ok"


# ---------- 端点 ----------

@app.get("/api/overview")
def overview() -> dict:
    runs = _all_runs()
    ok = [r for r in runs if _status(r) == "ok"]
    dead = [r for r in runs if _status(r) == "dead"]
    err = [r for r in runs if _status(r) == "error"]
    batches = sorted({r["batch"] for r in runs})
    tasks = sorted({r["task_id"] for r in runs})
    models = sorted({r.get("model", "") for r in runs if r.get("model")})
    return {
        "total_runs": len(runs), "ok_runs": len(ok), "dead_runs": len(dead),
        "error_runs": len(err), "batches": len(batches), "tasks": len(tasks),
        "models": models,
        "conclusions": [
            {"id": "C1", "text": "v1（原版 tdd）成本持续高于裸考（轮次 +25~33%）",
             "strength": "★★★ 三批复现"},
            {"id": "C2", "text": "v3（修订版）开销压到 v1 与 A0 之间（降本）",
             "strength": "★★★ 三批复现"},
            {"id": "C3", "text": "分数侧无正收益（健康渠道，可测范围内）",
             "strength": "★★★ n=5 全矩阵"},
            {"id": "C4", "text": "v1 弱基座随机性预算失效（仪式耗预算）",
             "strength": "★★ 定性清晰，健康窗口复测中"},
            {"id": "C5", "text": "完成率/超时指标混淆渠道健康度（须吞吐校正）",
             "strength": "★★★ 方法论（渠道混淆发现）"},
        ],
    }


@app.get("/api/matrix")
def matrix() -> dict:
    """模型 × 臂 × 任务 聚合（满分率 / 均分 / 均轮 / 死跑率）。"""
    runs = _all_runs()
    cells: dict = {}
    for r in runs:
        model = r.get("model") or "unknown"
        key = (model, r["arm"], r["task_id"])
        c = cells.setdefault(key, {"n": 0, "dead": 0, "error": 0, "pass": 0,
                                   "scores": [], "turns": [], "tps": []})
        c["n"] += 1
        st = _status(r)
        if st == "dead":
            c["dead"] += 1
        elif st == "error":
            c["error"] += 1
        else:
            c["scores"].append(r["score"])
            c["turns"].append(r["num_turns"])
            if r.get("tps"):
                c["tps"].append(r["tps"])
            if r["score"] == 1.0:
                c["pass"] += 1
    out = []
    for (model, arm, task), c in sorted(cells.items()):
        v = len(c["scores"])
        out.append({
            "model": model, "arm": arm, "task_id": task, "n": c["n"],
            "dead": c["dead"], "error": c["error"],
            "pass_rate": round(c["pass"] / c["n"], 3) if c["n"] else 0,
            "avg_score": round(sum(c["scores"]) / v, 3) if v else None,
            "avg_turns": round(sum(c["turns"]) / v, 1) if v else None,
            "avg_tps": round(sum(c["tps"]) / len(c["tps"]), 1) if c["tps"] else None,
        })
    return {"cells": out}


@app.get("/api/tasks")
def tasks() -> dict:
    """任务池（pool-v2 定稿 9 个 + 旧池概览）。"""
    out = []
    for mp in sorted((ROOT / "tasks" / "pool-v2" / "forged-final").glob("*/meta.yaml")):
        meta = yaml.safe_load(mp.read_text(encoding="utf-8"))
        td = mp.parent
        out.append({
            "task_id": meta["task_id"], "track": meta.get("track"),
            "difficulty": meta.get("difficulty"),
            "horizon_minutes": meta.get("horizon_minutes"),
            "targets_fids": meta.get("targets_fids"),
            "sites_required": meta.get("sites_required"),
            "baseline": meta.get("baseline"),
            "prompt": meta.get("prompt", "").strip()[:200],
            "has_intent": (td / "INTENT.md").exists(),
            "has_wrong": (td / "wrong" / "wrong_01").is_dir(),
            "has_p2p": any((td / "tests" / "p2p").glob("test_*.py"))
            if (td / "tests" / "p2p").is_dir() else False,
        })
    return {"tasks": out, "pool": "pool-v2.0（forged-final，四关+P2P 全过）"}


@app.get("/api/tasks/{task_id}")
def task_detail(task_id: str) -> dict:
    td = ROOT / "tasks" / "pool-v2" / "forged-final" / task_id
    if not td.is_dir():
        raise HTTPException(404, f"任务不存在：{task_id}")
    meta = yaml.safe_load((td / "meta.yaml").read_text(encoding="utf-8"))
    intent = (td / "INTENT.md").read_text(encoding="utf-8") \
        if (td / "INTENT.md").exists() else ""
    runs = [r for r in _all_runs() if r["task_id"] == task_id]
    return {"meta": meta, "intent": intent,
            "runs": sorted(runs, key=lambda r: (r["batch"], r["arm"], r["rep"]))}


@app.get("/api/batches")
def batches() -> dict:
    runs = _all_runs()
    agg: dict = {}
    for r in runs:
        b = agg.setdefault(r["batch"], {"n": 0, "dead": 0, "error": 0, "pass": 0,
                                        "scores": [], "tasks": set(), "models": set()})
        b["n"] += 1
        st = _status(r)
        if st == "dead":
            b["dead"] += 1
        elif st == "error":
            b["error"] += 1
        else:
            b["scores"].append(r["score"])
            if r["score"] == 1.0:
                b["pass"] += 1
        b["tasks"].add(r["task_id"])
        if r.get("model"):
            b["models"].add(r["model"])
    return {"batches": [
        {"batch": k, "n": v["n"], "dead": v["dead"], "error": v["error"],
         "pass": v["pass"],
         "avg_score": round(sum(v["scores"]) / len(v["scores"]), 3) if v["scores"] else None,
         "tasks": len(v["tasks"]), "models": sorted(v["models"])}
        for k, v in sorted(agg.items())]}


@app.get("/api/batches/{batch_id}")
def batch_detail(batch_id: str) -> dict:
    runs = [r for r in _all_runs() if r["batch"] == batch_id]
    if not runs:
        raise HTTPException(404, f"批次不存在：{batch_id}")
    for r in runs:
        r["status"] = _status(r)
    return {"batch": batch_id,
            "runs": sorted(runs, key=lambda r: (r["task_id"], r["arm"], r["rep"]))}


@app.get("/api/skill-versions")
def skill_versions() -> dict:
    """Skill 版本链：v1 冻结 → v2（被拦）→ v3（定版）→ heldout 终验。"""
    out = []
    for name in ("tdd-v1", "tdd-v2", "tdd-v3"):
        sd = ROOT / "skills" / name
        if not sd.is_dir():
            continue
        revision = sd / "REVISION.md"
        manifest = sd / "manifest.yaml"
        skill_md = sd / "SKILL.md"
        out.append({
            "version": name,
            "sha256": (sd / "SHA256").read_text().strip()
            if (sd / "SHA256").exists() else None,
            "lines": len(skill_md.read_text(encoding="utf-8").splitlines())
            if skill_md.exists() else None,
            "has_manifest": manifest.exists(),
            "revision": revision.read_text(encoding="utf-8")[:2000]
            if revision.exists() else None,
        })
    return {"versions": out}


@app.get("/api/attribution")
def attribution(batch: str | None = None, skill: str | None = None) -> dict:
    """归因查询：机械检测器（L2）+ 可选 manifest 指令联动（L3）。"""
    from backend.attribution.engine import (aggregate, attribute_run,
                                            link_manifest, load_events,
                                            load_fids, load_run_records,
                                            load_sites_required)
    fids = load_fids()
    events_by_run = load_events(None, batch)
    recs = load_run_records(batch)
    sites_map = load_sites_required()
    records = []
    for rid, evs in sorted(events_by_run.items()):
        rec = recs.get(rid)
        sr = sites_map.get(rec["task_id"], 1) if rec else 1
        records.append(attribute_run(rid, evs, rec, sr, fids))
    links = []
    if skill:
        sd = ROOT / skill
        if not sd.is_dir():
            raise HTTPException(404, f"Skill 目录不存在：{skill}")
        for r in records:
            for link in link_manifest(r["hits"], sd):
                links.append({**link, "run_id": r["run_id"]})
    return {"aggregate": aggregate(records), "records": records,
            "instruction_links": links}


@app.get("/api/runs/{batch_id}/{run_id}")
def run_detail(batch_id: str, run_id: str) -> dict:
    """单 run 详情：记录 + 归因命中 + 事件流（前端下钻用）。"""
    import duckdb
    rec = next((r for r in _all_runs()
                if r["batch"] == batch_id and r["run_id"] == run_id), None)
    if rec is None:
        raise HTTPException(404, f"run 不存在：{batch_id}/{run_id}")
    db = ROOT / "results" / "traces.duckdb"
    events, attribution = [], []
    if db.exists():
        con = duckdb.connect(str(db), read_only=True)
        try:
            events = [{"idx": i, "type": t_, "payload": json.loads(pl)}
                      for i, t_, pl in con.execute(
                          "SELECT idx, type, payload FROM events "
                          "WHERE batch_id=? AND run_id=? ORDER BY idx",
                          [batch_id, run_id]).fetchall()]
        except Exception:
            events = []
        try:
            attribution = [{"f_id": f, "confidence": c, "evidence": e, "note": n}
                           for f, c, e, n in con.execute(
                               "SELECT f_id, confidence, evidence_idx, note "
                               "FROM attribution WHERE batch_id=? AND run_id=?",
                               [batch_id, run_id]).fetchall()]
        except Exception:
            attribution = []
        con.close()
    return {**rec, "status": _status(rec), "events": events,
            "attribution": attribution}


@app.get("/api/log")
def experiment_log(limit: int = 20) -> dict:
    """实验日志流：EXPERIMENT_LOG.md 的批次段落索引（倒序）。"""
    f = ROOT / "docs" / "EXPERIMENT_LOG.md"
    if not f.exists():
        raise HTTPException(404, "实验日志不存在")
    text = f.read_text(encoding="utf-8")
    sections, cur = [], None
    for line in text.splitlines():
        if line.startswith("### "):
            if cur:
                sections.append(cur)
            cur = {"title": line[4:].strip(), "lines": []}
        elif cur is not None:
            cur["lines"].append(line)
    if cur:
        sections.append(cur)
    return {"sections": [{"title": s["title"],
                          "body": chr(10).join(s["lines"]).strip()}
                         for s in sections[-limit:][::-1]]}


@app.get("/api/gate/health")
def gate_health(batch: str) -> dict:
    """渠道健康（Pilot Gate 模块的只读包装）。"""
    from backend.gate.pilot_gate import channel_health
    d = ROOT / "results" / batch
    if not d.is_dir():
        raise HTTPException(404, f"批次不存在：{batch}")
    return channel_health(d)


# ---------- GitHub Skill 拉取（路演功能：输入网址 → 逐步反馈 → SKILL.md） ----------

import re as _re
import subprocess as _sp
import time as _time
import urllib.request as _urlreq

from pydantic import BaseModel

# 本机代理（127.0.0.1:10808）到 GitHub 全挂；直连反而通——专用无代理 opener（2026-10-05 实测）
_NO_PROXY_OPENER = _urlreq.build_opener(_urlreq.ProxyHandler({}))


class FetchSkillReq(BaseModel):
    url: str


class EvalSubmit(BaseModel):
    name: str
    content: str            # SKILL.md 全文
    dev: bool = False       # 管线自检模式（2 任务，分钟级）
    tier: str = "standard"


def _gh_get(url: str, timeout: int = 20, retries: int = 3) -> bytes:
    """直连拉取（无代理通道）+ 重试：raw.githubusercontent 直连可用但偶发抖动。"""
    last: Exception | None = None
    for i in range(retries):
        try:
            req = _urlreq.Request(url, headers={"User-Agent": "skill-bench/1.0"})
            with _NO_PROXY_OPENER.open(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries - 1:
                _time.sleep(1.5 * (i + 1))
    raise last  # type: ignore[misc]


def _parse_github(url: str) -> dict:
    """解析 GitHub URL → (raw_url, name, kind)。支持 blob/tree/仓库根/raw 直链。"""
    u = url.strip().rstrip("/")
    m = _re.match(r"https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)", u)
    if m:
        o, r, b, p = m.groups()
        name = p.rsplit("/", 2)[-2] if p.endswith("SKILL.md") else p.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        return {"raw": f"https://raw.githubusercontent.com/{o}/{r}/{b}/{p}",
                "name": name, "kind": "blob"}
    m = _re.match(r"https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.+)", u)
    if m:
        o, r, b, p = m.groups()
        return {"raw": f"https://raw.githubusercontent.com/{o}/{r}/{b}/{p}/SKILL.md",
                "name": p.rsplit("/", 1)[-1], "kind": "tree"}
    m = _re.match(r"https?://github\.com/([^/]+)/([^/]+)/?$", u)
    if m:
        o, r = m.groups()
        return {"raw": "", "name": r, "kind": "repo", "owner": o, "repo": r}
    if "raw.githubusercontent.com" in u:
        return {"raw": u, "name": u.rstrip("/").rsplit("/", 2)[-2], "kind": "raw"}
    raise HTTPException(400, "无法解析的 GitHub 网址（支持 blob/tree/仓库根/raw 直链）")


@app.post("/api/fetch-skill")
def fetch_skill(body: FetchSkillReq) -> dict:
    """GitHub 网址 → SKILL.md 内容（逐步反馈在 steps 里）。"""
    steps: list[str] = []
    info = _parse_github(body.url)
    steps.append(f"解析网址 ✓（{info['kind']}）")
    try:
        if info["kind"] == "repo":
            for cand in (f"https://raw.githubusercontent.com/{info['owner']}/{info['repo']}/main/SKILL.md",
                         f"https://raw.githubusercontent.com/{info['owner']}/{info['repo']}/master/SKILL.md"):
                try:
                    content = _gh_get(cand)
                    info["raw"] = cand
                    break
                except Exception:  # noqa: BLE001
                    continue
            if not info["raw"]:
                raise HTTPException(404, "仓库根未找到 SKILL.md——请给 skill 目录（tree）或文件（blob）链接")
        steps.append("直连拉取（无代理通道）…")
        content = _gh_get(info["raw"])
        text = content.decode("utf-8", "replace")
        if len(text.strip()) < 50:
            raise HTTPException(422, "内容过短，不像 SKILL.md")
        steps.append(f"下载 ✓（{len(content)} 字节）")
        steps.append("校验 ✓")
        return {"ok": True, "name": info["name"], "content": text,
                "size": len(content), "source": info["raw"], "steps": steps}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        steps.append(f"失败：{str(e)[:80]}")
        raise HTTPException(502, f"拉取失败：{str(e)[:100]}（{' → '.join(steps)}）")


def _eval_dirs() -> list[Path]:
    return sorted((ROOT / "results").glob("eval-*/"), key=lambda p: p.stat().st_mtime,
                  reverse=True)


def _eval_summary(d: Path) -> dict:
    st = {}
    sf = d / "status.json"
    if sf.exists():
        st = json.loads(sf.read_text(encoding="utf-8"))
    v = {}
    vf = d / "verdict.json"
    if vf.exists():
        v = json.loads(vf.read_text(encoding="utf-8"))
    stage = st.get("stage", "预检")
    if stage == "stopped":
        status = "stopped"
    elif stage == "done" or (not st and v):
        status = "done"      # verdict.json 在而 status.json 无 = 状态机上线前完成的旧单
    elif stage == "failed":
        status = "failed"
    else:
        status = "running"
    runs = 0
    for b in v.get("batches", []):
        f = ROOT / "results" / b / "runs.jsonl"
        if f.exists():
            runs += sum(1 for line in f.open(encoding="utf-8") if line.strip())
    return {"id": d.name, "name": st.get("eval", d.name), "status": status,
            "stage": stage, "reason": st.get("reason", ""),
            "channel": st.get("channel", v.get("channel", "")),
            "decision": v.get("decision", st.get("decision", "")),
            "verdict": v.get("verdict", ""),
            "signal": (v.get("signal") or {}).get("positive_pairs", st.get("signal", "")),
            "cost_ratio": (v.get("signal") or {}).get("cost_ratio", st.get("cost_ratio", "")),
            "runs": runs, "at": st.get("started_at", ""),
            "updated_at": st.get("updated_at", "")}


@app.post("/api/evals", status_code=201)
def create_eval(body: EvalSubmit) -> dict:
    """提交 Skill 评测单：落盘 skills/incoming/ → 后台起 eval_skill 流水线。"""
    name = _re.sub(r"[^a-zA-Z0-9._-]", "-", body.name.strip())[:60] or "unnamed"
    if not body.content.strip():
        raise HTTPException(400, "SKILL.md 内容为空")
    stamp = _time.strftime("%m%d-%H%M%S")
    incoming = ROOT / "skills" / "incoming" / f"{name}-{stamp}"
    incoming.mkdir(parents=True, exist_ok=True)
    (incoming / "SKILL.md").write_text(body.content, encoding="utf-8", newline="\n")
    cmd = [sys.executable, "scripts/eval_skill.py", str(incoming),
           "--tier", body.tier]
    if body.dev:
        cmd.append("--dev")
    logf = incoming / "submit.log"
    with logf.open("w", encoding="utf-8") as f:
        _sp.Popen(cmd, cwd=ROOT, stdout=f, stderr=_sp.STDOUT,
                  creationflags=getattr(_sp, "CREATE_NEW_PROCESS_GROUP", 0)
                  | getattr(_sp, "CREATE_NO_WINDOW", 0))
    return {"ok": True, "incoming": incoming.name,
            "note": "流水线已启动；eval id 形如 eval-<name>-<stamp>，"
                    "用 GET /api/evals 轮询状态"}


@app.get("/api/evals")
def list_evals() -> dict:
    """评测单列表（新→旧）。"""
    return {"evals": [_eval_summary(d) for d in _eval_dirs()]}


@app.get("/api/evals/{eval_id}")
def eval_detail(eval_id: str) -> dict:
    """评测单详情：状态机 + 判定 + 分臂对照。"""
    d = ROOT / "results" / eval_id
    if not d.is_dir():
        raise HTTPException(404, f"评测单不存在：{eval_id}")
    s = _eval_summary(d)
    v = {}
    vf = d / "verdict.json"
    if vf.exists():
        v = json.loads(vf.read_text(encoding="utf-8"))
    # 分臂对照：取分诊批（evallite-*）runs.jsonl 聚合
    arms: dict[str, dict] = {}
    from backend.analysis.cli_report import arm_stats
    for b in v.get("batches", []):
        bd = ROOT / "results" / b
        if b.startswith("evallite") and (bd / "runs.jsonl").exists():
            from backend.analysis.cli_report import load_runs as _lr
            arms = arm_stats(_lr(bd))
            break
    return {**s, "arms": arms, "batches": v.get("batches", []),
            "finished_at": v.get("finished_at", "")}


class ContinueReq(BaseModel):
    tier: str = "quick"     # quick-lite | quick | standard


@app.post("/api/evals/{eval_id}/stop")
def stop_eval(eval_id: str) -> dict:
    """停止评测单：STOP 旗标（阶段切换优雅退出）+ taskkill 进程树（立即硬停）。

    注：已在飞行中的 docker 容器会自然跑完/超时（--rm 自清理，无泄漏）。
    """
    d = ROOT / "results" / eval_id
    if not d.is_dir():
        raise HTTPException(404, f"评测单不存在：{eval_id}")
    (d / "STOP").write_text("stop\n", encoding="utf-8")
    killed = []
    sf = d / "status.json"
    if sf.exists():
        st = json.loads(sf.read_text(encoding="utf-8"))
        pid = st.get("pid")
        if pid:
            r = _sp.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                        capture_output=True)
            killed.append({"pid": pid, "rc": r.returncode})
        st.update({"stage": "stopped",
                   "updated_at": _time.strftime("%H:%M:%S")})
        sf.write_text(json.dumps(st, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    return {"ok": True, "killed": killed, "note": "已停止（旗标+进程树双保险）"}


@app.post("/api/evals/{eval_id}/continue")
def continue_eval(eval_id: str, body: ContinueReq) -> dict:
    """继续测评：按更高档位复跑同一 Skill（从评测单预设里找回原 Skill 路径）。"""
    d = ROOT / "results" / eval_id
    if not d.is_dir():
        raise HTTPException(404, f"评测单不存在：{eval_id}")
    skill_path = None
    for y in ("quicklite.yaml", "smoke.yaml"):
        f = d / y
        if f.exists():
            m = _re.search(r"skill:\s*(\S+)", f.read_text(encoding="utf-8"))
            if m:
                skill_path = m.group(1)
                break
    if not skill_path or not (ROOT / skill_path / "SKILL.md").exists():
        raise HTTPException(400, "无法从评测单找回原 Skill 路径")
    if body.tier not in ("quick-lite", "quick", "standard"):
        raise HTTPException(400, "tier 必须是 quick-lite/quick/standard")
    cmd = [sys.executable, "scripts/eval_skill.py", skill_path,
           "--tier", body.tier]
    logf = d / f"continue-{body.tier}.log"
    with logf.open("w", encoding="utf-8") as f:
        _sp.Popen(cmd, cwd=ROOT, stdout=f, stderr=_sp.STDOUT,
                  creationflags=getattr(_sp, "CREATE_NEW_PROCESS_GROUP", 0)
                  | getattr(_sp, "CREATE_NO_WINDOW", 0))
    return {"ok": True, "tier": body.tier, "skill": skill_path,
            "note": "复测流水线已启动（新评测单将出现在列表顶部）"}


# ---------- 前端静态托管 ----------

# ---------- 弊端定位与改进（题目核心：定位在哪里失效 → 有依据修改 → 再验证） ----------

_RULES_PROMPT = """读下面的 Skill 文档，提取其中**独立的规则/指令**（每条是可单独遵循或违背的要求）。

要求：每条给出 id（短横线命名）、rule（一句话）、cost_hint（遵循它需要 agent 付出什么
仪式开销：阅读篇幅/额外步骤/额外工具调用/写测试/写文档——高/中/低）。
输出严格 JSON 数组，最多 8 条，不要其他文字。

Skill 文档：
{skill_md}
"""

_OFFENSE_PROMPT = """你是 Skill 体检医师。一个 Skill 刚跑完对照评测，请定位**哪条规则弊端最大**。

评测数据：
- 判定：{verdict}
- 逐任务配对正符号：{signal}（0 = Skill 臂没有任何任务超过裸考）
- 成本比：×{cost_ratio}（>1.2 = 注入带来显著仪式开销）
- 分臂对照：{arms}
- Skill 臂 agent 的行为叙事节选（真实 trace）：
{narrative}

Skill 的规则清单：
{rules}

要求：
1. 按"弊端贡献"给规则排序——综合：该规则的仪式开销（agent 为它空转多少）、
   与零增益/负效果的因果（叙事里是否在为它做无用功）、必要性（删掉损失什么）；
2. 输出严格 JSON：
   {{"offenders": [{{"id": "...", "rule": "...", "severity": "高|中|低",
     "evidence": "来自叙事/数据的具体证据一句话", "fix": "具体改法一句话"}}],
    "overall": "这个 Skill 的核心问题一句话"}}
不要输出其他文字。"""

_IMPROVE_PROMPT = """你是 Skill 编辑。基于弊端分析改写这个 Skill：减仪式、留干货。

原始文档：
{skill_md}

弊端分析（按危害排序）：
{offenders}

改写原则：
1. 高弊端规则：删除或压缩到一行以内；
2. 中弊端：合并同类，砍掉重复说理（道理一遍就够）；
3. 保留：具体可操作的检查清单、硬约定（命名/返回值/顺序）、真实案例——这些才是知识增量；
4. 篇幅目标：不超过原文 50%；
5. 保持 Markdown 结构，开头保留 --- name/description frontmatter。

直接输出改写后的完整 SKILL.md，不要任何解释。"""


def _eval_skill_path(d: Path) -> str | None:
    for y in ("quicklite.yaml", "smoke.yaml"):
        f = d / y
        if f.exists():
            m = _re.search(r"skill:\s*(\S+)", f.read_text(encoding="utf-8"))
            if m:
                return m.group(1)
    return None


@app.post("/api/evals/{eval_id}/analyze")
def analyze_eval(eval_id: str) -> dict:
    """弊端定位 + 改进版（辅助 LLM 定性结论，全部带'待复核'水印——κ 门纪律）。"""
    from backend.llm_client import chat as _chat
    d = ROOT / "results" / eval_id
    if not d.is_dir():
        raise HTTPException(404, f"评测单不存在：{eval_id}")
    af = d / "analysis.json"
    if af.exists():
        return json.loads(af.read_text(encoding="utf-8"))
    v = {}
    vf = d / "verdict.json"
    if vf.exists():
        v = json.loads(vf.read_text(encoding="utf-8"))
    skill_path = _eval_skill_path(d)
    if not skill_path or not (ROOT / skill_path / "SKILL.md").exists():
        raise HTTPException(400, "无法从评测单找回原 Skill")
    skill_md = (ROOT / skill_path / "SKILL.md").read_text(encoding="utf-8")

    # ① 规则提取（DIS 偶发空 completion——空结果重试一次再报错）
    rules = []
    for attempt in range(2):
        try:
            out = _chat([{"role": "user", "content":
                          _RULES_PROMPT.format(skill_md=skill_md[:7000])}],
                        temperature=0, max_tokens=1500, timeout=120)
            m = _re.search(r"\[.*\]", out, _re.S)
            rules = json.loads(m.group(0)) if m else []
            if rules:
                break
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            if attempt == 1:
                raise HTTPException(502, f"规则提取失败：{str(e)[:80]}")
            _time.sleep(2)
    if not rules:
        raise HTTPException(502, "规则提取为空（辅助 LLM 两次均未返回有效 JSON），请重试")

    # ② 行为叙事节选（A1f 臂 trace 的 assistant 文本，最多 6 段）
    narrative: list[str] = []
    from backend.attribution.engine import events_from_raw
    for b in v.get("batches", []):
        wdir = ROOT / "results" / b / "work"
        if not wdir.is_dir():
            continue
        for rd in sorted(wdir.iterdir()):
            if "A1f" not in rd.name or len(narrative) >= 6:
                continue
            evs, _ = events_from_raw(str(rd / "trace.json"))
            for e in evs:
                if e["type"] == "step" and e["payload"].get("role") == "assistant":
                    txt = (e["payload"].get("text") or "")[:200]
                    if txt.strip():
                        narrative.append(txt)
    # 分臂对照文本
    arms_txt = json.dumps(v.get("decisive", {}), ensure_ascii=False)[:300]

    # ③ 弊端排序
    try:
        out = _chat([{"role": "user", "content": _OFFENSE_PROMPT.format(
            verdict=v.get("verdict", "（无判定）"),
            signal=(v.get("signal") or {}).get("positive_pairs", "?"),
            cost_ratio=(v.get("signal") or {}).get("cost_ratio", "?"),
            arms=arms_txt,
            narrative="\n".join(f"· {n}" for n in narrative) or "（无 trace 叙事）",
            rules=json.dumps(rules, ensure_ascii=False, indent=1))}],
            temperature=0, max_tokens=1500, timeout=150)
        m = _re.search(r"\{.*\}", out, _re.S)
        offense = json.loads(m.group(0)) if m else {"offenders": [], "overall": "解析失败"}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"弊端分析失败：{str(e)[:80]}")

    # ④ 改进版生成
    improved = ""
    if offense.get("offenders"):
        try:
            improved = _chat([{"role": "user", "content": _IMPROVE_PROMPT.format(
                skill_md=skill_md[:7000],
                offenders=json.dumps(offense["offenders"], ensure_ascii=False, indent=1))}],
                temperature=0, max_tokens=4000, timeout=240)
        except Exception:  # noqa: BLE001
            improved = ""

    result = {"eval": eval_id, "skill": skill_path, "rules": rules,
              "offenders": offense.get("offenders", []),
              "overall": offense.get("overall", ""),
              "improved": improved,
              "watermark": "辅助 LLM 定性结论（κ 门未过前待人工复核）；定量判定以 runs.jsonl 为准",
              "generated_at": _time.strftime("%Y-%m-%d %H:%M:%S")}
    af.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


@app.get("/api/evals/{eval_id}/tasks")
def eval_tasks(eval_id: str) -> dict:
    """任务级下钻：逐任务 A0/A1f 配对分数（题目的'任务级下钻'要求）。"""
    d = ROOT / "results" / eval_id
    if not d.is_dir():
        raise HTTPException(404, f"评测单不存在：{eval_id}")
    v = {}
    vf = d / "verdict.json"
    if vf.exists():
        v = json.loads(vf.read_text(encoding="utf-8"))
    from backend.analysis.cli_report import load_runs as _lr, is_channel_dead as _cd
    rows: dict[str, dict[str, list]] = {}
    for b in v.get("batches", []):
        if not b.startswith(("evallite", "evaldecisive")):
            continue
        bd = ROOT / "results" / b
        for r in _lr(bd):
            if _cd(r) or not isinstance(r.get("score"), (int, float)):
                continue
            rows.setdefault(r["task_id"], {}).setdefault(r["arm"], []).append(
                {"score": r["score"], "turns": r.get("num_turns", 0),
                 "out_tok": r.get("output_tokens", 0), "run_id": r.get("run_id", ""),
                 "batch": b, "trace_ref": r.get("trace_ref", "")})
    tasks = []
    for t, arms in sorted(rows.items()):
        def _m(k, field):
            arr = arms.get(k, [])
            return round(sum(x[field] for x in arr) / len(arr), 3) if arr else None
        tasks.append({"task": t,
                      "a0_score": _m("A0", "score"), "a1f_score": _m("A1f", "score"),
                      "a0_turns": _m("A0", "turns"), "a1f_turns": _m("A1f", "turns"),
                      "delta": (round(_m("A1f", "score") - _m("A0", "score"), 3)
                                if _m("A0", "score") is not None and _m("A1f", "score") is not None else None),
                      "runs": {k: [x["run_id"] for x in arr] for k, arr in arms.items()}})
    return {"eval": eval_id, "tasks": tasks}


@app.get("/api/trace")
def trace_view(batch: str, run: str, limit: int = 60) -> dict:
    """Trace 检视（题目'可观测性'要求）：run 的事件流（人类/Agent 可读）。"""
    tp = ROOT / "results" / batch / "work" / run / "trace.json"
    if not tp.exists():
        raise HTTPException(404, f"trace 不存在：{batch}/{run}")
    from backend.attribution.engine import events_from_raw
    evs, outputs = events_from_raw(str(tp))
    out = []
    for e in evs[-limit:]:
        p = e["payload"]
        if e["type"] == "tool_call":
            out.append({"idx": e["idx"], "kind": "tool",
                        "text": f"{p.get('name')}: {str(p.get('args'))[:150]}",
                        "output": (outputs.get(e["idx"]) or "")[:300]})
        else:
            out.append({"idx": e["idx"], "kind": p.get("role", "?"),
                        "text": (p.get("text") or "")[:300]})
    return {"batch": batch, "run": run, "events": out}


_frontend = ROOT / "frontend"
if _frontend.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
