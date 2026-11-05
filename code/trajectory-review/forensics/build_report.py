"""Build an offline, read-only report from collected evidence. No remote actions."""
from __future__ import annotations
import base64
import collections
import csv
import datetime as dt
import gzip
import hashlib
import html
import json
from pathlib import Path
from case_notes import NOTES

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'private'
OUT = ROOT / 'report'
EPISODES = OUT / 'episodes'
EPISODES.mkdir(parents=True, exist_ok=True)
H = html.escape
def js(x): return json.dumps(x, ensure_ascii=False, separators=(',', ':'))
def sha(b): return hashlib.sha256(b).hexdigest()
def load(p): return json.loads(p.read_text())
def gzload(p): return json.loads(gzip.decompress(p.read_bytes()))
def short_task(m): return m['task'].split('/')[-1]
def reward(m): return (m.get('rewards') or {}).get('reward')
def stamp(s):
    if not s: return '未记录'
    return dt.datetime.fromisoformat(s.replace('Z', '+00:00')).astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec='seconds')

CSS = '''
:root{color-scheme:dark;--bg:#101620;--panel:#17212e;--line:#304156;--text:#e8eef7;--muted:#a6b5ca;--blue:#8fcfff;--warn:#ffcb79;--red:#ff9c9c;--green:#8ee5bd}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.7 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}a{color:var(--blue);text-underline-offset:3px}a:hover{color:#c3e9ff}header{padding:28px 30px 16px;border-bottom:1px solid var(--line)}main{max-width:1450px;margin:auto;padding:22px}h1{font-size:28px;line-height:1.35;margin:10px 0}h2{font-size:23px;margin:30px 0 12px}h3{font-size:18px;margin:0 0 10px}p{margin:8px 0 14px}.hint,small{color:var(--muted)}.panel{padding:18px;background:var(--panel);border:1px solid var(--line);border-radius:10px;margin-bottom:16px}.warn{color:var(--warn)}.bad{color:var(--red)}.ok{color:var(--green)}.mono,pre,code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}.mono{font-size:12px}.badge{display:inline-block;margin:2px 6px 2px 0;padding:2px 8px;border:1px solid var(--line);border-radius:5px;font-size:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}.metric{font-size:29px;font-weight:650}table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{color:var(--muted);position:sticky;top:0;background:var(--panel)}.scroll{overflow:auto}button,select,input{background:#1c2b3d;color:var(--text);border:1px solid #526a84;border-radius:5px;padding:7px 10px;font:inherit}button{cursor:pointer}button:hover{background:#2e435e}input{min-width:200px}select{max-width:100%}.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0}details{border-top:1px solid var(--line);padding:10px 0}summary{cursor:pointer;color:var(--blue);overflow-wrap:anywhere}pre{white-space:pre-wrap;word-break:break-word;max-height:65vh;overflow:auto;font-size:12px;line-height:1.6;background:#101823;padding:12px;border-radius:5px}li{margin:9px 0}.call-layout{display:grid;grid-template-columns:310px minmax(0,1fr);gap:18px}.call-sidebar{position:sticky;top:12px;align-self:start;max-height:92vh;display:flex;flex-direction:column}.call-sidebar input{width:100%;min-width:0}.call-list{overflow:auto;min-height:80px}.call-row{display:block;text-align:left;width:100%;font-size:12px;padding:10px;margin:4px 0}.call-row strong,.call-row small{display:block}.call-row.selected{border-color:#94d7ff;background:#294967}.call-row.has-error{border-left:3px solid var(--red)}#token-chart{width:100%;height:145px;cursor:crosshair;background:#101823}.inspector{min-width:0}.sticky-controls{position:sticky;top:0;background:var(--bg);z-index:3;padding:6px 0;border-bottom:1px solid var(--line)}.case-note{line-height:1.85}.numbers{font-variant-numeric:tabular-nums}.source-row{max-width:450px;overflow-wrap:anywhere}.pill{border-left:3px solid var(--blue);padding-left:12px}.compare-step{padding:10px 14px;border-left:3px solid var(--warn);margin:12px 0;background:#111e2b}.task-cell{min-width:165px}.muted{color:var(--muted)}@media(max-width:850px){.call-layout{display:block}.call-sidebar{position:relative;max-height:360px}header{padding:20px}main{padding:14px}h1{font-size:23px}}
'''
CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'"
def document(title, body, script=''):
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="'+H(CSP,quote=True)+'"><title>'+H(title)+'</title><style>'+CSS+'</style></head><body>'+body+('<script>'+script+'</script>' if script else '')+'</body></html>'
def link(uid, label, tool=None, prefix='episodes/'):
    return '<a href="'+prefix+uid+'.html'+('#tool-'+str(tool) if tool else '')+'">'+H(label)+'</a>'
