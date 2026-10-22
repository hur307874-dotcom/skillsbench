"""一次性补丁：停止任务按钮（列表行内 + 详情页）+ stopped 状态丸。"""
from pathlib import Path

p = Path("frontend/skillbench.html")
t = p.read_text(encoding="utf-8")

# 1. stopped 状态丸
old_pill = '''function pillFor(e) {
  if (e.status === "running") return `<span class="pill run">${e.stage || "评测中"}</span>`;
  if (e.status === "failed") return `<span class="pill r">失败</span>`;'''
new_pill = '''function pillFor(e) {
  if (e.status === "running") return `<span class="pill run">${e.stage || "评测中"}</span>`;
  if (e.status === "stopped") return `<span class="pill a">已停止</span>`;
  if (e.status === "failed") return `<span class="pill r">失败</span>`;'''
assert old_pill in t, "pillFor not found"
t = t.replace(old_pill, new_pill)

# 2. 列表行：running 单加停止按钮（阻止行点击冒泡）
old_row = '''    <td>${pillFor(e)}</td>'''
new_row = '''    <td>${pillFor(e)}${e.status === "running" ? ` <button class="btn ghost" style="padding:2px 10px;font-size:11px" onclick="event.stopPropagation();stopEval('${e.id}')">■ 停止</button>` : ""}</td>'''
assert old_row in t, "row pill cell not found"
t = t.replace(old_row, new_row)

# 3. 详情页"评测中"卡加停止按钮
old_run = '''    verdictHtml = `<div class="verdict a"><div class="lbl">评测中</div>
      <h2>正在跑「${e.stage}」…</h2>
      <p>渠道健康：${e.channel || "—"}。页面每 8s 自动刷新。</p></div>`;'''
new_run = '''    verdictHtml = `<div class="verdict a"><div class="lbl">评测中</div>
      <h2>正在跑「${e.stage}」…</h2>
      <p>渠道健康：${e.channel || "—"}。页面每 8s 自动刷新。</p>
      <button class="btn ghost" style="margin-top:12px" onclick="stopEval('${e.id}')">■ 停止任务</button>
      <span id="stop-status" style="margin-left:10px;font-size:13px"></span></div>`;'''
assert old_run in t, "running verdict not found"
t = t.replace(old_run, new_run)

# 4. stopEval 函数（挂在 continueEval 前）
old_fn = "function continueEval(id, tier) {"
new_fn = '''function stopEval(id) {
  if (!confirm("确认停止该评测单？（已完成的 run 保留，飞行中的容器自然收尾）")) return;
  const el = document.getElementById("stop-status");
  if (el) el.textContent = "停止中…";
  fetch(API + "/api/evals/" + encodeURIComponent(id) + "/stop", { method: "POST" })
    .then(r => r.json())
    .then(() => { loadList(); setTimeout(loadList, 1500); })
    .catch(() => { if (el) el.textContent = "停止失败"; });
}

function continueEval(id, tier) {'''
assert old_fn in t, "continueEval not found"
t = t.replace(old_fn, new_fn, 1)

p.write_text(t, encoding="utf-8", newline="\n")
print("停止按钮三处注入完成")
