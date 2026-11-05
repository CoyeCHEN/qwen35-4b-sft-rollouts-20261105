"""Read-only canonical export of actual requests and verified raw SSE targets."""
from collections import OrderedDict
import gzip
import hashlib
import json
import io
from pathlib import Path
import sys
from teacher_call_dispositions import dispositions

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sys.path.insert(0,str(ROOT/'wheels/open_harness_ai-0.3.0-py3-none-any.whl'))
from foundation.rollouts.export import loadValue


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def normalized(message):
    if isinstance(message.get('content'),list):
        blocks=message['content']
        value=dict(role='assistant',content=''.join(b['text'] for b in blocks if b['type']=='text'),
            reasoning_content=''.join(b['thinking'] for b in blocks if b['type']=='thinking'))
        calls=[dict(id=b['id'],type='function',function=dict(name=b['name'],arguments=b['arguments']))
            for b in blocks if b['type']=='toolCall']
        if calls:value['tool_calls']=calls
    else:value=dict(message)
    value.setdefault('content','');value.setdefault('reasoning_content','')
    for call in value.get('tool_calls',[]):
        if isinstance(call['function']['arguments'],str):call['function']['arguments']=json.loads(call['function']['arguments'])
    return {k:value[k] for k in ['role','content','reasoning_content','tool_calls'] if k in value}


def raw_response(chunks):
    reasoning=[];text=[];calls=OrderedDict();content_started=False
    for chunk in chunks:
        for choice in chunk.get('choices',[]):
            delta=choice.get('delta') or {}
            if delta.get('reasoning_content'):
                if content_started:raise ValueError('Reasoning after visible body cannot be faithfully projected')
                reasoning.append(delta['reasoning_content'])
            if delta.get('content'):
                content_started=True;text.append(delta['content'])
            for c in delta.get('tool_calls') or []:
                f=c.get('function') or {};part=calls.setdefault(c['index'],dict(id='',name='',arguments=''))
                if c.get('id'):part['id']+=c['id']
                part['name']+=f.get('name') or '';part['arguments']+=f.get('arguments') or ''
    message=dict(role='assistant',content=''.join(text),reasoning_content=''.join(reasoning))
    if calls:
        message['tool_calls']=[dict(id=c['id'],type='function',function=dict(name=c['name'],arguments=c['arguments'])) for c in calls.values()]
    return message