def notes_html(n, uid=None, prefix='episodes/'):
    s='<div class="case-note"><h3>'+H(n['finding'])+'</h3><ol>'
    s+=''.join('<li>'+H(x)+'</li>' for x in n['chain'])+'</ol>'
    s+='<p class="warn">归因边界：'+H(n['attribution_limit'])+'</p>'
    s+='<p><strong>下一项可证伪对照（尚未执行）：</strong>'+H(n['falsification_test'])+'</p>'
    if uid and n['key_tools']:
        s+='<p>关键工具：'+' · '.join(link(uid,'T'+str(i),i,prefix) for i in n['key_tools'])+'</p>'
    return s+'</div>'

facts={x['id']:x for x in load(PRIVATE/'TRAJECTORY_FACTS.json')}
wire=load(PRIVATE/'BOUNDED_WIRE_EVENTS_R2.json')
source=load(PRIVATE/'SOURCE_AND_STATUS_SNAPSHOT_R1.json')
old_csv=ROOT.parent/'qwen35-calibforge-ab-20261027/followup-20261029/PRIMARY_PER_TASK.csv'
old_rows=list(csv.DictReader(old_csv.open()))
old_success=[r for r in old_rows if r['m0_reward'] and float(r['m0_reward'])==1]
assert len(old_success)==14
viewer=(ROOT/'scripts/viewer.js').read_text()
entries=[]

def classify(d):
    m=d['meta']; raw=d.get('verifier',{}); stdout=raw.get('test-stdout.txt',{}).get('text','')
    tests=[]
    if raw.get('ctrf.json',{}).get('text'):
        tests=json.loads(raw['ctrf.json']['text']).get('results',{}).get('tests',[])
    counter=[e for e in d['timeline'] if e['kind']=='context_event'
             and e.get('data',{}).get('type')=='input_token_count_failure'
             and e.get('data',{}).get('reason_code')=='counter_unavailable'
             and e.get('data',{}).get('generation_request_sent') is False]
    if m.get('exception_type')=='AgentSetupTimeoutError': execution='安装超时 / 零调用'
    elif counter and not d['calls']: execution='计数服务不可达 / 未发送生成'
    elif m.get('exception_type')=='AgentTimeoutError': execution='Agent 10800 秒超时'
    elif d['calls'] and (('RemoteProtocolError' in js(d['calls'][-1].get('response')))
                         or ('Server disconnected' in js(d['calls'][-1].get('response')))): execution='模型传输中断'
    elif '137' in (m.get('exception_message')or''): execution='退出 137 / 原因未定'
    elif any(c.get('source')=='agent' and (c.get('response')or{}).get('stopReason')=='length' for c in d['calls']): execution='主 Agent 输出 length'
    elif m.get('exception_type'): execution=m['exception_type']
    elif (d.get('run_end')or{}).get('status')=='completed': execution='Agent 正常闭合'
    else: execution='结束语义待核实'
    if not m.get('rewards'): scoring='无 Reward / UNKNOWN'
    elif 'uvx: command not found' in stdout and not tests: scoring='Verifier 未启动 / UNKNOWN'
    elif 'RemoteDisconnected' in stdout and 'download_attack_vectors' in stdout: scoring='评分下载失败 / 污染'
    elif tests: scoring='官方断言已执行'
    else: scoring='评分有效性待核实'
    if m['id'].startswith('56a53f1e'): scoring='官方给 1；题意假阳性'
    return execution,scoring

