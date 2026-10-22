"""一次性补丁：前端注入 GitHub 拉取 + 步骤反馈 JS。"""
from pathlib import Path

p = Path("frontend/skillbench.html")
t = p.read_text(encoding="utf-8")

old_js = '''/* ---------- 提交 ---------- */
function submitContent(name, content) {
  fetch(API + "/api/evals", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, content, dev: false, tier: "quick-lite" }) })
    .then(r => r.json()).then(() => setTimeout(loadList, 3000))
    .catch(() => alert("提交失败：API 未启动？（python -m uvicorn backend.api.server:app --port 8321）"));
}'''

new_js = '''/* ---------- 提交与 GitHub 拉取（每个等待点都有步骤反馈） ---------- */
let fetchedSkill = null;

function ghStatus(html, kind) {
  const el = document.getElementById("gh-status");
  el.style.display = "block";
  const border = kind === "err" ? "rgba(248,113,113,.4)" : (kind === "ok" ? "rgba(52,211,153,.4)" : "var(--line)");
  el.innerHTML = '<div class="card" style="padding:12px 16px;font-size:13px;border-color:' + border + '">' + html + "</div>";
}

function fetchGitHub() {
  const url = document.getElementById("gh-url").value.trim();
  if (!url) return;
  const btn = document.getElementById("gh-btn");
  btn.disabled = true; btn.textContent = "拉取中…";
  ghStatus('<span class="pill run">进行中</span> 解析网址 → 直连拉取 → 校验内容…');
  fetch(API + "/api/fetch-skill", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }) })
    .then(async r => {
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "拉取失败");
      fetchedSkill = { name: d.name, content: d.content };
      const preview = d.content.split("\\n").slice(0, 3).map(l => l.slice(0, 80)).join("\\n");
      ghStatus('<span class="pill g">就绪</span> <b>' + d.name + '</b>（' + d.size + ' 字节）· ' + (d.steps || []).join(" → ")
        + '<div class="codeblock" style="margin-top:8px;max-height:80px">' + preview + '</div>'
        + '<button class="btn" style="margin-top:10px" onclick="startFetched()">开始评测 ' + d.name + '</button>', "ok");
    })
    .catch(e => ghStatus('<span class="pill r">失败</span> ' + e.message, "err"))
    .finally(() => { btn.disabled = false; btn.textContent = "拉取 Skill"; });
}

function startFetched() {
  if (!fetchedSkill) return;
  ghStatus('<span class="pill run">提交中</span> 创建评测单 → 启动流水线…', "ok");
  submitContent(fetchedSkill.name, fetchedSkill.content, () => {
    ghStatus('<span class="pill g">已受理</span> 评测单已创建，流水线启动——下方列表 3 秒后刷新，点行进状态机。', "ok");
    setTimeout(() => { loadList(); }, 2500);
  });
}

function submitContent(name, content, after) {
  fetch(API + "/api/evals", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, content, dev: false, tier: "quick-lite" }) })
    .then(r => r.json()).then(() => { if (after) after(); else setTimeout(loadList, 3000); })
    .catch(() => ghStatus('<span class="pill r">提交失败</span> API 未启动？', "err"));
}'''

assert old_js in t, "old_js not found"
t = t.replace(old_js, new_js)

old_bind = '''document.querySelector(".paste-row input").addEventListener("keydown", ev => {
  if (ev.key === "Enter" && ev.target.value.trim()) {
    submitContent("pasted-skill-" + Date.now() % 10000, ev.target.value);
    ev.target.value = "";
  }
});'''
new_bind = '''document.querySelector(".paste-row input").addEventListener("keydown", ev => {
  if (ev.key === "Enter" && ev.target.value.trim()) {
    submitContent("pasted-skill-" + Date.now() % 10000, ev.target.value);
    ev.target.value = "";
  }
});
document.getElementById("gh-url").addEventListener("keydown", ev => {
  if (ev.key === "Enter") fetchGitHub();
});'''
assert old_bind in t, "old_bind not found"
t = t.replace(old_bind, new_bind)

p.write_text(t, encoding="utf-8", newline="\n")
print("JS 拉取/反馈逻辑已注入")
