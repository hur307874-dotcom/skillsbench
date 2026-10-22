"""一次性：前端补归因视图 + 渠道健康视图（B14）。"""
from pathlib import Path

p = Path("frontend/index.html")
t = p.read_text(encoding="utf-8")

t = t.replace(
    '  <button data-v="versions">Skill 版本链</button>',
    '  <button data-v="attribution">归因</button>\n'
    '  <button data-v="channel">渠道健康</button>\n'
    '  <button data-v="versions">Skill 版本链</button>')

t = t.replace(
    '  <section id="v-versions" class="view">',
    '''  <section id="v-attribution" class="view">
    <p class="muted" style="margin-bottom:10px">批次：
      <select id="at-batch"></select>
      <span style="margin-left:14px">机械检测器（零 LLM）· 证据行号随行 · κ 未过门前仅定性</span>
    </p>
    <div id="at-summary"></div>
    <div id="at-records" style="margin-top:14px"></div>
  </section>

  <section id="v-channel" class="view">
    <p class="muted" style="margin-bottom:10px">
      渠道健康 = 批次中位 token 吞吐（tps）对照全库历史中位；低于 50% 判降级窗口，
      该窗口内的完成率类结论须挂“渠道存疑”标签。</p>
    <div id="ch-table"></div>
  </section>

  <section id="v-versions" class="view">''')

JS = '''// ---- 归因 ----
async function loadAttribution() {
  const bt = await api('/api/batches');
  const opts = bt.batches.map(b => b.batch).reverse();
  $('#at-batch').innerHTML = opts.map(b => `<option>${esc(b)}</option>`).join('');
  $('#at-batch').onchange = () => renderAttribution($('#at-batch').value);
  await renderAttribution(opts[0]);
}
async function renderAttribution(batch) {
  const d = await api('/api/attribution?batch=' + encodeURIComponent(batch));
  const agg = d.aggregate;
  $('#at-summary').innerHTML = `<div class="cards">
    <div class="card"><div class="num">${agg.total_runs}</div><div class="lbl">run 总数</div></div>
    <div class="card"><div class="num">${agg.runs_with_hits}</div><div class="lbl">有归因命中</div></div>
    ${Object.entries(agg.f_id_freq || {}).map(([f, c]) =>
      `<div class="card"><div class="num">${c.high + c.medium_low}</div>
       <div class="lbl">${esc(f)}（high ${c.high}）</div></div>`).join('')}
  </div>`;
  const hit = d.records.filter(r => r.hits.length).slice(0, 15);
  $('#at-records').innerHTML = hit.length ? `<table>
    <tr><th>run</th><th>F-ID</th><th>置信</th><th>证据</th><th>说明</th></tr>` +
    hit.flatMap(r => r.hits.map(h => `<tr><td class="muted">${esc(r.run_id)}</td>
      <td><span class="pill">${esc(h.f_id)}</span></td><td>${esc(h.confidence)}</td>
      <td class="muted">${(h.evidence_idx || []).join(',')}</td>
      <td class="muted">${esc(h.note)}</td></tr>`)).join('') + '</table>'
    : '<p class="muted">本批次无归因命中（全满分或证据不足）</p>';
}

// ---- 渠道健康 ----
async function loadChannel() {
  const bt = await api('/api/batches');
  const rows = [];
  for (const b of bt.batches.slice(-14).reverse()) {
    let h = null;
    try { h = await api('/api/gate/health?batch=' + encodeURIComponent(b.batch)); }
    catch (e) { h = null; }
    rows.push({ b, h });
  }
  $('#ch-table').innerHTML = `<table><tr><th>批次</th><th>中位 tps</th>
    <th>历史中位</th><th>判定</th></tr>` +
    rows.map(({ b, h }) => {
      if (!h) return `<tr><td>${esc(b.batch)}</td><td colspan="3" class="muted">—</td></tr>`;
      const bad = h.degraded;
      const med = h.batch_median_tps != null ? h.batch_median_tps.toFixed(1) : '—';
      const hist = h.historical_median_tps != null ? h.historical_median_tps.toFixed(1) : '—';
      return `<tr><td>${esc(b.batch)}</td>
        <td class="${bad ? 'cell-bad' : 'cell-good'}">${med}</td>
        <td class="muted">${hist}</td>
        <td>${bad ? '<span class="pill bad">降级窗口</span>' : '<span class="pill">健康</span>'}</td></tr>`;
    }).join('') + '</table>';
}

// ---- 启动 ----'''

t = t.replace('// ---- 启动 ----', JS, 1)
t = t.replace(
    "  await Promise.all([loadOverview(), loadMatrix(), loadTasks(), loadBatches(), loadVersions()]);",
    "  await Promise.all([loadOverview(), loadMatrix(), loadTasks(), loadBatches(),\n"
    "                     loadAttribution(), loadChannel(), loadVersions()]);")

p.write_text(t, encoding="utf-8")
print("前端两视图补丁完成")