for p in sorted(PRIVATE.glob('*.json.gz')):
    d=gzload(p);m=d['meta'];uid=m['id'];n=NOTES[uid[:8]];f=facts[uid]
    execution,scoring=classify(d)
    # Source-side chunks are included only for the bounded calls explicitly fetched.
    these_wire=[w for w in wire if w['spec']['trial_id']==uid]
    if these_wire:d['bounded_wire_evidence']=these_wire
    raw=js(dict(trajectory=d,facts=f,notes=n)).encode()
    packed=base64.b64encode(gzip.compress(raw,compresslevel=6,mtime=0)).decode()
    title=m['label']+' · '+short_task(m)
    body='<header><a href="../index.html">← 逐轨迹总表</a> · <a href="../m0-comparison.html">两个 M0 翻零对照</a><h1>'+H(title)+'</h1>'
    body+='<p class="mono">Trial '+uid+' · '+H(m['trial'])+'</p>'
    body+='<span class="badge">原始 Reward '+str(reward(m))+'</span><span class="badge">'+H(scoring)+'</span><span class="badge">'+H(execution)+'</span><p id="load-status" class="hint">正在本地解压轨迹；不会联网或调用模型……</p></header><main>'
    body+='<section class="panel">'+notes_html(n,uid,'')+'</section>'
    body+='<section class="panel"><h3>Token 变化 · 点击横轴跳转 Call</h3><p class="hint">蓝色=input，紫色=output，橙点=length；这里是记录中的 usage，不冒充精确重算的 Token。Agent 与摘要均展示且分别标明。</p><svg id="token-chart" role="img" aria-label="各模型请求输入输出 Token 曲线"></svg></section>'
    body+='<div class="sticky-controls toolbar"><button id="prev">← 上一 Call</button><span id="position"></span><button id="next">下一 Call →</button><button id="first-error">首个工具报错</button><button id="last">最后 Call</button><span id="current-tools" class="hint"></span></div>'
    body+='<div class="call-layout"><aside class="panel call-sidebar"><h3>逐回合浏览</h3><input id="search" placeholder="搜索 Thinking / 参数 / Observation"><div class="toolbar"><select id="mode"><option value="all">所有 Call</option><option value="error">错误相关</option><option value="length">输出 length</option><option value="compaction">仅摘要</option></select><span id="matched" class="hint"></span></div><select id="tool-jump"><option value="0">直接跳至工具 T…</option></select><div id="call-list" class="call-list"></div></aside><article id="inspector" class="inspector"></article></div>'
    body+='<section class="panel"><h2>官方 Verifier / Reward 原始证据</h2><p class="hint">仅供受信任审阅；未放入任何 Agent 请求。原始分数未被修订。</p><div id="verifier-data"></div></section>'
    body+='<section class="panel"><h2>Compaction / 运行结束 / 工件异常</h2><div id="context-data"></div></section>'
    body+='<section class="panel"><h2>身份与可复核位置</h2><p class="hint">工具报错可能已经修复，不自动等于最终失败原因；缺少 run_end、坏 artifact、生成前证据缺失会单独显示。未对所有 Recorder 引用图作完整性认证。</p><button id="download-data">导出本页审阅 JSON</button><div id="identity-data"></div></section>'
    body+='</main><script id="packed-data" type="application/octet-stream">'+packed+'</script>'
    path=EPISODES/(uid+'.html');path.write_text(document(title,body,viewer))
    entries.append(dict(id=uid,label=m['label'],task=short_task(m),trial=m['trial'],reward=reward(m),calls=len(d['calls']),tools=len(d['tools']),
        execution=execution,scoring=scoring,recorder_run_end=bool(d.get('run_end')),artifact_integrity_errors=d.get('artifact_integrity_errors',[]),
        finding=n['finding'],notes=n,original_result_sha256=m['result_sha256'],original_journal_sha256=m.get('journal_sha256'),
        source=m['path'],source_started=m['started'],source_finished=m['finished'],journal_bytes=m.get('journal_bytes',0),
        derived_evidence_file=p.name,derived_evidence_sha256=sha(p.read_bytes()),html_file='episodes/'+path.name,html_sha256=sha(path.read_bytes())))
    print(js(dict(built=uid,label=m['label'],task=short_task(m))),flush=True)

byid={e['id']:e for e in entries}
models=['M0','NEW_M1_E3','NEW_M1_E5','NEW_M2_E1','NEW_M2_E3','NEW_M2_E5']
current=[e for e in entries if e['label']!='OLD_M0'];sft=[e for e in current if e['label']!='M0']
summary=dict(trajectory_records=len(entries),fully_reviewed_current_m0=2,fully_reviewed_current_sft=len(sft),old_m0_comparison_records=2,
    calls=sum(e['calls']for e in entries),tools=sum(e['tools']for e in entries),
    exact_parsed_call_to_tool_start=sum(f['tool_call_to_actual_start']['exact']for f in facts.values()),
    bounded_sse_calls=len(wire),
    compared_parsed_call_to_tool_start=sum(f['tool_call_to_actual_start']['compared']for f in facts.values()),
    zero_call_current_sft=sum(e['calls']==0 for e in sft),execution_counts=dict(collections.Counter(e['execution']for e in entries)),
    scoring_counts=dict(collections.Counter(e['scoring']for e in entries)),
    length_call_sources=dict(collections.Counter(c['source']for f in facts.values()for c in f['length_calls'])),
    snapshot_at=dt.datetime.fromtimestamp(source['at'],dt.timezone(dt.timedelta(hours=8))).isoformat(timespec='seconds'),
    native_status_rows=len(source['rows']))

