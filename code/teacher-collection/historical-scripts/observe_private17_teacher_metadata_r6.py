"""Read actual private17 teacher Recorder metadata; never dispatch a model."""
import datetime,hashlib,json,os,subprocess
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH']
os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
CLIENT=['docker','--host','ssh://chenkeyi@180.163.192.17:22']
CODE="""from pathlib import Path
import hashlib,json,os
from foundation.rollouts.export import loadValue
r=Path('/logs/agent/openharness-rollout');p=r/'events.jsonl';out={'recorder_exists':p.exists(),'proxy_environment_keys_present':[k for k in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'] if os.environ.get(k)]}
if p.exists():
 out.update(recorder_bytes=p.stat().st_size,recorder_modified_epoch=p.stat().st_mtime);sources={}
 for line in p.open():
  try:e=json.loads(line)
  except ValueError:break
  d=e.get('data') or {};ident=d.get('call_id')
  if e['type']=='call_start':sources[ident]=d.get('source')
  if e['type']=='call_payload':
   v=loadValue(d['payload'],r/'artifacts');schemas=[{k:t['function'][k] for k in ['name','description','parameters']} for t in v.get('tools',[])];systems=[m['content'] for m in v['messages'] if m['role']=='system']
   out['first_actual_payload']=dict(source=sources.get(ident),model=v['model'],thinking=v.get('thinking'),reasoning_effort=v.get('reasoning_effort'),max_tokens=v.get('max_tokens'),stream=v.get('stream'),temperature=v.get('temperature'),tool_names=[t['name'] for t in schemas],tool_schema_sha256=hashlib.sha256(json.dumps(schemas,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),system_prompt_sha256=hashlib.sha256(systems[0].encode()).hexdigest() if len(systems)==1 else None)
   break
 with p.open('rb') as f:f.seek(max(0,p.stat().st_size-262144));tail=f.read().splitlines()
 kinds=[]
 for line in tail:
  try:e=json.loads(line)
  except ValueError:continue
  if e['type'] in ['call_chunk','call_end']:kinds.append(e['type'])
 out['recent_provider_event_types']=sorted(set(kinds));out['recent_provider_event_count']=len(kinds)
print(json.dumps(out))
"""
def run(args):return subprocess.run(args,capture_output=True,text=True,timeout=35)
authority=json.loads((R/'checks/CURRENT_DISPATCH_AUTHORITY_R6.json').read_text())
state=json.loads(Path(authority['state_path']).read_text());rows=[]
for name,item in state['active_teacher_trials'].items():
 trial=R/'stream/collection-r4/trials'/name;cfg=json.loads((trial/'config.json').read_text())
 if cfg['environment']['kwargs']['endpoint']!='ssh://chenkeyi@180.163.192.17:22':continue
 q=run([*CLIENT,'info','--format','{{.ID}}']);assert q.returncode==0 and q.stdout.strip()=='59c8ba22-0aa4-4aed-bc43-4e1b5989fa22'
 compose,=trial.glob('remote-docker-*.compose.json');identity=compose.name.removeprefix('remote-docker-').removesuffix('.compose.json')
 q=run([*CLIENT,'ps','--filter','label=io.harbor.remote-docker.identity='+identity,'--format','{{.ID}}']);containers=q.stdout.split()
 row=dict(trial_name=name,**item,engine_id='59c8ba22-0aa4-4aed-bc43-4e1b5989fa22',config_sha256=hashlib.sha256((trial/'config.json').read_bytes()).hexdigest())
 if len(containers)==1:
  q=run([*CLIENT,'exec',containers[0],'/harbor/agent-runtime/harbor-open-harness-venv/bin/python','-c',CODE]);row['probe_returncode']=q.returncode
  if q.returncode==0:row['metadata']=json.loads(q.stdout)
  else:row['error']=q.stderr[-500:]
 rows.append(row)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),controller_pid=state['pid'],global_actual_teacher_trials=state['actual_teacher_trials'],private17_active_teachers=rows,model_calls_by_observer=0,raw_prompt_or_response_copied=0,qualified_success_claim=False)
p=R/'checks'/('private17-actual-teacher-metadata-r6-'+stamp+'.json')
with p.open('x') as f:json.dump(out,f,indent=2)
print(json.dumps(out))
