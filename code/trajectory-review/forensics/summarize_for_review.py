"""Evidence-derived review sheet. Flags are observations, not automatic model blame."""
import collections,gzip,hashlib,json,re
from pathlib import Path
A=Path(__file__).resolve().parents[1]
def txt(x):
    if isinstance(x,str):return x
    if isinstance(x,list):return '\n'.join(txt(v)for v in x)
    if isinstance(x,dict):
        if x.get('_display_limited'):return x['head']+'\n[DISPLAY LIMITED]\n'+x['tail']
        return txt(x.get('text',x.get('content',x.get('lines',''))))
    return ''
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def short(s,n=300):return s if len(s)<=n else s[:n//2]+' … '+s[-n//2:]
facts=[];sheets=[]
for p in sorted((A/'private').glob('*.json.gz')):
    d=json.loads(gzip.decompress(p.read_bytes()));m=d['meta'];calls=d['calls'];tools=d['tools'];bycall={c['call_id']:c for c in calls}
    groups=collections.defaultdict(list);errors=[];linkage=[];textual_errors=[];reads_image=[]
    for i,t in enumerate(tools,1):
        t['_index']=i;groups[(t.get('name'),sha(t.get('original_args')))].append(t)
        s=txt(t.get('result'));a=t.get('original_args')or{}
        if t.get('is_error'):errors.append(dict(index=i,call_id=t.get('call_id'),seq=t.get('start',{}).get('seq'),tool=t.get('name'),args=a,observation=s))
        if t.get('name')=='read'and isinstance(a,dict)and any(str(v).lower().endswith(('.png','.jpg','.jpeg','.webp'))for v in a.values()):reads_image.append(i)
        c=bycall.get(t.get('call_id'))or{};response=c.get('response')or{};content=response.get('content',[])if isinstance(response,dict)else[]
        block=next((b for b in content if b.get('type')=='toolCall'and b.get('id')==t.get('tool_call_id')),None)
        if block:
            ok=block.get('name')==t.get('name')and canonical(block.get('arguments'))==canonical(t.get('original_args'))
            linkage.append(dict(tool_index=i,exact=ok,call_id=t.get('call_id')))
        if t.get('name')=='bash'and isinstance(a,dict)and not t.get('is_error')and re.search(r'(?:error\[E\d+\]|error:|Traceback \(most recent call last\)|undefined reference)',s):
            textual_errors.append(dict(tool_index=i,call_id=t.get('call_id'),command=a.get('command'),observation=short(s,1400)))
    repeated=[]
    for (name,key),ts in groups.items():
        if len(ts)<3:continue
        t=ts[0];repeated.append(dict(tool=name,count=len(ts),errors=sum(bool(x.get('is_error'))for x in ts),first_index=t['_index'],last_index=ts[-1]['_index'],first_call=t.get('call_id'),last_call=ts[-1].get('call_id'),args=t.get('original_args'),first_observation=short(txt(t.get('result')),700)))
    repeated.sort(key=lambda x:(x['errors'],x['count']),reverse=True)
    last_calls=[];lengths=[];digitcollapse=[]
    for c in calls:
        r=c.get('response')or{};r=r if isinstance(r,dict)else{};u=r.get('usage')or{};blocks=r.get('content')or[]
        thought=''.join(txt(b.get('thinking',''))for b in blocks if b.get('type')=='thinking');body=''.join(txt(b)for b in blocks if b.get('type')=='text')
        item=dict(call_id=c['call_id'],source=c.get('source'),status=c.get('status'),stop=r.get('stopReason'),usage=u,thinking_characters=len(thought),body_characters=len(body),thinking_preview=short(thought,800),end_seq=(c.get('end')or{}).get('seq'))
        last_calls.append(item)
        if c.get('status')=='length'or r.get('stopReason')=='length':lengths.append(item)
        if re.search(r'(.)\1{255,}',thought):
            runs=[(m.group(0)[0],len(m.group(0)))for m in re.finditer(r'(.)\1{255,}',thought)];char,size=max(runs,key=lambda x:x[1]);digitcollapse.append(dict(call_id=c['call_id'],character=char,run_length=size,thinking_characters=len(thought)))
    ctrf=d.get('verifier',{}).get('ctrf.json',{}).get('text');tests=[]
    if ctrf:
        try:tests=json.loads(ctrf).get('results',{}).get('tests',[])
        except (json.JSONDecodeError,AttributeError):pass
    fails=[dict(name=t.get('name'),message=t.get('message'),trace=short(t.get('trace',''),1500))for t in tests if t.get('status')=='failed']
    f=dict(id=m['id'],label=m['label'],task=m['task'],trial=m['trial'],rewards=m.get('rewards'),exception=m.get('exception_type'),calls=len(calls),tools=len(tools),tool_errors=len(errors),
        first_visible_error=errors[0]if errors else None,first_five_errors=errors[:5],repeated_error_groups=repeated[:4],last_calls=last_calls[-3:],length_calls=lengths,digit_collapse=digitcollapse,
        tool_call_to_actual_start=dict(exact=sum(x['exact']for x in linkage),compared=len(linkage),mismatches=[x for x in linkage if not x['exact']],unlinked=len(tools)-len(linkage)),
        textual_compile_errors_with_shell_exit0=textual_errors,read_image_tool_indices=reads_image,failed_tests=fails,tests=tests,
        context_events=collections.Counter(e.get('data',{}).get('type')for e in d['timeline']if e['kind']=='context_event'),
        recorder_end=d['summary']['run_end_present'],artifact_integrity_errors=d.get('artifact_integrity_errors',[]),source_journal_sha256=m.get('journal_sha256'))
    facts.append(f)
    lines=[f"\n=== {m['label']} / {m['task']} / {m['id']} ===",f"reward={m.get('rewards')} exception={m.get('exception_type')} calls={len(calls)} tools={len(tools)} errors={len(errors)} end={f['recorder_end']} integrity_errors={len(f['artifact_integrity_errors'])}"]
    for t in errors[:2]:lines.append('FIRST_ERROR '+str(t['index'])+' '+t['tool']+' '+short(canonical(t['args']),300)+' => '+short(t['observation'],550))
    for g in repeated[:2]:lines.append('REPEAT '+str(g['count'])+' errors='+str(g['errors'])+' '+short(canonical(g['args']),260)+' => '+short(g['first_observation'],320))
    for c in last_calls[-2:]:lines.append('LAST_CALL '+canonical(c))
    for x in fails[:2]:lines.append('TEST_FAIL '+canonical(x))
    for i,t in list(enumerate(tools,1))[-2:]:lines.append('LAST_TOOL '+str(i)+' '+t.get('name','')+' '+short(canonical(t.get('original_args')),280)+' => '+short(txt(t.get('result')),400))
    sheets.append('\n'.join(lines))
(A/'private/TRAJECTORY_FACTS.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n')
(A/'private/REVIEW_SHEET.txt').write_text('\n'.join(sheets)+'\n')
print(json.dumps(dict(episodes=len(facts),models=dict(collections.Counter(f['label']for f in facts))),ensure_ascii=False))
