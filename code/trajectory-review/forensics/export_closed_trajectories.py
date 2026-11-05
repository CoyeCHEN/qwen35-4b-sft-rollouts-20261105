"""Read-only remote extraction, JSON-gzip to stdout; never executes a task/tool."""
import argparse,base64,collections,gzip,hashlib,json,re,sys,time
from pathlib import Path

def digest(b):return hashlib.sha256(b).hexdigest()
def encoded(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def loadValue(value, artifactDirectory):
    # Exact pure resolver inspected in the frozen native Wheel6.
    if isinstance(value,dict):
        if set(value)=={'$artifact','encoding','size'}:
            ident=value['$artifact']
            if len(ident)!=64 or any(c not in '0123456789abcdef'for c in ident):raise ValueError('Invalid artifact hash')
            data=(Path(artifactDirectory)/ident).read_bytes()
            if digest(data)!=ident or len(data)!=value['size']:raise ValueError('Corrupt artifact')
            return data.decode('utf-8')if value.get('encoding')=='utf-8'else {'binary_bytes':len(data),'sha256':ident}
        return{k:loadValue(v,artifactDirectory)for k,v in value.items()}
    if isinstance(value,list):return[loadValue(v,artifactDirectory)for v in value]
    return value

redactions=collections.Counter()
def safe(x):
    if isinstance(x,dict):
        return{k:('[REDACTED]'if any(s in k.lower()for s in ['api_key','apikey','authorization','password','subscription_url'])else safe(v))for k,v in x.items()}
    if isinstance(x,list):return[safe(v)for v in x]
    if isinstance(x,str):
        for pattern in [r'\bsk-[A-Za-z0-9_-]{12,}',r'(?i)Bearer\s+[A-Za-z0-9._~+/-]{10,}',r'(?im)(?:OPENAI_API_KEY|DEEPSEEK_API_KEY|HF_TOKEN)\s*[=:]\s*[^\s"\x27,}]+']:
            x,n=re.subn(pattern,'[REDACTED_CREDENTIAL]',x);redactions[pattern]+=n
        if len(x)>1500000:
            return dict(_display_limited=True,original_characters=len(x),original_text_sha256=digest(x.encode()),head=x[:100000],tail=x[-100000:],note='Full value remains in original Recorder artifact; not silently treated as complete.')
        return x
    return x

def text(x):
    if isinstance(x,str):return x
    if isinstance(x,list):return '\n'.join(text(v)for v in x)
    if isinstance(x,dict):
        if'text'in x:return text(x['text'])
        if'content'in x:return text(x['content'])
        if'lines'in x:return text(x['lines'])
        if x.get('_display_limited'):return x['head']+'\n[DISPLAY LIMITED]\n'+x['tail']
    return ''

def scan(p,label):
    started=time.time();raw=(p/'result.json').read_bytes();result=json.loads(raw);cfg=result.get('config')or json.loads((p/'config.json').read_text())
    agent=cfg.get('agent')or{};kw=agent.get('kwargs')or{};contract=kw.get('config')or{}
    meta=dict(label=label,path=str(p),id=result.get('id'),trial=result.get('trial_name',p.name),task=result.get('task_name'),task_checksum=result.get('task_checksum'),
        result_sha256=digest(raw),rewards=(result.get('verifier_result')or{}).get('rewards'),verifier_return_code=(result.get('verifier_result')or{}).get('return_code'),
        exception_type=(result.get('exception_info')or{}).get('exception_type'),exception_message=(result.get('exception_info')or{}).get('exception_message'),
        failure_phase=result.get('failure_phase'),infrastructure_errors=result.get('infrastructure_errors'),secondary_errors=result.get('secondary_errors'),
        started=result.get('started_at'),finished=result.get('finished_at'),agent_execution=result.get('agent_execution'),agent_setup=result.get('agent_setup'),verifier=result.get('verifier'),
        model=agent.get('model_name'),wheel_sha256=kw.get('wheel_sha256'),agent_timeout_sec=agent.get('override_timeout_sec'),
        model_usage=(result.get('agent_result')or{}).get('model_usage'),lifecycle=(result.get('agent_result')or{}).get('metadata'),
        protocol={k:contract.get(k)for k in ['tools','compaction','toolResultBudget','finish','timeBudget','thinkingLevel','requestOptions']})
    task_path=Path((cfg.get('task')or{}).get('path','/DOES_NOT_EXIST'))
    instruction=task_path/'instruction.md';toml=task_path/'task.toml'
    meta['instruction']=instruction.read_text()if instruction.exists()else None
    meta['instruction_sha256']=digest(instruction.read_bytes())if instruction.exists()else None
    meta['task_toml']=toml.read_text()if toml.exists()else None
    verifier={}
    for f in sorted((p/'verifier').iterdir())if(p/'verifier').exists()else[]:
        if f.is_file():
            data=f.read_bytes();verifier[f.name]=dict(sha256=digest(data),bytes=len(data),text=data.decode(errors='replace')if len(data)<=2000000 else data[:100000].decode(errors='replace')+'\n[DISPLAY LIMITED; ORIGINAL RETAINED]')
    journal=p/'agent/openharness-rollout/events.jsonl';calls={};tools={};timeline=[];counts=collections.Counter();source_digest=hashlib.sha256();seq_errors=[];previous_seq=None
    run_end=None;run_start=None;source_stat=None
    if journal.exists():
        source_stat=journal.stat();artifacts=journal.parent/'artifacts';offset=0
        with journal.open('rb')as f:
            for line in f:
                line_offset=offset;offset+=len(line);source_digest.update(line)
                # SSE chunks/events dominate bytes; call_end preserves full parsed response.
                if any(marker in line[:300]+line[-200:]for marker in [b'"type":"call_chunk"',b'"type": "call_chunk"',b'"type":"call_event"',b'"type": "call_event"',b'"type":"tool_chunk"',b'"type": "tool_chunk"',b'"type":"tool_update"',b'"type": "tool_update"']):continue
                e=json.loads(line);kind=e.get('type');d=e.get('data')or{};counts[kind]+=1;seq=e.get('seq');cid=d.get('call_id')
                evidence=dict(seq=seq,offset=line_offset,bytes=len(line),event_sha256=digest(line),timestamp=e.get('timestamp'))
                if previous_seq is not None and seq is not None and seq<=previous_seq:seq_errors.append(seq)
                previous_seq=seq
                if kind=='run_start':run_start={k:d.get(k)for k in ['model','model_revision','session_id','run_id','operation']}
                elif kind=='run_end':run_end=d;timeline.append(dict(kind=kind,evidence=evidence,data=d))
                elif kind=='call_start':
                    calls[cid]=dict(call_id=cid,start=evidence,source=d.get('source'),request_options={k:v for k,v in(d.get('request_options')or{}).items()if k not in ['apiKey','headers']},input_hash=d.get('input_hash'))
                    timeline.append(dict(kind=kind,evidence=evidence,call_id=cid))
                elif kind=='call_payload':
                    payload=loadValue(d.get('payload'),artifacts);c=calls.setdefault(cid,dict(call_id=cid));c['payload_evidence']=evidence;c['provider_payload_sha256']=digest(encoded(payload))
                    messages=payload.get('messages',[]);c['history_message_count']=len(messages);c['tool_schema_sha256']=digest(encoded(payload.get('tools')))
                    c['payload_tail']=messages[-6:];c['payload_options']={k:v for k,v in payload.items()if k not in ['messages','tools']}
                    if label in ['M0','OLD_M0']:c['full_provider_payload']=payload
                elif kind=='call_end':
                    response=loadValue(d.get('response'),artifacts);c=calls.setdefault(cid,dict(call_id=cid));c.update(end=evidence,status=d.get('status'),error=d.get('error'),response=response)
                    timeline.append(dict(kind=kind,evidence=evidence,call_id=cid))
                elif kind=='tool_start':
                    eid=d.get('execution_id');tools[eid]=dict(execution_id=eid,call_id=cid,tool_call_id=d.get('tool_call_id'),name=d.get('name'),original_args=loadValue(d.get('original_args'),artifacts),start=evidence)
                    timeline.append(dict(kind=kind,evidence=evidence,execution_id=eid,call_id=cid))
                elif kind in ['tool_prepared','tool_raw','tool_end']:
                    eid=d.get('execution_id');t=tools.setdefault(eid,dict(execution_id=eid,call_id=cid));t[kind+'_evidence']=evidence
                    if kind=='tool_prepared':t['actual_args']=loadValue(d.get('actual_args'),artifacts)
                    elif kind=='tool_raw':t['raw_result']=loadValue(d.get('result'),artifacts)
                    else:
                        t['result']=loadValue(d.get('result'),artifacts);t['is_error']=d.get('is_error');t['status']=d.get('status');timeline.append(dict(kind=kind,evidence=evidence,execution_id=eid,call_id=cid))
                elif kind=='context_event':
                    event=d.get('event')or{}
                    if event.get('type')!='input_token_count':timeline.append(dict(kind=kind,evidence=evidence,data=loadValue(event,artifacts)))
        unchanged=journal.stat().st_size==source_stat.st_size and journal.stat().st_mtime_ns==source_stat.st_mtime_ns
        meta.update(journal=str(journal),journal_bytes=source_stat.st_size,journal_sha256=source_digest.hexdigest(),journal_stat_unchanged=unchanged)
    groups=collections.defaultdict(list)
    for t in tools.values():groups[(t.get('name'),digest(encoded(t.get('original_args'))))].append(t)
    repetitions=sorted([dict(name=k[0],args_sha256=k[1],count=len(v),errors=sum(bool(t.get('is_error'))for t in v),first_call=v[0].get('call_id'),last_call=v[-1].get('call_id'))for k,v in groups.items()if len(v)>1],key=lambda v:v['count'],reverse=True)
    lengths=[]
    for c in calls.values():
        r=c.get('response')or{};u=r.get('usage')or{} if isinstance(r,dict)else{};stop=r.get('stopReason')if isinstance(r,dict)else None
        if stop=='length'or c.get('status')=='length':lengths.append(dict(call_id=c['call_id'],usage=u,end=c.get('end')))
    report=dict(meta=meta,run_start=run_start,run_end=run_end,calls=list(calls.values()),tools=list(tools.values()),timeline=timeline,verifier=verifier,
        summary=dict(calls=len(calls),tools=len(tools),tool_errors=sum(bool(t.get('is_error'))for t in tools.values()),tool_groups_repeated=repetitions[:20],length_calls=lengths,run_end_present=run_end is not None,seq_regressions=seq_errors,event_counts=dict(counts)),
        scope='Original full parsed Assistant, Tool Start/Prepared/Raw/End and contexts. SSE duplicates omitted; pre-parser generation IDs not inferred.',redaction_patterns='Known secret labels/Bearer/sk-token forms, plus native Recorder redaction; no auth headers exported.',elapsed_seconds=time.time()-started)
    report=safe(report);report['redaction_counts']=dict(redactions)
    data=encoded(report);packed=gzip.compress(data,compresslevel=6)
    print(json.dumps(dict(id=result.get('id'),trial=p.name,label=label,sha256=digest(data),compressed_sha256=digest(packed),gzip_base64=base64.b64encode(packed).decode())),flush=True)
    print(json.dumps(dict(exported=p.name,label=label,calls=len(calls),tools=len(tools),bytes=source_stat.st_size if source_stat else 0,seconds=time.time()-started)),file=sys.stderr,flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['current','old']);args=p.parse_args()
    if args.mode=='old':
        r=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-m0-baseline-tb21-20261026/jobs/qwen35-m0-r1-20261026')
        selected=[(r/n,'OLD_M0')for n in ['portfolio-optimization__wJxDGgG','polyglot-rust-c__bKCCYGV']]
    else:
        r=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/common30-wheel6-native-jobs-r1');selected=[]
        labels={'gpu1-m2e1':'NEW_M2_E1','gpu2-m0':'M0','gpu3-m2e5':'NEW_M2_E5','gpu6-m1e5':'NEW_M1_E5','gpu7-m2e3':'NEW_M2_E3'}
        for j in sorted(r.iterdir()):
            if not j.is_dir():continue
            label=next((v for k,v in labels.items()if k in j.name),None)
            if not label:continue
            for d in sorted(j.iterdir()):
                if not(d/'result.json').is_file():continue
                if label=='M0'and not any(d.name.startswith(t+'__')for t in ['portfolio-optimization','polyglot-rust-c']):continue
                selected.append((d,label))
    print(json.dumps(dict(frozen_scope_count=len(selected),mode=args.mode)),file=sys.stderr,flush=True)
    for path,label in selected:scan(path,label)

if __name__=='__main__':main()
