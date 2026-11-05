"""Existing CPU audit loop extended to both frozen native collection scopes."""
import datetime,fcntl,json,os,shlex,subprocess,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
E17='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029'
PY='/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
PY17='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
SSH=['ssh','-S','/home/chenkeyi/.ssh/cf17-20261028.sock','-oBatchMode=yes','-oProxyCommand=false']
HOST='chenkeyi@180.163.192.17'
SCOPES=['stream-collection-r3','stream-collection-r4']
for key in ['DEEPSEEK_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
# Same sole derived-data writer lock as the previous worker.
lock=(R/'derived/stream-r3-audit-worker.lock').open('a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
last_signature={};errors={};audited=set();next_pool='tmax';pending={}
executor=ThreadPoolExecutor(max_workers=2)
def save(stage,trial=None):
 value=dict(status='CPU_TARGET_AUDITS_ACTIVE',pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
  stage=stage,current_trial_id=trial,newly_audited_trial_ids=sorted(audited),errors=errors,
  scopes=SCOPES,active_trial_ids=sorted(pending),max_concurrent_cpu_audits=2,
  teacher_dispatches_by_this_worker=0,new_gpu_processes=0)
 path=R/'checks/stream-r4-data-audit-worker.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2));tmp.replace(path)
def run(args,**kwargs):return subprocess.run(args,check=True,**kwargs)
def script(name,*args):
 save(name)
 with (R/'logs/stream-r4-data-audit.log').open('a') as log:
  run([PY,str(R/'scripts'/name),*args],stdout=log,stderr=subprocess.STDOUT,timeout=12000)
def audit_one(item,export):
 ident=item['trial_id']
 if export['errors'] or export['exported']==0:raise ValueError('Canonical export incomplete; preserve raw, no fabricated targets')
 import hashlib
 if hashlib.sha256(Path(export['export']).read_bytes()).hexdigest()!=export['export_sha256']:
  raise ValueError('Immutable canonical export SHA changed')
 # Existing UUID-addressed inputs and caches remain unchanged. These are CPU
 # derivations, never additional Harbor tasks or paid teacher attempts.
 remote=E17+'/validation/stream-r3/'+ident
 run(SSH+[HOST,'mkdir -p '+shlex.quote(remote+'/sources/canary-calls-all')],timeout=30)
 run(['rsync','-a','--bwlimit=8192','-e',shlex.join(SSH),export['export'],HOST+':'+remote+'/sources/canary-calls-all/'],timeout=1800)
 run(SSH+[HOST,shlex.join([PY17,E17+'/scripts/audit_stream_data_17.py',ident])],timeout=37000)
 incoming=R/'derived/stream-student-proofs-r3'/ident;incoming.mkdir(parents=True,exist_ok=True)
 run(['rsync','-a','-e',shlex.join(SSH),HOST+':'+remote+'/checks/',str(incoming/'checks')+'/'],timeout=300)
 return incoming/'checks/STUDENT_AUDIT_TRIALS_ALL.json'
while True:
 try:
  for ident,(future,item) in list(pending.items()):
   if not future.done():continue
   try:
    incoming=future.result()
    # One writer merges proofs and produces indexes, even when two independent
    # CPU audits are in flight on17.
    script('merge_student_proofs.py',str(R),str(incoming),'stream-r3-'+ident)
    script('audit_collection_results.py');audited.add(ident);errors.pop(ident,None)
   except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
    errors[ident]=dict(error_type=type(error).__name__,error=str(error)[:800],last_failed_epoch=time.time())
   finally:del pending[ident]
  changed=False
  for scope in SCOPES:
   base=R/'stream'/scope.removeprefix('stream-')
   if not (base/'CAMPAIGN.json').exists():continue
   signature=tuple(sorted((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in (base/'trials').glob('*/result.json')))
   if signature!=last_signature.get(scope):
    script('audit_native_canary_protocol.py',scope)
    script('export_native_canary_calls.py',scope)
    last_signature[scope]=signature;changed=True
  if changed:script('audit_collection_results.py')
  proof_index=json.loads((R/'checks/STUDENT_AUDIT_TRIALS.json').read_text())
  known={x['trial_id'] for x in proof_index['entries']}
  exports={}
  for scope in SCOPES:
   file=R/'checks'/(scope+'-actual-calls-export.json')
   if file.exists():exports.update({x['trial_id']:x for x in json.loads(file.read_text())})
  candidates=[]
  for pool in ['CALIBFORGE','TMAX']:
   for line in (R/'indexes'/(pool+'_FAILURE_OR_PENDING_INDEX.jsonl')).open():
    x=json.loads(line)
    if x['classification']=='REWARD_ONE_NATIVE_COMPLETE_STUDENT_AUDIT_PENDING' and x['job_name'] in SCOPES and x['trial_id'] not in known:
     candidates.append(x)
  candidates=[x for x in candidates if x['trial_id'] not in pending and time.time()-errors.get(x['trial_id'],{}).get('last_failed_epoch',0)>=300]
  candidates.sort(key=lambda x:(x['trial_id'] in errors,x['pool']!=next_pool,x['started_at'],x['trial_id']))
  for item in candidates[:2-len(pending)]:
   ident=item['trial_id'];next_pool='calibforge' if item['pool']=='tmax' else 'tmax'
   if ident not in exports:
    errors[ident]=dict(error_type='MISSING_IMMUTABLE_EXPORT',last_failed_epoch=time.time())
    continue
   pending[ident]=(executor.submit(audit_one,item,exports[ident]),item)
 except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
  errors['worker_observation']=dict(error_type=type(error).__name__,error=str(error)[:800])
 save('CPU_TARGET_AUDITS_RUNNING' if pending else 'IDLE_BETWEEN_OBSERVATIONS')
 time.sleep(30)