# Decode bounded SSE tool fragments independently; do not guess missing tool identities.
wire_checks=[]
for w in wire:
    accum={}
    for event in w['events']:
        if event.get('type')!='call_chunk':continue
        chunk=event['data'].get('chunk')
        if not isinstance(chunk,str):continue
        try:o=json.loads(chunk)
        except json.JSONDecodeError:continue
        for ch in o.get('choices',[]):
            for t in ch.get('delta',{}).get('tool_calls') or []:
                index=t.get('index');a=accum.setdefault(index,dict(name='',id='',arguments=''))
                a['name']+=(t.get('function')or{}).get('name')or''
                a['id']+=t.get('id')or''
                a['arguments']+=(t.get('function')or{}).get('arguments')or''
    trajectory=gzload(PRIVATE/(w['spec']['trial_id']+'.json.gz'))
    c=next(c for c in trajectory['calls']if c['call_id']==w['spec']['call_id'])
    blocks=[b for b in c['response']['content']if b.get('type')=='toolCall']
    decoded=[]
    for index,a in accum.items():
        args=json.loads(a['arguments']);b=next(b for b in blocks if b['id']==a['id'])
        decoded.append(dict(index=index,**a,parsed_arguments=args,equals_harness=(args==b['arguments'] and a['name']==b['name'])))
    assert decoded and all(d['equals_harness']for d in decoded)
    wire_checks.append(dict(spec=w['spec'],range_sha256=w['range_sha256'],decoded=decoded))
(OUT/'SSE_TOOL_COMPARISON.json').write_text(json.dumps(wire_checks,ensure_ascii=False,indent=2)+'\n')

snapshot_rows=[]
for label,needle in [('M0','gpu2-m0'),('NEW_M1_E3','NOT_PRESENT_IN_THIS_DIRECTORY'),('NEW_M1_E5','gpu6-m1e5'),('NEW_M2_E1','gpu1-m2e1'),('NEW_M2_E3','gpu7-m2e3'),('NEW_M2_E5','gpu3-m2e5')]:
    rows=[r for r in source['rows']if needle in r['job']]
    snapshot_rows.append(dict(model=label,terminal_results=len(rows) if rows else None,raw_one=sum((r['rewards']or{}).get('reward')==1 for r in rows),raw_zero=sum((r['rewards']or{}).get('reward')==0 for r in rows),no_reward=sum(not r['rewards']for r in rows),fully_reviewed=sum(e['label']==label for e in entries)))

body='<header><span class="badge">只读轨迹审阅</span><span class="badge">离线 HTML · 无模型调用</span><h1>这几次失败，究竟坏在哪一步？</h1><p>两个 M0 翻零案例的新旧对照，以及其他 Checkpoint 已结束轨迹逐条分析。原始 Result、Reward、Recorder 均未改动。</p><p class="hint">状态快照：'+H(summary['snapshot_at'])+'；这不是当前实时队列状态。18 后来重启，本文仍只解释已收集的历史记录。</p></header><main>'
body+='<div class="grid"><section class="panel"><div class="metric">'+str(len(entries))+'</div><p>逐条审阅记录：2 条旧 M0 + 2 条新 M0 + '+str(len(sft))+' 条训练 Checkpoint 终态</p></section><section class="panel"><div class="metric">'+str(summary['zero_call_current_sft'])+'</div><p>训练 Checkpoint 零模型调用：5 次安装超时，5 次计数服务不可达。不是十次模型解题失败。</p></section><section class="panel"><div class="metric">'+f"{summary['tools']:,}"+'</div><p>工具执行逐项保留；已解析 Tool Call → Tool Start 参数全数一致。未因此证明 Serving Parser 前生成也一致。</p></section></div>'
body+='<section class="panel"><h2>先看两个 M0 翻零</h2><div class="grid"><div><h3>Portfolio：计算正确，官方测速未达标</h3><p>新轨迹公开自测约 1.5–1.6×；官方 N5000、6000 却只有约 1.127×、1.161×。函数正确性通过。计时差的机制尚不能归因硬件或模型。</p>'+link('5ee06990-e26b-4ad8-b519-556169844669','新 M0：看自测 T39',39)+' · '+link('2744cf85-9248-4491-9fa7-ec1ee552de80','旧 M0：看自测 T17',17)+'</div><div><h3>Polyglot：旧 1 分存在评分假阳性</h3><p>旧模型承认不是单文件 polyglot，却留下两个独立编译的程序；官方 g++ main.rs 失败后仍运行旧 cmain 并通过。新模型删除旧程序后编译失败，得 0。</p>'+link('56a53f1e-e143-4281-a6bd-e681846c9dc0','旧 M0：README T152',152)+' · '+link('93e70998-9446-4798-ba79-8798273b8325','新 M0：掩盖编译退出的 T193',193)+'</div></div><p><a href="m0-comparison.html">打开完整的新旧证据链、源码位置与可证伪解释 →</a></p></section>'
body+='<section class="panel"><h2>之前的共同 30 题跑完了吗？</h2><p>这个 Wheel6 目录的快照共有 84 个终态 Result。M0 为 30/30；其余四个已见 Checkpoint 各 12–14/30，不能说五组全完成。M1 E3 未在这个目录发现，未审计其他目录不作“完全没跑”结论。</p><div class="scroll"><table><thead><tr><th>模型</th><th>终态 Result / 30</th><th>原始 1</th><th>原始 0</th><th>缺 Reward</th><th>本次完整逐轨迹审阅</th></tr></thead><tbody>'
for r in snapshot_rows:
    body+='<tr><td>'+r['model']+'</td><td>'+('此目录未见' if r['terminal_results'] is None else str(r['terminal_results'])+'/30')+'</td><td>'+str(r['raw_one'])+'</td><td>'+str(r['raw_zero'])+'</td><td>'+str(r['no_reward'])+'</td><td>'+str(r['fully_reviewed'])+'</td></tr>'
