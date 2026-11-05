"""Read metadata from live Recorder without exposing prompts or modifying trials."""
import hashlib,json,subprocess
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
code='''from pathlib import Path
import hashlib,json
from foundation.rollouts.export import loadValue
r=Path('/logs/agent/openharness-rollout');p=r/'events.jsonl';calls={};payloads=[];thinking_chars=0
if not p.exists():print(json.dumps(dict(status='RECORDER_NOT_YET_CREATED')));raise SystemExit
for raw in p.read_text().splitlines():
 try:e=json.loads(raw)
 except ValueError:continue
 d=e.get('data') or {};kind=e['type'];ident=d.get('call_id')
 if kind=='call_start':calls[ident]=d.get('source')
 if kind=='call_payload':
  v=loadValue(d['payload'],r/'artifacts');schemas=[{k:t['function'][k] for k in ['name','description','parameters']} for t in v.get('tools',[])]
  systems=[m['content'] for m in v['messages'] if m['role']=='system']
  payloads.append(dict(source=calls.get(ident),model=v['model'],thinking=v.get('thinking'),reasoning_effort=v.get('reasoning_effort'),max_tokens=v.get('max_tokens'),stream=v.get('stream'),temperature=v.get('temperature'),tool_names=[t['name'] for t in schemas],tool_schema_sha256=hashlib.sha256(json.dumps(schemas,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),system_prompt_sha256=hashlib.sha256(systems[0].encode()).hexdigest() if len(systems)==1 else None))
print(json.dumps(dict(status='LIVE_PREFIX_ONLY',call_count=len(calls),payload_count=len(payloads),first_payload=payloads[0] if payloads else None,last_payload=payloads[-1] if payloads else None,qualified_success=False)))'''
records=[]
for file in (R/'stream/collection-r3/dispatches').glob('*/dispatch.json'):
 x=json.loads(file.read_text())
 if x['kind']!='teacher':continue
 trial=R/'stream/collection-r3/trials'/x['trial_name']
 if (trial/'result.json').exists():continue
 lifecycle=list(trial.glob('remote-docker-*.compose.json'))
 if len(lifecycle)!=1:continue
 identity=lifecycle[0].name.removeprefix('remote-docker-').removesuffix('.compose.json')
 names=subprocess.run(['docker','ps','--filter','label=io.harbor.remote-docker.identity='+identity,'--format','{{.ID}}'],capture_output=True,text=True,check=True).stdout.split()
 if len(names)!=1:continue
 reply=subprocess.run(['docker','exec',names[0],'/harbor/agent-runtime/harbor-open-harness-venv/bin/python','-c',code],capture_output=True,text=True,timeout=20)
 item=dict(task_id=x['task_id'],pool=x['pool'],trial_name=x['trial_name'],container_id=names[0],returncode=reply.returncode)
 if reply.returncode==0:item['observation']=json.loads(reply.stdout)
 else:item['error']=reply.stderr[:300]
 records.append(item)
value=dict(scope='Live container Recorder metadata only; native terminal collection and qualification separate',records=records,teacher_model_requests_by_this_probe=0)
(R/'checks/stream-r3-live-container-payloads.json').write_text(json.dumps(value,indent=2));print(json.dumps(value))
