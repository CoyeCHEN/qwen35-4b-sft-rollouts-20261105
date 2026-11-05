"""One finite retry of unchanged contexts blocked by registry HEAD or public Python-package TLS EOF."""
import collections,datetime,fcntl,hashlib,json,os,stat,subprocess,time,urllib.request
from pathlib import Path
from inspect_cold_oci_r1 import inspect_archive,sha_file
R=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def freeze(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(x,f,indent=2)
def main():
 lock=(R/'checks/tmax-original-network-recovery-r10.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 manifest=R/'manifests/TMAX_REMAINING_INITIAL_SSD17_R7.json'
 selected=json.loads(manifest.read_text())['tasks'];plan=R/'manifests/TMAX_ORIGINAL_NETWORK_EOF_RECOVERY_R10.json'
 if not plan.exists():
  entries=[]
  for row in selected:
   old=S/'buildkit-rootless-r2/archives'/row['task_id']/'client-proxy-r3'
   p=old/'build.json'
   if not p.exists():continue
   failed=json.loads(p.read_text());log=old/'build.log'
   if failed['status']=='NATIVE_SSD_BUILD_FAILED' and 'EOF' in log.read_text() and 'auth.docker.io/token' not in log.read_text() and ('registry-1.docker.io' in log.read_text() or 'files.pythonhosted.org' in log.read_text()):
    entries.append(dict(task_id=row['task_id'],original_build_receipt=str(p),original_build_receipt_sha256=sha_file(p),original_build_log=str(log),original_build_log_sha256=sha_file(log)))
  freeze(plan,dict(checked_at=now(),source_manifest=str(manifest),source_manifest_sha256=sha_file(manifest),tasks=entries,
   retry_limit_per_original_context=1,model_calls=0,task_replacements=0,source_sha256=sha_file(Path(__file__))))
 registered=json.loads(plan.read_text());assert sha_file(manifest)==registered['source_manifest_sha256']
 results={};auth_attempt=0
 def state(status,**fields):
  x=dict(status=status,pid=os.getpid(),checked_at=now(),planned_tasks=len(registered['tasks']),observed_tasks=len(results),counts=dict(collections.Counter(results.values())),model_calls=0,teacher_dispatches=0,task_replacements=0,**fields)
  p=R/'checks/tmax-original-network-recovery-r10.json';t=p.with_suffix('.tmp');t.write_text(json.dumps(x,indent=2));t.replace(p)
 for entry in registered['tasks']:
  ident=entry['task_id'];old=Path(entry['original_build_receipt']);dest=old.parent.parent/'registry-head-pip-recovery-r10'
  if (dest/'build.json').exists():results[ident]=json.loads((dest/'build.json').read_text())['status'];continue
  assert sha_file(old)==entry['original_build_receipt_sha256'] and sha_file(Path(entry['original_build_log']))==entry['original_build_log_sha256']
  failed=json.loads(old.read_text());context=S/'buildkit-rootless-r2/contexts'/ident
  actual=[dict(path=str(p.relative_to(context)),mode=stat.S_IMODE(p.stat().st_mode),sha256=sha_file(p)) for p in sorted(context.rglob('*')) if p.is_file()]
  assert actual==failed['source_context']['build_context_files']
  while True:
   auth_attempt+=1
   try:
    # No token body is retained. Public registry readiness is not a model call.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({'http':'http://127.0.0.1:7890','https':'http://127.0.0.1:7890'}))
    with opener.open('https://auth.docker.io/token?scope=repository%3Alibrary%2Fubuntu%3Apull&service=registry.docker.io',timeout=12) as reply:
     assert reply.status==200;reply.read()
    break
   except Exception as error:
    state('ENV_BLOCKED_REGISTRY_AUTH_TLS_WAITING',current_task_id=ident,registry_readiness_attempt=auth_attempt,last_registry_error=type(error).__name__+':'+str(error)[:350])
    time.sleep(300)
  dest.mkdir(exist_ok=False)
  command=failed['command'].copy()
  command[command.index('--output')+1]='type=oci,name=rsi-ssd-tmax-r2:'+ident+',dest='+str(dest/'image.oci.tar')
  command[command.index('--metadata-file')+1]=str(dest/'buildctl-metadata.json')
  item=dict(entry,source_context=failed['source_context'],command=command,checked_at=now(),source_sha256=sha_file(Path(__file__)),retry_limit=1,model_calls=0,original_files_modified=0)
  freeze(dest/'PLAN.json',item);started=time.monotonic();state('REBUILDING_UNCHANGED_ORIGINAL_CONTEXT',current_task_id=ident)
  try:
   with (dest/'build.log').open('x') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=3600)
   archive=dest/'image.oci.tar';digest=sha_file(archive)
   import tarfile
   with tarfile.open(archive) as tar:
    index=json.loads(tar.extractfile('index.json').read());descriptor,=index['manifests'];image=descriptor['digest']
   audit=inspect_archive(str(archive),image,digest);freeze(dest/'image-audit.json',audit)
   item.update(status='ORIGINAL_NATIVE_OCI_ARCHIVE_BUILT_INITIAL_AND_VERIFIER_TESTS_PENDING',archive=str(archive),archive_sha256=digest,archive_bytes=archive.stat().st_size,native_manifest_digest=image,all_manifest_config_layer_hashes_verified=True,full_manifest_config_layer_diffid_proof=str(dest/'image-audit.json'),full_manifest_config_layer_diffid_proof_sha256=sha_file(dest/'image-audit.json'))
  except Exception as error:item.update(status='ORIGINAL_REGISTRY_RECOVERY_FAILED',error_type=type(error).__name__,error=str(error)[:1200])
  item['seconds']=time.monotonic()-started;freeze(dest/'build.json',item);results[ident]=item['status']
  state('BETWEEN_FINITE_ORIGINAL_CONTEXT_RECOVERIES')
 state('FINITE_ORIGINAL_REGISTRY_CONTEXT_RECOVERY_TERMINAL')
if __name__=='__main__':
 for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
 os.environ['HTTP_PROXY']=os.environ['HTTPS_PROXY']='http://127.0.0.1:7890'
 main()
