"""One derived-data writer with explicit canonical tokenizer and export quarantine."""
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
MAX_PENDING=64
import hashlib
REGISTRY_FILE=R/'checks/ENCODER_NFC_REPROOF_CASES_R367.json'
if hashlib.sha256(REGISTRY_FILE.read_bytes()).hexdigest()!='bc57ec4ffc95601ce94a1346b2d5432ab38f37c80d5593d5e414779b41ae6d1e':raise ValueError('Exact NFC reproof scope changed')
NFC_REGISTRY=json.loads(REGISTRY_FILE.read_text())
NFC_ENCODER=NFC_REGISTRY['current_encoder_sha256']

def audit_one(item,export):
 ident=item['trial_id']
 if export['errors']:
  from reviewed_export_quarantines_r246 import review
  return review(item,export)
 if export['exported']==0:raise ValueError('Canonical export empty; preserve raw, no fabricated targets')
 import hashlib
 if hashlib.sha256(Path(export['export']).read_bytes()).hexdigest()!=export['export_sha256']:
  raise ValueError('Immutable canonical export SHA changed')
 # Preserve completed, unmerged legacy canonical proofs without redoing them.
 cached=R/'derived/stream-student-proofs-r6'/ident/'checks/STUDENT_AUDIT_TRIALS_ALL.json'
 if ident not in NFC_REGISTRY['cases'] and cached.exists():
  doc=json.loads(cached.read_text());entry,=doc['entries']
  if entry['trial_id']!=ident or entry['source_journal_sha256']!=item['source_journal_sha256'] or entry['raw_export_sha256']!=export['export_sha256']:raise ValueError('Existing unmerged proof has another original trajectory')
  for proof in doc['proofs'].values():
   if hashlib.sha256((cached.parent.parent/proof['relative_path']).read_bytes()).hexdigest()!=proof['sha256']:raise ValueError('Existing unmerged native proof artifact changed')
  return cached
 remote=E17+'/validation/stream-r3/'+ident
 run(SSH+[HOST,'mkdir -p '+shlex.quote(remote+'/sources/canary-calls-all')],timeout=30)
 run(['rsync','-a','-e',shlex.join(SSH),export['export'],HOST+':'+remote+'/sources/canary-calls-all/'],timeout=1800)
 reply=run(SSH+[HOST,shlex.join([PY17,E17+'/scripts/audit_stream_nfc_canonical17_r366.py',ident])],timeout=37000,capture_output=True,text=True)
 document=json.loads(reply.stdout.strip().splitlines()[-1]);checks=document['checks']
 roots=['/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/data-canonical-trials-r366/'+ident+'/checks']
 if checks not in roots:raise ValueError('Student proof outside the declared immutable SSD audit roots')
 incoming=R/'derived/stream-student-proofs-nfc-r12'/ident;incoming.mkdir(parents=True,exist_ok=True)
 run(['rsync','-a','-e',shlex.join(SSH),HOST+':'+checks+'/',str(incoming/'checks')+'/'],timeout=300)
 return incoming/'checks/STUDENT_AUDIT_TRIALS_ALL.json'

def run(args,**kwargs):return subprocess.run(args,check=True,**kwargs)

