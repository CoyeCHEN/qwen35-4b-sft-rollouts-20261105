"""One finite public-asset preparation pass, using existing native Skopeo.

This is not a Harbor/teacher controller. Model credentials are removed from this
process. 149 remains the only task/agent/verifier engine. No daemon is changed.
"""
import datetime,json,os,shlex,shutil,subprocess,time
from pathlib import Path
from verify_public_oci import verify,file_sha
R=Path(__file__).resolve().parents[1]
REMOTE='/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/registry/tasks-local-skopeo-r1'
REMOTE_CODE='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029/scripts'
REMOTE_PYTHON='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
for key in ['DEEPSEEK_API_KEY','GH_TOKEN','GITHUB_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
rows=[json.loads(x) for x in (R/'manifests/CALIBFORGE_500_TASKS.jsonl').open()]
assert len(rows)==500 and len({x['task_id'] for x in rows})==500
existing149=json.loads((R/'checks/cf-public-prefetch-existing149-r2.json').read_text())
existing17=json.loads((R/'checks/cf-public-prefetch-existing17-r2.json').read_text())
plan_file=R/'manifests/CF_PUBLIC_OCI_PREFETCH_PLAN_R2.json'
if plan_file.exists():raise FileExistsError('Finite public-asset pass already registered; inspect before explicit resumption')
plan=dict(tasks=[dict(task_id=x['task_id'],source=json.loads((R/'checks/cf-public-image-identities'/(x['task_id']+'.json')).read_text())) for x in rows],
 existing149=existing149,existing17=existing17,model_calls=0,teacher_attempts=0,
 native_tool_version=subprocess.run(['skopeo','--version'],capture_output=True,text=True,check=True).stdout,
 native_tool_sha256=file_sha('/usr/bin/skopeo'),worker_count=1,archive_transfer_limit_kib_per_sec=8192)
parent_plan=R/'manifests/CF_PUBLIC_OCI_PREFETCH_PLAN_R1.json'
assert [x['task_id'] for x in plan['tasks']]==[x['task_id'] for x in json.loads(parent_plan.read_text())['tasks']]
plan['resume_parent_plan_sha256']=file_sha(parent_plan)
plan['reason']='User confirmed restored network; prior pass terminal after public blob EOF and nonessential observer SCP timeout. Original500 task/digest identities preserved.'
plan_file.write_text(json.dumps(plan,indent=2))
store=R/'sources/public-oci-shared-store-r1';root=R/'sources/public-oci-cache-r2'
def sync_observer(file):
 try:
  reply=subprocess.run(['scp','-q','-oBatchMode=yes','-oControlMaster=no','-oControlPath=none','-oConnectTimeout=8',str(file),
   'aibox-149:/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029/checks/cf-public-oci-prefetch.json'],capture_output=True,text=True,timeout=30,check=False)
  if reply.returncode:print(json.dumps(dict(status='NONESSENTIAL_OBSERVER_SYNC_UNOBSERVED',returncode=reply.returncode)),flush=True)
 except (OSError,subprocess.SubprocessError) as error:
  print(json.dumps(dict(status='NONESSENTIAL_OBSERVER_SYNC_UNOBSERVED',error_type=type(error).__name__)),flush=True)
observed=[];errors=[]
for row in sorted(plan['tasks'],key=lambda x:x['task_id']):
 ident=row['task_id'];source=row['source'];record=dict(task_id=ident,pinned=source['pinned'])
 started=time.monotonic()
 try:
  if ident in existing149:
   assert existing149[ident]['image_id']==source['top_manifest_digest']
   record['status']='ALREADY_PREPARED_ON_NATIVE_149'
  elif ident in existing17:
   assert existing17[ident]['pinned']==source['pinned']
   record['status']='ALREADY_STAGED_VERIFIED_PUBLIC_ARCHIVE_ON_17'
  else:
   if shutil.disk_usage(R).free<100*1024**3:raise RuntimeError('Local public-cache headroom below100GiB')
   directory=root/ident;directory.mkdir(parents=True,exist_ok=True);archive=directory/'image.oci.tar';receipt=directory/'cache.json'
   if not receipt.exists():
    with (directory/'prefetch-copy.log').open('x') as log:
     subprocess.run(['skopeo','copy','--preserve-digests','--retry-times','2','--src-no-creds',
      'docker://docker.io/'+source['pinned'],'oci:'+str(store)+':'+ident],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
     subprocess.run(['skopeo','copy','--preserve-digests','oci:'+str(store)+':'+ident,
      'oci-archive:'+str(archive)+':'+ident],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
    value=verify(source,archive)
    with receipt.open('x') as stream:stream.write(json.dumps(value,indent=2))
   else:
    value=json.loads(receipt.read_text());assert value['pinned']==source['pinned'] and value['archive_sha256']==file_sha(archive)
   destination=REMOTE+'/'+ident
   subprocess.run(['ssh','-oBatchMode=yes','ruc-a800-17','mkdir -p '+shlex.quote(destination)],check=True,timeout=30)
   subprocess.run(['rsync','-a','--bwlimit=8192',str(archive),'ruc-a800-17:'+destination+'/image.oci.tar'],check=True,timeout=1800)
   subprocess.run(['rsync','-a',str(receipt),'ruc-a800-17:'+destination+'/cache-origin.json'],check=True,timeout=60)
   staged=subprocess.run(['ssh','-oBatchMode=yes','ruc-a800-17',shlex.join([REMOTE_PYTHON,REMOTE_CODE+'/stage_public_oci_receipt_17.py',ident])],capture_output=True,text=True,check=True,timeout=120)
   record.update(status='EXACT_OFFICIAL_OCI_ARCHIVE_STAGED_ON_17',archive_sha256=value['archive_sha256'],native_receipt=staged.stdout.strip())
 except (OSError,ValueError,AssertionError,RuntimeError,subprocess.SubprocessError) as error:
  record.update(status='PUBLIC_ASSET_PREFETCH_FAILED',error_type=type(error).__name__,error=str(error)[:400]);errors.append(record)
 record['seconds']=time.monotonic()-started;observed.append(record)
 state=dict(status='PREFETCHING_FROZEN_PUBLIC_ASSETS',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
  pid=os.getpid(),planned_tasks=500,observed_tasks=len(observed),failed_assets=len(errors),records=observed,
  task_manifest_sha256=file_sha(R/'manifests/CALIBFORGE_500_TASKS.jsonl'),plan_sha256=file_sha(plan_file),
  model_calls=0,teacher_attempts=0,teacher_engine='Existing native RemoteDocker149 unchanged')
 file=R/'checks/cf-public-oci-prefetch.json';temporary=file.with_suffix('.tmp');temporary.write_text(json.dumps(state,indent=2));temporary.replace(file)
 if len(observed)%10==0 or record['status']=='PUBLIC_ASSET_PREFETCH_FAILED':
  sync_observer(file)
 print(json.dumps(record),flush=True)
state['status']='PUBLIC_ASSET_PREFETCH_FINISHED' if not errors else 'PUBLIC_ASSET_PREFETCH_PARTIAL_FAILURES_PRESERVED'
file.write_text(json.dumps(state,indent=2))
sync_observer(file)
