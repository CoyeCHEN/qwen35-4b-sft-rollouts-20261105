"""Independent native Recorder, full-tool, payload, history and closure checks."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from foundation.rollouts.export import RolloutView
from foundation.rollouts.store import isArtifactRef

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')


def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def main():
    output=Path(sys.argv[1]);view=RolloutView.open(output/'recorder')
    validation=view.validate();assert validation['complete'],validation
    def resolve(value):
        if isArtifactRef(value):
            raw=view.readArtifact(value)
            return raw.decode()if value['encoding']=='utf-8'else raw
        if isinstance(value,dict):return {k:resolve(v)for k,v in value.items()}
        if isinstance(value,list):return [resolve(v)for v in value]
        return value
    calls,tools,runs,contexts=[resolve(x)for x in view.rows()]
    assert len(runs)==1 and runs[0]['status']=='completed'
    active=[c for c in calls if c['source']=='agent']
    assert len(active)>=3 and all(c['status']in ('toolUse','stop')for c in active)
    names={t['name']for t in tools};assert {'write','read','edit_patch','finish','bash','bash_job','trajectory_read'}<=names,names
    assert (output/'bg-ok.txt').read_text().strip()=='ready','Real background job must complete'
    binding=json.loads((output/'SERVING_MODEL_BINDING.json').read_text())
    assert any(t['name']=='finish'and t.get('raw_result',{}).get('finishRequested')for t in tools)
    assert runs[0]['config']['finish']['enabled']
    assert runs[0]['config']['toolResultBudget']['enabled']
    assert runs[0]['config']['backgroundJobs']['enabled']
    if (output/'bg-ok.txt').exists():assert {'bash','bash_job','trajectory_read'}<=names,names
    previous={};projected=[];replayed=0;rows=[]
    for call in active:
        p=call['payload'];response=call['response']
        assert p['model']==binding['model_id']
        assert call['fidelity']=='provider_payload'
        assert digest(p['tools'])=='099b173339bdf84c6206669330ae5e7d1e04fdb17a8ae124303a76c98eab98e7'
        system='\n'.join(x['content']for x in p['messages']if x['role']=='system')
        assert hashlib.sha256(system.encode()).hexdigest()=='400cd2a6498f6f0b33dea4b15cdc6c2e8c75b450017aca7ea7e6045041fb6958'
        for key,value in dict(max_tokens=81920,temperature=1.,top_p=.95,top_k=20,min_p=0.,presence_penalty=1.5,repetition_penalty=1.,stream=True).items():assert p[key]==value,(key,p.get(key))
        assert p['chat_template_kwargs']=={'enable_thinking':True}
        for m in p['messages']:
            if m['role']=='assistant'and m.get('tool_calls'):
                ident=m['tool_calls'][0]['id'];expected=previous[ident]
                if expected:
                    assert m.get('reasoning_content')==expected,'Historical thinking was dropped or rewritten'
                    replayed+=1
        thinking=''.join(x['thinking']for x in response['content']if x['type']=='thinking')
        text=''.join(x['text']for x in response['content']if x['type']=='text')
        tc=[]
        for x in response['content']:
            if x['type']=='toolCall':
                previous[x['id']]=thinking
                tc.append(dict(id=x['id'],type='function',function=dict(name=x['name'],arguments=json.dumps(x['arguments'],ensure_ascii=False))))
        assistant=dict(role='assistant',content=text,reasoning_content=thinking)
        if tc:assistant['tool_calls']=tc
        usage=response['usage']
        projected.append(dict(call_id=call['call_id'],context_fidelity='provider_payload',provider_payload=p,
            assistant_response=assistant,actual_prompt_tokens=usage['input']+usage['cacheRead']))
        rows.append(dict(call_id=call['call_id'],status=call['status'],payload_sha256=digest(p),thinking_characters=len(thinking),reasoning_usage_tokens=usage.get('reasoning'),actual_completion_tokens=usage['output'],native_prompt_tokens=usage['input']+usage['cacheRead']))
    assert replayed>=2,'No actual multi-turn reasoning replay exercised'
    (output/'RESOLVED_NATIVE_CALLS.json').write_text(json.dumps(projected,ensure_ascii=False)+'\n')
    subprocess.run([str(R/'env/serve-new11-r1/bin/python'),str(R/'audit-native-cli-prefix-r2.py'),str(output)],check=True,timeout=60)
    prefix=json.loads((output/'NATIVE_PREFIX_AUDIT.json').read_text());assert prefix['passed']
    sessions=list((output/'sessions').glob('*.jsonl'));assert sessions
    session_files=[]
    for path in sessions:
        raw=path.read_bytes();assert raw.endswith(b'\n')
        for line in raw.splitlines():json.loads(line)
        session_files.append(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest()))
    result=dict(passed=True,native_recording_validation=validation,calls=rows,
        actual_thinking_history_replays_verified=replayed,full_eleven_tool_payload_verified=True,
        actual_tool_names=sorted(names),tool_calls=len(tools),session_files=session_files,
        native_sglang_prefix_and_gpu_usage_verified=prefix,
        task_verifier_score=None,scope='Native protocol and scratch artifacts, no official Task/Reward')
    (output/'NATIVE_CLI_AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,calls=len(active),tools=sorted(names),reasoning_replays=replayed)),flush=True)


if __name__=='__main__':main()
