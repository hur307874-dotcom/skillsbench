"""一次性补丁：详情页判定卡下加"继续测评"操作组。"""
from pathlib import Path

p = Path("frontend/skillbench.html")
t = p.read_text(encoding="utf-8")

# 1. 在详情模板里插入操作组（verdictHtml 之后）
old_tpl = "${statsHtml}${verdictHtml}${armsHtml}"
new_tpl = "${statsHtml}${verdictHtml}${actionsHtml}${armsHtml}"
assert old_tpl in t
t = t.replace(old_tpl, new_tpl, 1)

# 2. openDetail 里生成 actionsHtml（在 statsHtml 定义之后）
old_anchor = '''  $("#detail-body").innerHTML = `'''
new_anchor = '''  let actionsHtml = "";
  if (e.status === "done") {
    const primary = e.decision === "decisive-positive" ? "standard" : "quick";
    actionsHtml = `<div class="section" style="margin-top:18px">
      <div class="head"><span class="idx">▶</span><h2>继续测评</h2>
        <span class="note">判定不是终点——升级档位复测或加厚验证</span></div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="btn${primary === "quick" ? "" : " ghost"}" onclick="continueEval('${e.id}','quick')">升级 quick 48 复测</button>
        <button class="btn${primary === "standard" ? "" : " ghost"}" onclick="continueEval('${e.id}','standard')">standard 确诊档</button>
        <button class="btn ghost" onclick="continueEval('${e.id}','quick-lite')">重跑一次（quick-lite）</button>
      </div>
      <div id="cont-status" style="margin-top:10px;font-size:13px"></div>
    </div>`;
  }

  $("#detail-body").innerHTML = `'''
assert old_anchor in t
t = t.replace(old_anchor, new_anchor, 1)

# 3. continueEval 函数（挂在 submitContent 前）
old_fn = "function submitContent(name, content, after) {"
new_fn = '''function continueEval(id, tier) {
  const el = document.getElementById("cont-status");
  const label = { "quick": "quick 48", "standard": "standard 确诊", "quick-lite": "quick-lite" }[tier] || tier;
  el.innerHTML = '<span class="pill run">受理中</span> 正在启动 ' + label + ' 流水线…';
  fetch(API + "/api/evals/" + encodeURIComponent(id) + "/continue", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tier }) })
    .then(async r => {
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "启动失败");
      el.innerHTML = '<span class="pill g">已受理</span> ' + (d.note || "") + '——3 秒后回列表看新评测单';
      setTimeout(() => { go("home"); loadList(); }, 3000);
    })
    .catch(e2 => { el.innerHTML = '<span class="pill r">失败</span> ' + e2.message; });
}

function submitContent(name, content, after) {'''
assert old_fn in t
t = t.replace(old_fn, new_fn, 1)

p.write_text(t, encoding="utf-8", newline="\n")
print("继续测评操作组已注入")