body+='</tbody></table></div><p class="warn">“原始 0”不是“评分有效的模型零分”。下方逐条列出测试未启动、服务中断、零生成等污染，不能按上表直接比较能力。</p><p>有超时设置：本次细审记录中 27 条是 AgentTimeoutError，配置研究时限为 10800 秒。不是一题无限跑几天；每题三小时、排队、安装和 Verifier 故障会叠加拖长总时长。这里只解释这些历史记录，不把队列当下状态伪装成已恢复。</p></section>'
body+='<section class="panel"><h2>旧 M0 成功清单：实际 14 题，本目录只覆盖其中 5 题</h2><p>旧 CSV 确认为 14 条原始 1 分。重合五题中，新 M0 的 cobol、constraints 仍为原始 1；code-from-image 是 VerifierTimeout / 无 Reward，不能说变 0；polyglot 与 portfolio 的两个 0 已细审。另九题在此次目录未见，不能说已跑完。</p><div class="scroll"><table><thead><tr><th>旧成功任务</th><th>旧 M0</th><th>本次目录新 M0</th><th>证据范围</th></tr></thead><tbody>'
retention=[]
for old in old_success:
    r=next((r for r in source['rows']if 'gpu2-m0' in r['job']and r['task']==old['task_id']),None)
    uid=r['id']if r else None
    label='原始 '+str((r['rewards']or{}).get('reward'))+(' · '+str(r['exception'])if r['exception']else'')if r else'此目录未见'
    evidence='完整轨迹已细审'if uid in byid else ('仅 Result 快照，尚未作轨迹定因'if r else'没有本次执行证据')
    body+='<tr><td>'+H(old['task_id'].split('/')[-1])+'</td><td>原始 1'+('；假阳性路径'if old['task_id'].endswith('/polyglot-rust-c')else'')+'</td><td>'+(link(uid,label)if uid in byid else H(label))+'</td><td>'+evidence+'</td></tr>'
    retention.append(dict(task=old['task_id'],old_m0_raw_reward=1,old_trial_id=old['m0_trial_id'],new_m0_status=label,new_m0_trial_id=uid,review_scope=evidence))
body+='</tbody></table></div><p class="mono">旧 CSV SHA256 '+sha(old_csv.read_bytes())+'</p><details><summary>全部 30 个 M0 原始 Result（其中 28 条尚未逐轨迹审阅）</summary><table><tr><th>任务</th><th>原始 Reward</th><th>原始异常</th></tr>'
for r in source['rows']:
    if 'gpu2-m0' in r['job']:
        body+='<tr><td>'+H(r['task'].split('/')[-1])+'</td><td>'+str((r['rewards']or{}).get('reward'))+'</td><td>'+H(str(r['exception']))+'</td></tr>'
