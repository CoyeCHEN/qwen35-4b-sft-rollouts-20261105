"""Recheck3 original tasks whose preparation receipt was lost on cleanup timeout."""
import datetime,json,os,subprocess,sys
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
for key in ['DEEPSEEK_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
os.environ.update(DOCKER_HOST='ssh://chenkeyi@127.0.0.1:5102',SSH_AUTH_SOCK='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock')
os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH']
plan=json.loads((R/'checks/tmax-original-runtime-pool-preparation.json').read_text())
tasks=[x['task_id'] for x in plan['observed'] if x['status']=='NO_PREPARATION_RECEIPT']
if set(tasks)!={'task_002256_a6eb7333','task_003869_321abf76','task_004229_60792e8f'}:raise ValueError('Explicit recovery scope changed')
report=R/'checks/tmax-missing-receipt-recovery-r7.json'
if report.exists():raise FileExistsError('Inspect existing recovery; never duplicate')
records=[]
for ident in tasks:
 receipt=R/'checks/tmax-environments-runtime-r4'/(ident+'.json')
 if receipt.exists():raise FileExistsError('Original receipt now present; inspect instead of overwriting')
 # Only stale preparation containers for this task/context may be removed.
 for context in (R/'build-contexts').glob(ident+'-*'):
  name='tmax500-preflight-runtime-r4-'+context.name.removeprefix(ident+'-')
  probe=subprocess.run(['docker','inspect',name],capture_output=True,text=True,timeout=60)
  if probe.returncode:
   if 'no such' not in probe.stderr.casefold():raise RuntimeError('Container ownership unobserved')
   continue
  value=json.loads(probe.stdout)[0]
  if value['Config']['Labels'].get('rsi.campaign')!=R.name:raise ValueError('Preparation container ownership differs')
  subprocess.run(['docker','rm','-f',value['Id']],check=True,timeout=180)
 result=subprocess.run([sys.executable,str(R/'scripts/prepare_tmax_images_v2.py'),'--task-id',ident,'--startup-recheck'],check=False)
 value=json.loads(receipt.read_text()) if receipt.exists() else dict(status='RECOVERY_MISSING_RECEIPT')
 records.append(dict(task_id=ident,returncode=result.returncode,status=value['status'],receipt=str(receipt)))
 report.write_text(json.dumps(dict(status='RECOVERING_ORIGINAL_TASKS',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),records=records,model_calls=0,official_task_changes=0),indent=2))
 print(json.dumps(records[-1]),flush=True)
state=json.loads(report.read_text());state['status']='THREE_ORIGINAL_ENVIRONMENT_RECHECKS_TERMINAL';report.write_text(json.dumps(state,indent=2))