def main():
 lock=(R/'derived/stream-r3-audit-worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 last_signature={};errors={};audited=set();pending={};next_pool='tmax'
 executor=ThreadPoolExecutor(max_workers=2)
 def save(stage,trial=None):
  value=dict(status='CPU_TARGET_AUDITS_ACTIVE',source_revision='r12',pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
   stage=stage,current_trial_id=trial,newly_audited_trial_ids=sorted(audited),errors=errors,scopes=SCOPES,
   active_trial_ids=sorted(k for k,(f,_) in pending.items() if f.running()),
   queued_trial_ids=sorted(k for k,(f,_) in pending.items() if not f.running() and not f.done()),
   completed_waiting_merge=sorted(k for k,(f,_) in pending.items() if f.done()),
   pending_futures=len(pending),max_pending_cpu_audits=MAX_PENDING,max_concurrent_cpu_audits=2,
   teacher_dispatches_by_this_worker=0,new_gpu_processes=0)
  path=R/'checks/stream-r4-data-audit-worker.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2));tmp.replace(path)
 def script(name,*args):
  save(name)
  with (R/'logs/stream-r12-data-audit.log').open('a') as log:run([PY,str(R/'scripts'/name),*args],stdout=log,stderr=subprocess.STDOUT,timeout=12000)
 def enqueue():
  nonlocal next_pool
  proof_index=json.loads((R/'checks/STUDENT_AUDIT_TRIALS.json').read_text());known={x['trial_id'] for x in proof_index['entries']}; reproof={x['trial_id'] for x in proof_index['entries'] if x['trial_id'] in NFC_REGISTRY['cases'] and x.get('student_tokenizer_runtime_contract',{}).get('encoder_sha256')!=NFC_ENCODER}
  exports={}
  for scope in SCOPES:
   file=R/'checks'/(scope+'-actual-calls-export.json')
   if file.exists():exports.update({x['trial_id']:x for x in json.loads(file.read_text())})
  candidates=[]
  for pool in ['CALIBFORGE','TMAX']:
   for line in (R/'indexes'/(pool+'_FAILURE_OR_PENDING_INDEX.jsonl')).open():
    x=json.loads(line)
    if (x['classification']=='REWARD_ONE_NATIVE_COMPLETE_STUDENT_AUDIT_PENDING' or x['trial_id'] in reproof) and x['job_name'] in SCOPES and (x['trial_id'] not in known or x['trial_id'] in reproof) and x['trial_id'] not in pending and time.time()-errors.get(x['trial_id'],{}).get('last_failed_epoch',0)>=300:
     candidates.append(x)
  while candidates and len(pending)<MAX_PENDING:
   item=min(candidates,key=lambda x:(x['trial_id'] in errors,x['pool']!=next_pool,x['started_at'],x['trial_id']));candidates.remove(item)
   ident=item['trial_id'];next_pool='calibforge' if item['pool']=='tmax' else 'tmax'
   if ident not in exports:
    errors[ident]=dict(error_type='MISSING_IMMUTABLE_EXPORT',last_failed_epoch=time.time());continue
   pending[ident]=(executor.submit(audit_one,item,exports[ident]),item)
 while True:
  try:
   merged=False
   for ident,(future,item) in list(pending.items()):
    if not future.done():continue
    try:
     incoming=future.result()
     script('merge_student_proofs_nfc_r368.py',str(R),str(incoming),'stream-r12-'+ident)
     audited.add(ident);errors.pop(ident,None);merged=True
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
     errors[ident]=dict(error_type=type(error).__name__,error=str(error)[:800],last_failed_epoch=time.time())
    finally:del pending[ident]
   # Existing immutable exports and native-pending indexes are sufficient to
   # fill this bounded backlog before slow whole-campaign report scans.
   enqueue()
   changed=False
   for scope in SCOPES:
    base=R/'stream'/scope.removeprefix('stream-')
    if not (base/'CAMPAIGN.json').exists():continue
    signature=tuple(sorted((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in (base/'trials').glob('*/result.json')))
    if signature!=last_signature.get(scope):
     script('audit_native_canary_protocol_r216.py',scope);script('export_native_canary_calls_r187.py',scope)
     last_signature[scope]=signature;changed=True
   # One full qualification refresh per batch, retaining all per-Trial proofs.
   if merged or changed:
    script('audit_collection_results_r11.py')
    errors.pop('worker_observation',None)
   enqueue()
  except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
   errors['worker_observation']=dict(error_type=type(error).__name__,error=str(error)[:800])
  save('CPU_TARGET_AUDITS_RUNNING' if pending else 'IDLE_BETWEEN_OBSERVATIONS')
  time.sleep(30)

if __name__=='__main__':
 for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
 os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
 os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH']
 main()