body+='</table></details></section>'
body+='<section class="panel"><h2>逐任务 × Checkpoint 覆盖</h2><p class="hint">每格链接到实际轨迹。— 表示本次没有收集该格，绝不补造结果。M0 其他 28 题只有 Result 快照，未做详细轨迹审计。</p><div class="scroll"><table><thead><tr><th>任务</th>'+''.join('<th>'+x+'</th>'for x in models)+'</tr></thead><tbody>'
for task in sorted(set(e['task']for e in current)):
    body+='<tr><td class="task-cell">'+H(task)+'</td>'
    for model in models:
        e=next((e for e in current if e['task']==task and e['label']==model),None)
        body+='<td>'+ (link(e['id'],f"原始 {e['reward']} · {e['calls']} Calls")+'<br><small>'+H(e['execution'])+'<br>'+H(e['scoring'])+'</small>' if e else '—')+'</td>'
    body+='</tr>'
body+='</tbody></table></div></section>'
body+='<section class="panel"><h2>每条轨迹的具体原因</h2><div class="toolbar"><input id="case-search" placeholder="按任务 / 模型 / 错误搜索"><select id="model-filter"><option value="">所有模型</option>'+''.join('<option>'+x+'</option>'for x in ['OLD_M0']+models)+'</select><span id="case-count" class="hint"></span></div><div class="scroll"><table id="case-table"><thead><tr><th>模型 / Task</th><th>原始分数与评分链</th><th>执行 / Recorder 收尾</th><th>本轨迹结论</th></tr></thead><tbody>'
for e in sorted(entries,key=lambda e:(e['task'],e['label'])):
    body+='<tr data-model="'+e['label']+'"><td>'+H(e['label'])+'<br>'+link(e['id'],e['task'])+'<br><small>'+e['id'][:8]+'</small></td><td>Reward '+str(e['reward'])+'<br>'+H(e['scoring'])+'</td><td>'+H(e['execution'])+'<br><small>'+str(e['calls'])+' Calls / '+str(e['tools'])+' Tools<br>run_end '+('有'if e['recorder_run_end']else'缺失')+ (' · 工件损坏'if e['artifact_integrity_errors']else'')+'</small></td><td class="source-row">'+H(e['finding'])+'</td></tr>'
body+='</tbody></table></div></section>'
body+='<section class="panel"><h2>怎么查看一条轨迹</h2><ol><li>点任务名，先看该条结论和归因边界。</li><li>点关键 T 编号或 Token 曲线，逐回合查看 Thinking、Tool Call、实际参数、原始/格式化 Observation，再看下一请求的真实消息尾部。</li><li>页末查看官方 Verifier 全日志、Compaction、原始路径、Call ID、seq、byte offset 和 SHA。超长 Thinking 默认折叠，原文仍保留。</li></ol><p>页面离线自包含，无外部脚本或网络请求。需近期 Chrome / Edge / Firefox。<a href="TRAJECTORY_AUDIT.md">文字审阅报告</a> · <a href="AUDIT_MANIFEST.json">机器可读 Manifest</a> · <a href="SSE_TOOL_COMPARISON.json">四次原始 SSE 对照</a> · <a href="SHA256SUMS.txt">交付文件 SHA</a></p></section>'
body+='<section class="panel"><h2>已确认与尚不能归因</h2><p>CONFIRMED：旧 polyglot 陈旧二进制假阳性；新 portfolio 性能断言失败；五次生成前 counter 失败；五次安装超时；八次 UV bootstrap 未运行测试；一条 Recorder 有坏工件；部分服务响应同时间中断。</p><p>INFERRED：若干 Checkpoint 存在较弱的错误恢复、交付推进和 Thinking 控制。已有短输入也达到 81920 Thinking，说明不能把全部现象归于长上下文。</p><p>UNVERIFIED：SFT 数据、训练目标、权重还是 SGLang 解码造成这些行为的主因。历史 Parser 前 Token 不完整；本次不新跑推理，不用猜测填补这段证据。</p></section></main>'
index_js="""const q=document.getElementById('case-search'),m=document.getElementById('model-filter');function f(){let n=0;for(const r of document.querySelectorAll('#case-table tbody tr')){const show=(!m.value||r.dataset.model===m.value)&&r.textContent.toLowerCase().includes(q.value.toLowerCase());r.hidden=!show;if(show)n++;}document.getElementById('case-count').textContent=n+' 条';}q.oninput=f;m.onchange=f;f();"""
(OUT/'index.html').write_text(document('逐轨迹错误定位 · M0 / M1 / M2',body,index_js))

