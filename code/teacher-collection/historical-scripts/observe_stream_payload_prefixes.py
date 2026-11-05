"""Copy two live Recorder prefixes through Docker archive API; metadata only."""
from collections import Counter
import datetime,hashlib,json,subprocess
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
records=[];seen=set()
for file in (R/'stream/collection-r3/dispatches').glob('*/dispatch.json'):
 x=json.loads(file.read_text())
 if x['kind']!='teacher' or x['pool'] in seen:continue
 trial=R/'stream/collection-r3/trials'/x['trial_name']
 if (trial/'result.json').exists():continue
 configs=list(trial.glob('remote-docker-*.compose.json'))
 if len(configs)!=1:continue
 identity=configs[0].name.removeprefix('remote-docker-').removesuffix('.compose.json')
 names=subprocess.run(['docker','ps','--filter','label=io.harbor.remote-docker.identity='+identity,'--format','{{.ID}}'],capture_output=True,text=True,check=True).stdout.split()
 if len(names)!=1:continue
 folder=R/'checks/live-recorder-prefixes'/x['trial_name'];folder.mkdir(parents=True,exist_ok=True)
 output=folder/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')+'.prefix.jsonl')
 reply=subprocess.run(['docker','cp',names[0]+':/logs/agent/openharness-rollout/events.jsonl',str(output)],capture_output=True,text=True,timeout=30)
 if reply.returncode:continue
 events=Counter();payloads=[];calls={};models=set()
 for raw in output.open():
  try:e=json.loads(raw)
  except ValueError:continue
  events[e['type']]+=1;d=e.get('data') or {}
  if e['type']=='call_start':calls[d['call_id']]=d.get('source')
  if e['type']=='call_payload' and isinstance(d['payload'],dict) and 'model' in d['payload']:
   v=d['payload'];schemas=[{k:t['function'][k] for k in ['name','description','parameters']} for t in v.get('tools',[])]
   systems=[m['content'] for m in v['messages'] if m['role']=='system']
   payloads.append(dict(source=calls.get(d['call_id']),model=v['model'],thinking=v.get('thinking'),reasoning_effort=v.get('reasoning_effort'),max_tokens=v.get('max_tokens'),stream=v.get('stream'),temperature=v.get('temperature'),tool_names=[t['name'] for t in schemas],tool_schema_sha256=hashlib.sha256(json.dumps(schemas,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),system_prompt_sha256=hashlib.sha256(systems[0].encode()).hexdigest() if len(systems)==1 else None))
  if e['type']=='call_chunk':
   value=d['chunk']
   try:value=json.loads(value) if isinstance(value,str) else value
   except ValueError:continue
   if isinstance(value,dict) and value.get('model'):models.add(value['model'])
 if payloads:
  first=next(p for p in payloads if p['source']=='agent')
  expected=json.loads((R/'checks/summary-r1-offline-teacher-contract.json').read_text())
  passed=all(first[k]==expected[k] for k in ['tool_names','tool_schema_sha256','system_prompt_sha256','thinking','reasoning_effort','max_tokens','stream','temperature'])
  records.append(dict(pool=x['pool'],task_id=x['task_id'],trial_name=x['trial_name'],prefix_path=str(output),prefix_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),event_counts=dict(events),model_calls_by_source=dict(Counter(calls.values())),first_actual_payload=first,first_payload_contract_passed=passed,response_models=sorted(models),terminal=False))
  seen.add(x['pool'])
value=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='Two live native Recorder prefixes; first actual request check only, terminal all-call audit remains necessary',records=records,teacher_requests_by_probe=0)
(R/'checks/stream-r3-live-container-payloads.json').write_text(json.dumps(value,indent=2));print(json.dumps(value))
