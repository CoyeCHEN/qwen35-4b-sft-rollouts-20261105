"""Read-only canonical export of actual requests and verified raw SSE targets."""
from collections import OrderedDict
import gzip
import hashlib
import json
from pathlib import Path
import sys

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
    out=ROOT/'derived/canary-calls';out.mkdir(parents=True,exist_ok=True)
    report=[]
    for journal in sorted((ROOT/'jobs/cf-tmax-canary-first2-20261030').glob('*/agent/openharness-rollout/events.jsonl')):
        artifacts=journal.parent/'artifacts';trial=journal.parent.parent.parent;calls=OrderedDict()
        for line in journal.open():
            event=json.loads(line);data=event['data'];ident=data.get('call_id')
            if event['type']=='call_start':calls[ident]=dict(call_id=ident,source=data.get('source'),chunks=[])
            elif event['type']=='call_payload':calls[ident]['provider_payload']=loadValue(data['payload'],artifacts)
            elif event['type']=='call_chunk':
                value=loadValue(data['chunk'],artifacts)
                try:value=json.loads(value) if isinstance(value,str) else value
                except ValueError:continue
                if isinstance(value,dict):calls[ident]['chunks'].append(value)
            elif event['type']=='call_end':
                calls[ident].update(native_response=loadValue(data.get('response'),artifacts),status=data.get('status'),error=data.get('error'))
        result=json.loads((trial/'result.json').read_text());records=[];errors=[]
        for call in calls.values():
            if call['source']!='agent':continue
            try:
                response=raw_response(call['chunks'])
                if digest(normalized(response))!=digest(normalized(call['native_response'])):
                    raise ValueError('Raw SSE and native assistant response disagree')
                records.append(dict(call_id=call['call_id'],trial_id=result['id'],task_name=result['task_name'],
                    provider_payload=call['provider_payload'],assistant_response=response,context_fidelity='provider_payload',
                    source_journal_sha256=hashlib.sha256(journal.read_bytes()).hexdigest(),
                    native_response_sha256=digest(call['native_response']),raw_sse_response_semantics_verified=True,
                    usage=call['native_response'].get('usage'),stop_reason=call['native_response'].get('stopReason'),
                    call_status=call['status']))
            except (ValueError,KeyError,TypeError) as error:
                errors.append(dict(call_id=call['call_id'],reason=str(error)))
        path=out/(trial.name+'.jsonl.gz')
        with gzip.open(path,'wt',encoding='utf-8') as stream:
            for record in records:stream.write(json.dumps(record,ensure_ascii=False)+'\n')
        report.append(dict(trial_id=result['id'],task_name=result['task_name'],source_trial=str(trial),
            agent_calls=sum(c['source']=='agent' for c in calls.values()),exported=len(records),errors=errors,
            export=str(path),export_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            reward=(result.get('verifier_result') or {}).get('rewards'),
            sft_admission='NOT_DECIDED_BY_EXPORT; requires verifier, native integrity and student prefix/loader audit'))
    (ROOT/'checks/canary-actual-calls-export.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))


if __name__=='__main__':main()