# Static comparison remains readable even without JavaScript.
body='<header><a href="index.html">← 全部逐轨迹总表</a><h1>两个 M0 的 1 → 0：证据分别说明什么</h1><p>原始奖励完全保留；只解释分数翻转，不把不同协议、不同产物当作严格权重因果实验。</p></header><main>'
for task,old,new in [('polyglot-rust-c','56a53f1e-e143-4281-a6bd-e681846c9dc0','93e70998-9446-4798-ba79-8798273b8325'),('portfolio-optimization','2744cf85-9248-4491-9fa7-ec1ee552de80','5ee06990-e26b-4ad8-b519-556169844669')]:
    body+='<section class="panel"><h2>'+task+'</h2><div class="grid"><article>'+notes_html(NOTES[old[:8]],old)+'</article><article>'+notes_html(NOTES[new[:8]],new)+'</article></div></section>'
    for uid in [old,new]:
        d=gzload(PRIVATE/(uid+'.json.gz'));stdout=d['verifier'].get('test-stdout.txt',{})
        body+='<details class="panel"><summary>'+H(d['meta']['label'])+' · 官方 Verifier 全日志 · SHA '+H(stdout.get('sha256','缺失'))+'</summary><pre>'+H(stdout.get('text','缺失'))+'</pre></details>'
    src=next(s for s in source['sources']if s['task'].endswith('/'+task)and s['path'].endswith('test_outputs.py'))
    numbered='\n'.join(f'{i:4d}  {line}'for i,line in enumerate(src['text'].splitlines(),1))
    body+='<details class="panel"><summary>只读官方测试源码（受信任审阅） · SHA '+src['sha256']+'</summary><p class="mono">'+H(src['path'])+'</p><pre>'+H(numbered)+'</pre></details>'
    if task.startswith('polyglot'):
        body+='<div class="panel"><h3>逐层定位</h3><div class="compare-step">旧：两个独立源码编译 → 已有 main/cmain → 官方用 main.rs 编译 C++ 失败但未检查 → 继续运行旧 cmain → 原始 Reward 1。</div><div class="compare-step">新：真实 SSE 发出 rm -f main cmain + 编译管道 → Harness 原样执行 → head / echo 使 shell 0 掩盖编译器失败 → 最终无 main → 官方 Reward 0。</div><p>这已足以否定“这组翻转本身证明模型比旧 M0 变差”。新模型确实没有完成该任务，但旧分数并非可信的题意成功证据。</p></div>'
    else:
        body+='<div class="panel"><h3>已定位的直接失败与未定位的测速落差</h3><p>官方 N5000：1.1273312839721432×；N6000：1.1609903748559458×。四个其他 pytest item 通过。公开 benchmark 只测 5000/8000，不能保证 6000；但同一 5000 的自测/官方计时也不一致，原因仍需固定代码与运行条件的独立测量。</p><p>两个实现不同；不能直接把时间差归为机器坏，也不能从基线翻零归因 SFT。当前没有修改测试、重跑测速或偷偷择优。</p></div>'
body+='<section class="panel"><h2>旧 / 新协议并不完全相同</h2><div class="scroll"><table><tr><th>字段</th><th>旧 M0</th><th>当前 M0</th></tr><tr><td>工具 / Finish</td><td>10 工具 / 关闭</td><td>11 工具 / 开启</td></tr><tr><td>Wheel SHA</td><td>f84f810e8a61545d685fb6722593886a0c88cc829b2ab9ca7c3476fe11e1209e</td><td>8c84a8659c136b027c36c48a7100d956fdb58c873b347ef6b240b561cc75e85d</td></tr><tr><td>温度 / top_p</td><td>1 / 0.95</td><td>1 / 0.95</td></tr><tr><td>presence / top_k / min_p 等</td><td>旧请求未显式发送；不猜默认值</td><td>1.5 / 20 / 0 等显式字段</td></tr><tr><td>Agent 时限</td><td>沿任务原值，未设研究覆盖</td><td>10800 秒研究时限</td></tr></table></div><p>Task checksum 相同不等于运行分布相同；未重新证明旧权重文件 SHA 和输入 Token 完全一致。</p></section></main>'
(OUT/'m0-comparison.html').write_text(document('M0 两个翻零案例 · 新旧证据对照',body))

manifest=dict(schema='read-only-trajectory-audit-v1',summary=summary,scope='Two old/new M0 pairs; every closed SFT trajectory available in the inspected Wheel6 directory at collection. Not a whole-project result aggregation.',
    status_snapshot_sha256=sha((PRIVATE/'SOURCE_AND_STATUS_SNAPSHOT_R1.json').read_bytes()),status_snapshot=snapshot_rows,
    old_m0_success_source=dict(path=str(old_csv),sha256=sha(old_csv.read_bytes()),count=14),old_success_retention=retention,
    raw_evidence_preserved=True,native_scores_modified=False,new_model_requests_sent=0,entries=entries)
