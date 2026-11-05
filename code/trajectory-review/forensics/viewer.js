'use strict';
// Read-only viewer. Student text is rendered exclusively through textContent.
let D, F, N, current = 0, filtered = [], toolIndices, toolCallMap;
const $ = id => document.getElementById(id);
const text = v => typeof v === 'string' ? v : JSON.stringify(v, null, 2);
function node(tag, cls, value) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (value !== undefined) e.textContent = text(value);
  return e;
}
function detail(parent, title, value, open = false) {
  const el = node('details'); el.open = open;
  el.append(node('summary', '', title));
  const pre = node('pre', '', value === undefined ? '未保存此字段' : value);
  el.append(pre); parent.append(el); return el;
}
function section(title, parent = $('inspector')) {
  const el = node('section', 'panel'); el.append(node('h3', '', title)); parent.append(el); return el;
}
function shown(x) {
  if (typeof x === 'string') return x;
  if (Array.isArray(x)) return x.map(shown).join('\n');
  if (x && typeof x === 'object') {
    if (x._display_limited) return `${x.head}\n[显示副本有长度限制；原始字符数 ${x.original_characters}；SHA ${x.original_text_sha256}]\n${x.tail}`;
    if (x._unreadable_artifact) return '[原始工件损坏/缺失，此处不补造内容]\n' + text(x._unreadable_artifact);
    if (x.text !== undefined) return shown(x.text);
    if (x.content !== undefined) return shown(x.content);
  }
  return x == null ? '' : text(x);
}
function evidence(v) {
  if (!v) return '未记录';
  return `seq=${v.seq} · byte offset=${v.offset} · bytes=${v.bytes}\nSHA256=${v.event_sha256}\n${new Date(v.timestamp * 1000).toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai', hour12: false})} +08:00`;
}
function preview(c) {
  const ts = toolCallMap.get(c.call_id) || [];
  if (ts.length) return ts.map(t => `${t.name} ${text(t.original_args)}`).join(' · ').replace(/\s+/g, ' ').slice(0, 125);
  const r = c.response || {};
  return shown(r.errorMessage || c.error || r.content || c.status).replace(/\s+/g, ' ').slice(0, 125);
}
function status(c) { return c.response?.stopReason || c.status || '无结束记录'; }
function showCall(i, updateHash = true) {
  if (!D.calls.length) return;
  current = Math.max(0, Math.min(D.calls.length - 1, i));
  const c = D.calls[current], r = c.response || {};
  $('inspector').replaceChildren();
  $('position').textContent = `Call ${current + 1} / ${D.calls.length}`;
  if (updateHash) history.replaceState(null, '', '#call-' + (current + 1));
  document.querySelectorAll('.call-row').forEach(el => el.classList.toggle('selected', Number(el.dataset.index) === current));
  const head = section(`Call ${current + 1} · ${c.source || '未知用途'} · ${status(c)}`);
  head.append(node('p', 'mono', c.call_id));
  head.append(node('p', '', `历史消息 ${c.history_message_count ?? '未知'} · input ${r.usage?.input ?? '?'} · output ${r.usage?.output ?? '?'} · reasoning ${r.usage?.reasoning ?? '?'} Token`));
  if (r.errorMessage || r.errorDetails || c.error) detail(head, '错误内容（不将传输异常改称模型完成）', {error: c.error, errorMessage: r.errorMessage, errorDetails: r.errorDetails}, true);
  detail(head, '原始事件身份与位置', {start: c.start, payload: c.payload_evidence, end: c.end, provider_payload_sha256: c.provider_payload_sha256, tool_schema_sha256: c.tool_schema_sha256});
  const req = section('输入 · 教师/Agent 当时请求证据');
  req.append(node('p', 'hint', 'Provider Payload 是请求消息证据，不是 Serving 最终 Token IDs。全历史只在两个 M0 对照案例中保留；其余页面提供实际最后六条消息及完整 Payload 哈希，完整原件仍在远端 Recorder。'));
  detail(req, '请求参数', c.payload_options || c.request_options || {});
  detail(req, '请求末六条真实消息（可能包含预算化 Observation）', c.payload_tail || []);
  if (c.full_provider_payload) detail(req, '本案例保存的完整 Provider Payload', c.full_provider_payload);
  const assistant = section('输出 · Harness 保存的 Assistant（已过 Serving Parser）');
  const blocks = Array.isArray(r.content) ? r.content : [];
  if (!blocks.length) assistant.append(node('p', 'warn', '没有可读取的 Assistant 内容。不能据此伪造一次模型动作。'));
  blocks.forEach((b, n) => {
    if (b.type === 'thinking') detail(assistant, `Thinking ${n + 1} · ${shown(b.thinking).length.toLocaleString()} 字符`, shown(b.thinking));
    else if (b.type === 'toolCall') detail(assistant, `Tool Call · ${b.name || '[缺名称]'} · ${b.id || '[缺 ID]'}`, b, true);
    else detail(assistant, `正文/其他 · ${b.type || '未知'}`, b.type === 'text' ? shown(b) : b, shown(b).length < 1200);
  });
  detail(assistant, '完整保存的响应对象（含 stopReason / usage）', r);
  const ts = toolCallMap.get(c.call_id) || [];
  ts.forEach(t => {
    const ti = toolIndices.get(t.execution_id);
    const el = section(`工具 T${ti} · ${t.name} · ${t.is_error ? '工具报告错误' : t.status || '未知状态'}`);
    el.id = 't-' + ti;
    el.append(node('p', 'mono', `tool_call_id=${t.tool_call_id}\nexecution_id=${t.execution_id}`));
    detail(el, '请求参数 → 实际执行参数', {original_args: t.original_args, actual_args: t.actual_args}, true);
    detail(el, '实际返回给 Harness 的工具 Observation（原文）', t.result, true);
    detail(el, '预算前 / 格式化前原始结果（若有保存）', t.raw_result);
    detail(el, 'Tool Start / Prepared / Raw / End 的 SHA 与位置', {start: t.start, prepared: t.tool_prepared_evidence, raw: t.tool_raw_evidence, end: t.tool_end_evidence});
    if (current + 1 < D.calls.length) {
      const b = node('button', '', '查看下一次请求中的 Observation / 历史');
      b.onclick = () => showCall(current + 1); el.append(b);
    }
  });
  if (!ts.length) assistant.append(node('p', 'hint', '该 Call 未关联工具执行：可能是正文、摘要、请求失败或输出 length。'));
  const wire = (D.bounded_wire_evidence || []).find(w => w.spec.call_id === c.call_id);
  if (wire) {
    const el = section('有界原始 SSE 对照（此 Call 额外采集）');
    el.append(node('p', 'hint', '这里的 call_chunk 是 Serving 发出的 OpenAI SSE 内容，已经过 SGLang Parser；不是 Parser 前原始生成 Token。'));
    detail(el, 'SSE 分片、Harness 事件与范围 SHA', wire, true);
  }
  $('current-tools').textContent = ts.length ? ts.map(t => 'T' + toolIndices.get(t.execution_id)).join('、') : '此 Call 无工具';
}
function filterCalls() {
  const q = $('search').value.trim().toLowerCase(), mode = $('mode').value;
  const rows = [];
  for (let i = 0; i < D.calls.length; i++) {
    const c = D.calls[i], ts = toolCallMap.get(c.call_id) || [];
    if (mode === 'error' && !(ts.some(t => t.is_error) || c.error || c.response?.errorMessage || ['error', 'aborted'].includes(status(c)))) continue;
    if (mode === 'length' && status(c) !== 'length') continue;
    if (mode === 'compaction' && c.source !== 'compaction') continue;
    if (q) {
      const hay = JSON.stringify([c.call_id, c.response, c.payload_tail, ts]).toLowerCase();
      if (!hay.includes(q)) continue;
    }
    rows.push(i);
  }
  filtered = rows; $('call-list').replaceChildren();
  rows.forEach(i => {
    const c = D.calls[i], ts = toolCallMap.get(c.call_id) || [];
    const btn = node('button', 'call-row' + (i === current ? ' selected' : ''));
    btn.dataset.index = i;
    btn.append(node('strong', '', `${i + 1} · ${c.source || '?'} · ${status(c)}`));
    btn.append(node('small', '', preview(c)));
    if (ts.some(t => t.is_error)) btn.classList.add('has-error');
    btn.onclick = () => showCall(i); $('call-list').append(btn);
  });
  $('matched').textContent = `${rows.length} / ${D.calls.length} Calls`;
}
function gotoTool(n) {
  const t = D.tools[n - 1]; if (!t) return;
  const i = D.calls.findIndex(c => c.call_id === t.call_id); if (i < 0) return;
  showCall(i, false); history.replaceState(null, '', '#tool-' + n);
  $('t-' + n)?.scrollIntoView({block: 'start', behavior: 'smooth'});
}
function plot() {
  const svg = $('token-chart'), ns = 'http://www.w3.org/2000/svg', w = 1000, h = 145;
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  const max = Math.max(1, ...D.calls.map(c => Math.max(c.response?.usage?.input || 0, c.response?.usage?.output || 0)));
  for (const [key, col] of [['input', '#3fa8df'], ['output', '#d092ff']]) {
    const p = document.createElementNS(ns, 'polyline');
    p.setAttribute('points', D.calls.map((c, i) => `${30 + i * 950 / Math.max(1, D.calls.length - 1)},${125 - (c.response?.usage?.[key] || 0) / max * 108}`).join(' '));
    p.setAttribute('fill', 'none'); p.setAttribute('stroke', col); p.setAttribute('stroke-width', '1.5'); svg.append(p);
  }
  [0, max].forEach((v, i) => { const e = document.createElementNS(ns, 'text'); e.setAttribute('x', '4'); e.setAttribute('y', i ? '12' : '141'); e.setAttribute('fill', '#9ba8bd'); e.setAttribute('font-size', '10'); e.textContent = Math.round(v).toLocaleString(); svg.append(e); });
  D.calls.forEach((c, i) => {
    if (status(c) !== 'length') return;
    const e = document.createElementNS(ns, 'circle'); e.setAttribute('cx', 30 + i * 950 / Math.max(1, D.calls.length - 1)); e.setAttribute('cy', 125 - (c.response?.usage?.output || 0) / max * 108); e.setAttribute('r', '4'); e.setAttribute('fill', '#ffb451'); svg.append(e);
  });
  svg.onclick = ev => { const r = svg.getBoundingClientRect(); showCall(Math.round(Math.max(0, Math.min(1, ((ev.clientX - r.left) / r.width * 1000 - 30) / 950)) * (D.calls.length - 1))); };
}
function showVerifier() {
  const el = $('verifier-data');
  const tests = F.tests || [];
  if (tests.length) {
    const table = node('table');
    tests.forEach(t => { const tr = node('tr'); tr.append(node('td', t.status === 'passed' ? 'ok' : 'bad', t.status), node('td', '', t.name)); table.append(tr); }); el.append(table);
    el.append(node('p', 'hint', '上表是 CTRF 行，不一定等于 pytest 参数化 item 数。精确运行情况以 stdout 为准。'));
  } else el.append(node('p', 'warn', '没有 CTRF 测试明细；结合下方 bootstrap 和 Result 判断，不能自动视为模型零分。'));
  for (const [name, v] of Object.entries(D.verifier || {})) detail(el, `${name} · ${v.bytes} bytes · SHA ${v.sha256}`, v.text ?? '[未内嵌全文；原件保留]', name === 'test-stdout.txt' && !tests.length);
}
function contextEvents() {
  const el = $('context-data');
  for (const e of D.timeline.filter(e => e.kind === 'context_event')) {
    detail(el, `${e.data?.type || '未知事件'} · seq ${e.evidence?.seq}`, {evidence: e.evidence, event: e.data});
  }
  if (!el.children.length) el.append(node('p', 'hint', '此导出中没有 Compaction/异常等上下文事件（频繁 input_token_count 成功事件未展开）。'));
  detail(el, 'run_start / run_end（run_end 存在不等于正常成功）', {run_start: D.run_start, run_end: D.run_end});
  detail(el, '工件完整性错误', D.artifact_integrity_errors || [], (D.artifact_integrity_errors || []).length > 0);
}
async function boot() {
  try {
    if (!globalThis.DecompressionStream) throw new Error('浏览器不支持 DecompressionStream，请用近期 Chrome/Edge/Firefox 打开。');
    const packed = atob($('packed-data').textContent.trim());
    const bytes = Uint8Array.from(packed, x => x.charCodeAt(0));
    const ds = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    const wrap = JSON.parse(await new Response(ds).text()); D = wrap.trajectory; F = wrap.facts; N = wrap.notes;
    toolIndices = new Map(D.tools.map((t, i) => [t.execution_id, i + 1])); toolCallMap = new Map();
    D.tools.forEach(t => { if (!toolCallMap.has(t.call_id)) toolCallMap.set(t.call_id, []); toolCallMap.get(t.call_id).push(t); });
    $('load-status').textContent = `载入 ${D.calls.length} Calls、${D.tools.length} 工具；所有浏览操作均在本地进行。`;
    plot(); showVerifier(); contextEvents();
    detail($('identity-data'), 'Task / Trial / Wheel / Result / Recorder 与运行协议', D.meta);
    detail($('identity-data'), '派生审阅事实（不改原始评分）', F);
    detail($('identity-data'), '导出范围与显示限制', {scope: D.scope, redaction_patterns: D.redaction_patterns, summary: D.summary});
    const jq = $('tool-jump'); D.tools.forEach((t, i) => { const o = node('option', '', `T${i + 1} · ${t.name}${t.is_error ? ' · 错误' : ''}`); o.value = i + 1; jq.append(o); });
    jq.onchange = () => gotoTool(Number(jq.value));
    $('prev').onclick = () => showCall(current - 1); $('next').onclick = () => showCall(current + 1);
    $('last').onclick = () => showCall(D.calls.length - 1);
    $('first-error').onclick = () => { const n = F.first_visible_error?.index; if (n) gotoTool(n); };
    $('mode').onchange = filterCalls;
    let timer; $('search').oninput = () => { clearTimeout(timer); timer = setTimeout(filterCalls, 300); };
    $('download-data').onclick = () => { const a = node('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(wrap, null, 2)], {type: 'application/json'})); a.download = D.meta.id + '-review.json'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); };
    filterCalls();
    const hash = location.hash, tm = hash.match(/^#tool-(\d+)$/), cm = hash.match(/^#call-(\d+)$/);
    if (tm) gotoTool(Number(tm[1])); else if (D.calls.length) showCall(cm ? Number(cm[1]) - 1 : 0);
    else $('inspector').append(node('div', 'panel warn', '零模型调用：请看上下文异常、安装时限和官方评分日志。不存在可供展示的模型动作。'));
    window.addEventListener('hashchange', () => { const m = location.hash.match(/^#tool-(\d+)$/); if (m) gotoTool(Number(m[1])); });
  } catch (e) { $('load-status').textContent = '载入失败：' + e.message; $('load-status').className = 'bad'; console.error(e); }
}
boot();
