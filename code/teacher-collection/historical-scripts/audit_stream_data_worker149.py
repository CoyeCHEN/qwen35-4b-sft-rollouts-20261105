"""Derived-data audit only; native teacher queue remains the sole paid dispatcher.

Use existing CPU tools and persistent149->17 SSH. No new timer or scheduler.
"""
import datetime,fcntl,json,os,shlex,subprocess,sys,time
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
E17='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029'
PY='/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
PY17='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
SSH=['ssh','-S','/home/chenkeyi/.ssh/cf17-20261028.sock','-oBatchMode=yes','-oProxyCommand=false']
HOST='chenkeyi@180.163.192.17'
for key in ['DEEPSEEK_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
lock=(R/'derived/stream-r3-audit-worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
last_signature=None;errors={};audited=set()
def run(args,**kw):return subprocess.run(args,check=True,**kw)
def script(name,*args):
 with (R/'logs/stream-r3-data-audit.log').open('a') as log:run([PY,str(R/'scripts'/name),*args],stdout=log,stderr=subprocess.STDOUT,timeout=12000)
while True:
 try:
  terminal=list((R/'stream/collection-r3/trials').glob('*/agent/openharness-rollout/events.jsonl'))
  signature=tuple(sorted(str(p) for p in terminal if (p.parent.parent.parent/'result.json').exists()))
  if signature!=last_signature:
   script('audit_native_canary_protocol.py','stream-collection-r3')
   script('export_native_canary_calls.py','stream-collection-r3')
   script('audit_collection_results.py')
   last_signature=signature
  proof_index=json.loads((R/'checks/STUDENT_AUDIT_TRIALS.json').read_text())
  known={x['trial_id'] for x in proof_index['entries']}
  exports={x['trial_id']:x for x in json.loads((R/'checks/stream-collection-r3-actual-calls-export.json').read_text())} if (R/'checks/stream-collection-r3-actual-calls-export.json').exists() else {}
  candidates=[]
  for pool in ['CALIBFORGE','TMAX']:
   for line in (R/'indexes'/(pool+'_FAILURE_OR_PENDING_INDEX.jsonl')).open():
    x=json.loads(line)
    if x['classification']=='REWARD_ONE_NATIVE_COMPLETE_STUDENT_AUDIT_PENDING' and x['job_name']=='stream-collection-r3' and x['trial_id'] not in known:candidates.append(x)
  for item in candidates:
   ident=item['trial_id']
   try:
    export=exports[ident]
    if export['errors'] or export['exported']==0:raise ValueError('Canonical export incomplete; retain raw and audit error, no fabricated targets')
    remote=E17+'/validation/stream-r3/'+ident
    run(SSH+[HOST,'mkdir -p '+shlex.quote(remote+'/sources/canary-calls-all')],timeout=30)
    run(['rsync','-a','--bwlimit=8192','-e',shlex.join(SSH),export['export'],HOST+':'+remote+'/sources/canary-calls-all/'],timeout=1800)
    run(SSH+[HOST,shlex.join([PY17,E17+'/scripts/audit_stream_data_17.py',ident])],timeout=37000)
    incoming=R/'derived/stream-student-proofs-r3'/ident;incoming.mkdir(parents=True,exist_ok=True)
    run(['rsync','-a','-e',shlex.join(SSH),HOST+':'+remote+'/checks/',str(incoming/'checks')+'/'],timeout=300)
    script('merge_student_proofs.py',str(R),str(incoming/'checks/STUDENT_AUDIT_TRIALS_ALL.json'),'stream-r3-'+ident)
    script('audit_collection_results.py');audited.add(ident);errors.pop(ident,None)
   except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:errors[ident]=dict(error_type=type(error).__name__,error=str(error)[:800])
 except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:errors['worker_observation']=dict(error_type=type(error).__name__,error=str(error)[:800])
 state=dict(status='CPU_TARGET_AUDITS_ACTIVE',pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
  newly_audited_trial_ids=sorted(audited),errors=errors,teacher_dispatches_by_this_worker=0,new_gpu_processes=0)
 path=R/'checks/stream-r3-data-audit-worker.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2));tmp.replace(path)
 time.sleep(30)