def main():
    job=sys.argv[1]
    if job not in ['stream-collection-r3','stream-collection-r4','cf-tmax-canary-first2-20261030','cf-tmax-canary-remaining14-20261030',
                   'cf-tmax-canary-second-attempt6-20261030',
                   'cf-summary-contract-canary-20261030',
                   'tmax-summary-contract-canary-20261030',
                   'cf-tmax-original-environment-canary-20261030',
                   'tmax-original-environment-acceptance-extension-20261030',
                   'cf-tmax-formal-first-pass-summary-r1-20261030',
                   'cf-tmax-formal-second-pass-summary-r1-20261030']:raise ValueError('Unexpected canary job')
    out=ROOT/'derived/canary-calls-all';out.mkdir(parents=True,exist_ok=True)
    report=[]
    ledger=[]
    pool_by_task={row['task_id']:row['pool'] for name in ['CALIBFORGE_500_TASKS.jsonl','TMAX_RUNTIME_CANDIDATES_V2.jsonl'] for row in map(json.loads,(ROOT/'manifests'/name).open())}
    from collection_selection_r4 import active_rows
    from run_collection_stream_r3 import attempt_counts
    pool_by_task.update({row['task_id']:row['pool'] for row in active_rows(attempt_counts())})
    trial_root=ROOT/'stream'/job.removeprefix('stream-')/'trials' if job in ['stream-collection-r3','stream-collection-r4'] else ROOT/'jobs'/job
    for journal in sorted(trial_root.glob('*/agent/openharness-rollout/events.jsonl')):
        artifacts=journal.parent/'artifacts';trial=journal.parent.parent.parent;calls=OrderedDict()
        if not (trial/'result.json').exists():continue
        journal_sha256=hashlib.sha256(journal.read_bytes()).hexdigest()
        for line in journal.open():
            event=json.loads(line);data=event['data'];ident=data.get('call_id')
            if event['type']=='call_start':calls[ident]=dict(call_id=ident,source=data.get('source'),chunks=[],
                started_event={k:v for k,v in event.items() if k!='data'},api_attempt=data.get('attempt'),retry_of=data.get('retry_of'))
            elif event['type']=='call_payload':calls[ident]['provider_payload']=loadValue(data['payload'],artifacts)
            elif event['type']=='call_chunk':
                value=loadValue(data['chunk'],artifacts)
                try:value=json.loads(value) if isinstance(value,str) else value
                except ValueError:continue
                if isinstance(value,dict):calls[ident]['chunks'].append(value)
            elif event['type']=='call_end':
                calls[ident].update(native_response=loadValue(data.get('response'),artifacts),status=data.get('status'),error=data.get('error'),
                    finished_event={k:v for k,v in event.items() if k!='data'})
        result=json.loads((trial/'result.json').read_text());records=[];errors=[]
        call_dispositions={x['call_id']:x for x in dispositions(calls.values())}
        sidecar=ROOT/'derived/teacher-call-dispositions'/(result['id']+'.json')
        sidecar.parent.mkdir(parents=True,exist_ok=True)
        binding=dict(trial_id=result['id'],source_journal_sha256=journal_sha256,
            classifier_sha256=hashlib.sha256((ROOT/'scripts/teacher_call_dispositions.py').read_bytes()).hexdigest(),
            calls=list(call_dispositions.values()),raw_attempts_preserved=True)
        if sidecar.exists():
            if json.loads(sidecar.read_text())!=binding:raise ValueError('Immutable call-disposition binding changed')
        else:sidecar.write_text(json.dumps(binding,indent=2))
        for call in calls.values():
            payload=call.get('provider_payload') or {}
            usage_updates=[{k:chunk.get(k) for k in ['id','created','model','usage']}
                for chunk in call['chunks'] if chunk.get('usage') is not None]
            ledger.append(dict(task_id=Path(result['config']['task']['path']).name,task_name=result['task_name'],
                pool=pool_by_task[Path(result['config']['task']['path']).name],trial_id=result['id'],
                call_id=call['call_id'],source=call['source'],api_attempt=call.get('api_attempt'),
                started_event=call.get('started_event'),finished_event=call.get('finished_event'),
                service_model_alias=payload.get('model'),actual_response_model_aliases=sorted({x['model'] for x in call['chunks'] if x.get('model')}),
                thinking=payload.get('thinking'),reasoning_effort=payload.get('reasoning_effort'),
                requested_max_output=payload.get('max_tokens'),requested_temperature=payload.get('temperature'),
                temperature_semantics='Ignored in Thinking mode; effective when Thinking disabled',
                provider_usage_updates=usage_updates,native_usage=(call.get('native_response') or {}).get('usage'),
                provider_final_usage=next((u['usage'] for u in reversed(usage_updates) if u.get('usage')),None),
                billing_status='PROVIDER_USAGE_RECORDED' if any(u.get('usage') for u in usage_updates) else 'NO_PROVIDER_USAGE_REPORT',
                native_cost_semantics='Estimate from frozen descriptor rates, not a provider invoice; raw usage preserved',
                call_status=call.get('status'),stop_reason=(call.get('native_response') or {}).get('stopReason'),
                retry_of=call.get('retry_of'),assistant_target_disposition=call_dispositions[call['call_id']],
                source_journal_sha256=journal_sha256,raw_evidence=str(journal)))
            if call['source']!='agent':continue
            if call_dispositions[call['call_id']]['disposition']=='RECOVERED_EMPTY_TRANSPORT_CALL_NO_ASSISTANT_TARGET':continue
            try:
                response=raw_response(call['chunks'])
                if digest(normalized(response))!=digest(normalized(call['native_response'])):
                    raise ValueError('Raw SSE and native assistant response disagree')
                records.append(dict(call_id=call['call_id'],trial_id=result['id'],task_name=result['task_name'],
                    provider_payload=call['provider_payload'],assistant_response=response,context_fidelity='provider_payload',
                    source_journal_sha256=journal_sha256,
                    native_response_sha256=digest(call['native_response']),raw_sse_response_semantics_verified=True,
                    usage=call['native_response'].get('usage'),stop_reason=call['native_response'].get('stopReason'),
                    call_status=call['status']))
            except (ValueError,KeyError,TypeError) as error:
                errors.append(dict(call_id=call['call_id'],reason=str(error)))
        path=out/(trial.name+'.jsonl.gz')
        encoded=''.join(json.dumps(record,ensure_ascii=False)+'\n' for record in records)
        if path.exists():
            with gzip.open(path,'rt',encoding='utf-8') as stream:
                if stream.read()!=encoded:raise ValueError('A completed canonical export changed; preserve and investigate its identity')
        else:
            with path.open('xb') as raw:
                with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as compressed:
                    with io.TextIOWrapper(compressed,encoding='utf-8') as stream:stream.write(encoded)
        report.append(dict(trial_id=result['id'],task_name=result['task_name'],source_trial=str(trial),
            agent_calls=sum(c['source']=='agent' for c in calls.values()),exported=len(records),errors=errors,
            call_dispositions=str(sidecar),call_dispositions_sha256=hashlib.sha256(sidecar.read_bytes()).hexdigest(),
            export=str(path),export_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            reward=(result.get('verifier_result') or {}).get('rewards'),
            sft_admission='NOT_DECIDED_BY_EXPORT; requires verifier, native integrity and student prefix/loader audit'))
    ledger_file=ROOT/'indexes'/(job+'-CALL_COST_TOKEN_LEDGER.jsonl')
    with ledger_file.with_suffix('.tmp').open('w') as stream:
        for row in ledger:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    ledger_file.with_suffix('.tmp').replace(ledger_file)
    (ROOT/'checks'/(job+'-actual-calls-export.json')).write_text(json.dumps(report,indent=2));print(json.dumps(report))


if __name__=='__main__':main()
