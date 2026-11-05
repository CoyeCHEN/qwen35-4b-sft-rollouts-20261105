"""Finite original TMax image preparation on17 SSD; existing149 runtime gate stays."""
from pathlib import Path
import datetime,hashlib,json,os,shlex,subprocess,sys
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
E17='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029'
S17='/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/buildkit-rootless-r2'
SSH=['ssh','-S','/home/chenkeyi/.ssh/cf17-20261028.sock','-oBatchMode=yes','-oProxyCommand=false'];HOST='chenkeyi@180.163.192.17'
PY17='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
for key in ['DEEPSEEK_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
manifest=R/'manifests/TMAX_RUNTIME_CANDIDATES_V2.jsonl';rows=list(map(json.loads,manifest.open()))
# Freeze identities before this finite non-model pass; never add tasks or replace model failures.
rows=[r for r in rows if not (R/'checks/tmax-environments-runtime-r4'/(r['task_id']+'.json')).exists()]
plan=R/'manifests/TMAX_REMAINING_SSD17_R3.json'
if plan.exists():raise FileExistsError('Inspect existing finite prep pass before resumption')
plan.write_text(json.dumps(dict(task_ids=[r['task_id'] for r in rows],source_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),model_calls=0,worker_count=1,teacher_backend='149 unchanged'),indent=2))
records=[]
def run(args,**kw):return subprocess.run(args,check=True,**kw)
for row in reversed(rows):
 ident=row['task_id'];item=dict(task_id=ident)
 try:
  current=R/'checks/tmax-environments-runtime-r4'/(ident+'.json')
  if current.exists():item['status']='ORIGINAL_CANONICAL_PREPARATION_ALREADY_FINISHED'
  else:
   with (R/'logs/tmax-remaining-ssd17-contexts-r3.log').open('a') as log:
    run([sys.executable,str(R/'scripts/prepare_tmax_images_v2.py'),'--startup-recheck','--context-only','--task-id',ident],stdout=log,stderr=subprocess.STDOUT,timeout=300)
   meta=R/'checks/tmax-native-contexts-ssd17-r2'/(ident+'.json');source=json.loads(meta.read_text());dest=S17+'/contexts/'+ident
   run(SSH+[HOST,'mkdir -p '+shlex.quote(dest)],timeout=30)
   run(['rsync','-a','--bwlimit=8192','-e',shlex.join(SSH),source['actual_build_context']+'/',HOST+':'+dest+'/'],timeout=600)
   run(['rsync','-a','-e',shlex.join(SSH),str(meta),HOST+':'+S17+'/contexts/'+ident+'.context.json'],timeout=30)
   remote_receipt=S17+'/archives/'+ident+'/client-proxy-r3/build.json'
   existing=subprocess.run(SSH+[HOST,'test -f '+shlex.quote(remote_receipt)],capture_output=True,timeout=30)
   if existing.returncode==1:
    run(SSH+[HOST,shlex.join([PY17,E17+'/scripts/build_tmax_native_oci_ssd17_r3.py',ident])],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=3800)
   elif existing.returncode!=0:raise RuntimeError('Remote archive observation failed, not a missing archive')
   response=run(SSH+[HOST,'cat '+shlex.quote(remote_receipt)],capture_output=True,text=True,timeout=30)
   built=json.loads(response.stdout)
   if built['status']!='ORIGINAL_NATIVE_OCI_ARCHIVE_BUILT_INITIAL_AND_VERIFIER_TESTS_PENDING':raise ValueError('Original native build failed; full remote evidence retained')
   target=R/'checks/tmax-ssd17-archives-r2'/(ident+'.json');target.parent.mkdir(exist_ok=True)
   if target.exists():assert json.loads(target.read_text())==built
   else:
    with target.open('x') as stream:stream.write(response.stdout)
   item.update(status='NATIVE_OCI_ARCHIVE_READY_149_RUNTIME_ACCEPTANCE_PENDING',archive_sha256=built['archive_sha256'],archive_bytes=built['archive_bytes'])
 except (OSError,ValueError,AssertionError,subprocess.SubprocessError) as error:item.update(status='ORIGINAL_TASK_SSD_PREPARATION_FAILED',error_type=type(error).__name__,error=str(error)[:500])
 records.append(item)
 value=dict(status='PREPARING_REMAINING_ORIGINAL_TMAX_ON17_SSD',pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),planned_tasks=len(rows),observed_tasks=len(records),records=records,model_calls=0,environment_ready_not_implied=True)
 p=R/'checks/tmax-remaining-ssd17-r3.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2));tmp.replace(p)
 print(json.dumps(item),flush=True)
value['status']='FINITE_SSD_IMAGE_PREPARATION_TERMINAL';p.write_text(json.dumps(value,indent=2))