(OUT/'AUDIT_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')

md=[f'只读逐轨迹审阅：M0 / NEW-M1 / NEW-M2\n\n快照：{summary["snapshot_at"]}。\n',
    '18 已由用户告知重启；此前管理方提示的 10.20.20.53 与 18 主机名解析一致，但本次未取得重启前逐进程 FD 证据，不能归因到本项目。此次审阅读 17 SSD、写本地 ext4；不继续存储排查。\n',
    f'本次详细收集 {len(entries)} 条：2 条旧 M0、2 条新 M0、{len(sft)} 条训练 Checkpoint 终态。检查目录内共有 {len(source["rows"])} 个 Result；M0 30/30、其余四个各12–14/30。M1 E3 在此目录未见，不推断其他目录。\n',
    '原生 Result 存在不等于官方有效评分；原始奖励未修改，评分污染单独标注。未启动新推理、训练或评测，不修改主总控。\n',
    f'共 {summary["calls"]:,} Calls、{summary["tools"]:,} Tools。已解析 Tool Call → Tool Start 共 {summary["compared_parsed_call_to_tool_start"]:,} 对，参数/名称全部相同；该一致性不覆盖 Serving Parser 之前。四次额外原始 SSE 对照也与 Harness 结果一致。\n',
    'M0 的两个关键结论\n\n1. portfolio：计算正确，官方性能 5000/6000 分别1.12733×、1.16099×低于1.2×；公开自测更快，差异机制尚未确认。\n2. polyglot：旧模型明确承认不是单文件方案；官方编译失败却运行陈旧二进制获得1分。新模型删除二进制后未编译成功得0。这一对不是能力退化的可靠证据。\n',
    '旧成功 CSV 实际为14题。本目录重合5题：cobol、constraints 的新M0原始仍为1；code-from-image为VerifierTimeout、缺Reward，不能算0；另两个翻0详见本审阅。其余9题本目录未见。\n',
    '本次记录中10条训练 Checkpoint 零调用：5安装超时、5生成前计数服务不可达；8条 Verifier UV bootstrap 失败；另1条评分时下载攻击数据失败；1条 Recorder有损坏引用。上述分类可与退出异常重叠，不能相加冒充独立失败总数。\n',
    '27条记录为10800秒Agent超时；19次length分别为10次主Agent和9次辅助摘要。单题没有无限运行几天的证据；队列和工程故障拖长了整体运行。\n',
    '可视化：打开 index.html。每条有逐回合 Thinking、工具参数、原始/格式化 Observation、下一请求消息尾部、Compaction、Verifier 和 SHA/位置。完整 Provider Payload 只为两个 M0 案例保存；其余提供尾6条+完整请求哈希。原始 SSE 仅额外提取四次，不能冒充全部原始生成 Token。\n',
    '每条轨迹\n']
for e in sorted(entries,key=lambda e:(e['task'],e['label'])):
    n=e['notes'];md+=['\n### '+e['label']+' / '+e['task']+'\n',
        f'Trial `{e["id"]}`；原始 reward={e["reward"]}；{e["scoring"]}；{e["execution"]}。\n',n['finding']+'\n']
    md+=['- '+x+'\n'for x in n['chain']]
    md+=['\n归因边界：'+n['attribution_limit']+'\n','\n可证伪对照（未执行）：'+n['falsification_test']+'\n',
        '\n[逐回合查看]('+e['html_file']+')。原始路径 `'+e['source']+'`；Result SHA `'+e['original_result_sha256']+'`；Recorder SHA `'+str(e['original_journal_sha256'])+'`。\n']
(OUT/'TRAJECTORY_AUDIT.md').write_text('\n'.join(md))

with (OUT/'TRAJECTORY_INDEX.csv').open('w') as f:
    fields=['id','label','task','reward','calls','tools','execution','scoring','recorder_run_end','finding','source','original_result_sha256','original_journal_sha256','html_file']
    w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(entries)
inventory=[]
for p in sorted(OUT.rglob('*')):
    if p.is_file() and p.name!='SHA256SUMS.txt': inventory.append(sha(p.read_bytes())+'  '+str(p.relative_to(OUT)))
(OUT/'SHA256SUMS.txt').write_text('\n'.join(inventory)+'\n')
print(js(summary))
