"""Accept the finite unchanged-context registry recoveries using native Harbor."""
import asyncio,datetime,fcntl,hashlib,json,os,shlex,subprocess,time
from pathlib import Path
from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
import accept_original_tmax_infra_recovery149_r7 as native
import run_collection_stream_r4 as c
R=c.R;S=R/'stream/tmax-original-registry-acceptance-r9'
SSH=['ssh','-S','/home/chenkeyi/.ssh/cf17-20261028.sock','-oBatchMode=yes','-oProxyCommand=false','chenkeyi@180.163.192.17']
PY17='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
REMOTE="""import datetime,hashlib,json,sys
from pathlib import Path
r=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
s=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/buildkit-rootless-r2/archives')
ident=sys.argv[1];old=s/ident/'client-proxy-r3/build.json';actual=s/ident/'registry-auth-recovery-r9/build.json'
if not actual.exists():print(json.dumps({'pending':True}));raise SystemExit
raw=actual.read_bytes();built=json.loads(raw);failed=json.loads(old.read_text())
if built['status']!='ORIGINAL_NATIVE_OCI_ARCHIVE_BUILT_INITIAL_AND_VERIFIER_TESTS_PENDING':print(json.dumps({'failed':True,'build':built}));raise SystemExit
assert built['source_context']==failed['source_context'] and built['source_context']['task_id']==ident
assert hashlib.sha256(Path(built['archive']).read_bytes()).hexdigest()==built['archive_sha256']
canonical=s/ident/'network-recovery-r5/build.json';canonical.parent.mkdir(exist_ok=True)
if canonical.exists():assert canonical.read_bytes()==raw
else:
 with canonical.open('xb') as f:f.write(raw)
entry=dict(kind='EXPLICIT_ORIGINAL_CONTEXT_NETWORK_RECOVERY',task_id=ident,original_failed_build_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),
 recovery_build_receipt=str(canonical),recovery_build_receipt_sha256=hashlib.sha256(raw).hexdigest(),
 actual_recovery_revision='registry-auth-r9',original_recovery_receipt=str(actual),original_recovery_receipt_sha256=hashlib.sha256(raw).hexdigest(),
 canonical_registration='Byte-identical immutable receipt under the existing native recovery reader contract; original R9 build/log/archive retained',model_calls=0)
registered=r/'checks/tmax-original-build-network-recovery-r5'/(ident+'.json');registered.parent.mkdir(exist_ok=True)
if registered.exists():assert json.loads(registered.read_text())==entry
else:
 with registered.open('x') as f:json.dump(entry,f,indent=2)
print(json.dumps({'build':built,'registration':entry,'original_build_log':(old.parent/'build.log').read_text()}))
"""
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def freeze(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(x,f,indent=2)
async def main():
 S.mkdir(parents=True,exist_ok=True);lock=(S/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 planfile=R/'manifests/TMAX_ORIGINAL_REGISTRY_EOF_RECOVERY_R9.json';plan=json.loads(planfile.read_text())
 if (S/'PLAN.json').exists():raise FileExistsError('Inspect the existing finite native acceptance; no replay')
 freeze(S/'PLAN.json',dict(source_plan_sha256=sha(planfile),tasks=plan['tasks'],source_sha256=sha(Path(__file__)),pid=os.getpid(),native_concurrency=1,model_calls=0,teacher_dispatches=0,reserved_private17_canary_task='task_007206_2ea22c7f'))
 native.S=S;queue=TrialQueue(n_concurrent=1,retry_config=RetryConfig(max_retries=0));pending={x['task_id']:x for x in plan['tasks']};results={}
 def state(stage,ident=None):
  x=dict(status=stage,pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),planned_tasks=len(plan['tasks']),observed_tasks=len(results),current_task_id=ident,counts={s:list(results.values()).count(s) for s in set(results.values())},model_calls=0,teacher_dispatches=0)
  p=S/'state.json';t=p.with_suffix('.tmp');t.write_text(json.dumps(x,indent=2));t.replace(p)
 while pending:
  for ident,entry in list(pending.items()):
   state('OBSERVING_REGISTERED_ORIGINAL_RECOVERY',ident)
   try:
    command=shlex.join([PY17,'-c',REMOTE,ident]);q=await asyncio.to_thread(subprocess.run,[*SSH,command],capture_output=True,text=True,timeout=90,check=True)
    response=json.loads(q.stdout)
    if response.get('pending'):continue
    if response.get('failed'):
     freeze(S/'build-failures'/(ident+'.json'),response);results[ident]='ENV_FAILED_ORIGINAL_REGISTRY_RECOVERY';del pending[ident];continue
    case=S/'source-evidence'/ident;case.mkdir(parents=True)
    freeze(case/'recovered-build.json',response['build']);freeze(case/'native-recovery-registration.json',response['registration'])
    log=case/'original-failed-build.log'
    with log.open('x') as f:f.write(response['original_build_log'])
    if ident=='task_007206_2ea22c7f':
     results[ident]='RESERVED_FOR_NATIVE17_CANARY_ACCEPTANCE';del pending[ident];continue
    initial=R/'checks/tmax-environments-ssd17-r7'/(ident+'.json')
    acceptance=dict(task_id=ident,original_preparation_failure=str(initial),original_preparation_failure_sha256=sha(initial),
      original_failed_build_log=str(log),original_failed_build_log_sha256=sha(log),native_build_receipt=response['registration']['recovery_build_receipt'])
    state('NATIVE_ORIGINAL_INITIAL_CLI_AND_VERIFIER_ACCEPTANCE',ident)
    outcome=await native.accept_one(acceptance,queue,response['build']);results[ident]=outcome['status'];del pending[ident]
   except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
    # Transport observation failures leave this same unattempted item pending;
    # completed native outcomes are never replayed.
    outcome=S/'environment-outcomes'/(ident+'.json')
    if outcome.exists():results[ident]=json.loads(outcome.read_text())['status'];del pending[ident]
    elif (S/'source-evidence'/ident).exists():
     freeze(outcome,dict(task_id=ident,pool='tmax',status='ENV_FAILED',error_type=type(error).__name__,reason=str(error)[:1200],model_calls=0,teacher_attempts=0))
     results[ident]='ENV_FAILED';del pending[ident]
    else:
     p=S/'observation-errors'/(ident+'.json');p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(dict(error_type=type(error).__name__,reason=str(error)[:1000])))
  state('WAITING_FOR_REMAINING_REGISTERED_RECOVERIES' if pending else 'FINITE_ORIGINAL_REGISTRY_ACCEPTANCE_TERMINAL')
  if pending:await asyncio.sleep(30)
if __name__=='__main__':
 for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
 os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH']
 os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
 asyncio.run(main())
