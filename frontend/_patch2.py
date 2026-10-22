"""一次性补丁：虚线框双按钮（提交 Skill + 本地资料库）+ 真拖拽 + 资料库面板。"""
from pathlib import Path

p = Path("frontend/skillbench.html")
t = p.read_text(encoding="utf-8")

# ---- 1. HTML：dropzone 内加双按钮行 ----
old_dz = '''  <div class="dropzone" id="dz" onclick="demoSubmit()">
    <div class="icon">⬆</div>
    <h3>拖入 SKILL.md，或点击选择</h3>
    <div class="sub">支持单文件 / 整个 skill 目录打包（zip）｜ 也可以 <code>skill-bench eval ./my-skill</code> 走 CLI</div>
  </div>'''
new_dz = '''  <div class="dropzone" id="dz">
    <div class="icon">⬆</div>
    <h3>把 SKILL.md 拖进这个虚线框</h3>
    <div class="sub">松手即读取 · 或从下面两个入口选一个</div>
    <div style="display:flex;gap:10px;justify-content:center;margin-top:16px">
      <button class="btn" onclick="event.stopPropagation();demoSubmit()">📁 提交 Skill</button>
      <button class="btn ghost" onclick="event.stopPropagation();openLibrary()">📚 本地资料库选择</button>
    </div>
  </div>
  <div id="lib-panel" style="max-width:640px;margin:12px auto 0;display:none"></div>'''
assert old_dz in t, "dropzone not found"
t = t.replace(old_dz, new_dz)

# ---- 2. JS：真拖拽 + 资料库面板 ----
old_submit = '''function demoSubmit() {
  const inp = document.createElement("input");
  inp.type = "file"; inp.accept = ".md,.markdown,.txt";
  inp.onchange = () => {
    const f = inp.files[0]; if (!f) return;
    const rd = new FileReader();
    rd.onload = () => submitContent(f.name.replace(/\\.\\w+$/, ""), rd.result);
    rd.readAsText(f);
  };
  inp.click();
}'''
new_submit = '''function readSkillFile(f) {
  if (!f) return;
  ghStatus('<span class="pill run">读取中</span> ' + f.name + '…');
  const rd = new FileReader();
  rd.onload = () => {
    fetchedSkill = { name: f.name.replace(/\\.\\w+$/, ""), content: rd.result };
    ghStatus('<span class="pill g">就绪</span> <b>' + fetchedSkill.name + '</b>（' + (f.size || rd.result.length) + ' 字节）'
      + '<button class="btn" style="margin-top:10px" onclick="startFetched()">开始评测 ' + fetchedSkill.name + '</button>', "ok");
  };
  rd.readAsText(f);
}
function demoSubmit() {
  const inp = document.createElement("input");
  inp.type = "file"; inp.accept = ".md,.markdown,.txt";
  inp.onchange = () => readSkillFile(inp.files[0]);
  inp.click();
}

/* 真拖拽：dragover 高亮，drop 读取 */
const dzEl = document.getElementById("dz");
dzEl.addEventListener("dragover", ev => { ev.preventDefault(); dzEl.classList.add("over"); });
dzEl.addEventListener("dragleave", () => dzEl.classList.remove("over"));
dzEl.addEventListener("drop", ev => {
  ev.preventDefault(); dzEl.classList.remove("over");
  readSkillFile(ev.dataTransfer.files[0]);
});
dzEl.addEventListener("click", demoSubmit);

/* 本地资料库面板 */
async function openLibrary() {
  const el = document.getElementById("lib-panel");
  if (el.style.display === "block") { el.style.display = "none"; return; }
  el.style.display = "block";
  el.innerHTML = '<div class="card" style="padding:14px 16px"><span class="pill run">加载中</span> 读取本地资料库…</div>';
  try {
    const r = await fetch(API + "/api/library");
    const d = await r.json();
    el.innerHTML = '<div class="card" style="padding:8px 6px"><table><thead><tr><th>Skill</th><th>大小</th><th>更新</th><th></th></tr></thead><tbody>'
      + d.skills.map(s => '<tr style="cursor:pointer" onclick="pickLibrary(\\'' + s.name + '\\')"><td class="mono">' + s.name + '</td><td class="mono">' + s.size + '</td><td class="mono" style="color:var(--text-3)">' + s.mtime + '</td><td><button class="btn ghost" style="padding:3px 12px">选用</button></td></tr>').join("")
      + '</tbody></table></div>';
  } catch (e) {
    el.innerHTML = '<div class="card" style="padding:14px 16px"><span class="pill r">失败</span> 资料库读取失败（API 未启动？）</div>';
  }
}
async function pickLibrary(name) {
  ghStatus('<span class="pill run">读取中</span> 从资料库取出 ' + name + '…');
  try {
    const r = await fetch(API + "/api/library/" + encodeURIComponent(name) + "/content");
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "读取失败");
    fetchedSkill = { name: d.name, content: d.content };
    const preview = d.content.split("\\n").slice(0, 3).map(l => l.slice(0, 80)).join("\\n");
    ghStatus('<span class="pill g">就绪</span> <b>' + d.name + '</b>（' + d.size + ' 字节，来自本地资料库）'
      + '<div class="codeblock" style="margin-top:8px;max-height:80px">' + preview + '</div>'
      + '<button class="btn" style="margin-top:10px" onclick="startFetched()">开始评测 ' + d.name + '</button>', "ok");
  } catch (e) {
    ghStatus('<span class="pill r">失败</span> ' + e.message, "err");
  }
}'''
assert old_submit in t, "demoSubmit not found"
t = t.replace(old_submit, new_submit)

p.write_text(t, encoding="utf-8", newline="\n")
print("双按钮 + 真拖拽 + 资料库面板已注入")
