"""Finite original CF CLI/NOP preparation; no teacher dispatch or source edits."""
import asyncio,datetime,fcntl,hashlib,json,os
from pathlib import Path
from uuid import uuid4
from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
import run_collection_stream_r4 as contract
from collection_readiness_r4 import basic_receipt,prepared,ensure_resident,release_cold_cache,verify_nop,blocking_review
from collection_selection_r4 import active_rows
from native_image_archive149_r1 import ImageCapacityError

R=contract.R
S=R/'stream/environment-preflight-r5'
TEACHER_SHA=contract.TEACHER_SHA
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp')
 tmp.write_text(json.dumps(value,indent=2));tmp.replace(p)
def freeze(p,value):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:f.write(json.dumps(value,indent=2))
def controller_is_original():
 return read(R/'campaign-state.json')['pid']==611441 and not (R/'stream/collection-r4/CAMPAIGN.json').exists()
def eligible_rows():
 counts=contract.attempt_counts()
 dispatched={read(p)['task_id'] for p in R.glob('stream/*/dispatches/*/dispatch.json')}
 items=[]
 for row in active_rows(counts):
  ident=row['task_id']
  if row['pool']!='calibforge' or counts.get(ident,0) or ident in dispatched or blocking_review(ident):continue
  marker=R/'checks/cf-environments-oci-r5'/(ident+'.json')
  if not marker.exists() or read(marker)['status']!='IMAGE_BASIC_PASSED_CAPACITY_HOLD':continue
  if any((R/'checks'/folder/(ident+'.json')).exists() for folder in ['cf-environments-ssd17-r6','cf-environments-ssd17-recheck-r7','cf-reserve-environments-r1']):continue
  items.append(dict(row=row,marker=str(marker),marker_sha256=sha(marker)))
 return items

async def main():
 S.mkdir(parents=True,exist_ok=True)
 lock=(S/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if not controller_is_original():raise RuntimeError('Updated controller owns preparation; no parallel admission for its tasks')
 items=eligible_rows()
 freeze(S/'PLAN.json',dict(tasks=items,source_sha256=sha(Path(__file__)),model_calls=0,
  selection='All unattempted original CF tasks with the existing derived capacity-hold marker and no alternate ready receipt; no source tasks replaced',
  full_pool_slots=500,native_preparation_concurrency=2,native_retry=0,
  teacher_config_sha256=TEACHER_SHA,teacher_dispatches=0))
 queue=TrialQueue(n_concurrent=2,retry_config=RetryConfig(max_retries=0))
 residency=asyncio.Semaphore(1);inflight=set();results={};iterator=iter(items)
 contract.S=S
 def state():
  save(S/'state.json',dict(status='PREPARING_ORIGINAL_SELECTED_CF' if inflight else 'BETWEEN_NATIVE_PRECHECKS',
   pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
   planned_tasks=len(items),observed_tasks=len(results),active_task_ids=sorted(inflight),
   counts={key:list(results.values()).count(key) for key in set(results.values())},
   model_calls=0,teacher_dispatches=0,original_task_modifications=0))
 async def dispatch(admitted,kind):
  config=contract.native_config(admitted,kind)
  config.environment.kwargs['project_namespace']='cftmaxpreflightr520261030'
  if kind=='install':config.agent.env={}
  directory=S/'dispatches'/str(uuid4());directory.mkdir(parents=True)
  (directory/'trial-config.json').write_text(config.model_dump_json(indent=2))
  freeze(directory/'dispatch.json',dict(task_id=admitted['task_id'],pool='calibforge',kind=kind,
   trial_name=config.trial_name,config_sha256=sha(directory/'trial-config.json'),model_calls=0))
  result=await queue.submit(config)
  return result,S/'trials'/config.trial_name
 async def one(item):
  row=item['row'];ident=row['task_id'];marker=Path(item['marker']);before=marker.read_bytes()
  admitted=None;changed=False;proof=None
  outcome=dict(task_id=ident,pool='calibforge',status='ENV_FAILED',model_calls=0,teacher_attempts=0)
  try:
   if sha(marker)!=item['marker_sha256'] or contract.attempt_counts().get(ident,0):raise ValueError('Admission/marker changed; no duplicate task preparation')
   admitted=prepared(row,basic_receipt(row))
   archive=S/'capacity-marker-originals'/(ident+'.json');archive.parent.mkdir(exist_ok=True)
   with archive.open('xb') as f:f.write(before)
   working=read(marker)
   working.update(status='NATIVE_CLI_NOP_ACCEPTANCE_IN_PROGRESS',native_preflight_scope=str(S),
    saved_capacity_marker=str(archive),saved_capacity_marker_sha256=sha(archive))
   save(marker,working);changed=True
   if basic_receipt(row) is not None:raise ValueError('Task still exposed through another readiness path')
   while True:
    try:
     async with residency:await asyncio.to_thread(ensure_resident,admitted)
     break
    except ImageCapacityError:
     if not controller_is_original():
      outcome.update(status='ENV_CHECK_PENDING',reason='Hand off capacity-waiting task to the updated controller');return
     state();await asyncio.sleep(30)
   installed,install_trial=await dispatch(admitted,'install')
   if installed.exception_info or installed.infrastructure_errors:raise ValueError('Native CLI installation/lifecycle failed')
   verified,nop_trial=await dispatch(admitted,'nop')
   reward=verify_nop(verified,nop_trial,admitted)
   outcome.update(status='ENV_READY',admitted_task=admitted,native_install_trial=str(install_trial),native_nop_trial=str(nop_trial),
    install_result_sha256=sha(install_trial/'result.json'),nop_result_sha256=sha(nop_trial/'result.json'),
    nop_reward=reward,teacher_success_not_implied=True)
   proof=dict(task_id=ident,pool='calibforge',status='ENV_READY',admitted_task=admitted,
    kind='ORIGINAL_SELECTED_TASK_NATIVE_ENVIRONMENT_ACCEPTANCE',
    native_install_trial=str(install_trial),native_nop_trial=str(nop_trial),nop_reward=reward,
    original_verifier_logs=[dict(path=str(p),sha256=sha(p)) for p in (nop_trial/'verifier').glob('test-*.txt')],
    model_calls=0,teacher_attempts=0,teacher_success_not_implied=True)
  except Exception as error:
   outcome.update(error_type=type(error).__name__,reason=str(error)[:1000])
  finally:
   if admitted:
    try:
     async with residency:release=await asyncio.to_thread(release_cold_cache,admitted)
     save(S/'image-releases'/(ident+'.json'),release)
    except Exception as error:save(S/'image-releases'/(ident+'.json'),dict(status='CACHE_RELEASE_REFUSED',reason=str(error)[:800]))
   raw=S/'environment-outcomes'/(ident+'.json');freeze(raw,outcome)
   if proof:
    proof.update(raw_outcome=str(raw),raw_outcome_sha256=sha(raw),
     review_reason='Original CLI installation and official NOP verifier completed in the native149 backend; accepted setup only, no model success implied')
    freeze(R/'checks/native-reserve-acceptance-r4'/(ident+'.json'),proof)
   if changed:
    current=read(marker)
    if current.get('native_preflight_scope')!=str(S):raise ValueError('Derived admission marker ownership changed; preserve and inspect')
    temporary=marker.with_suffix('.restore-tmp');temporary.write_bytes(before);temporary.replace(marker)
   results[ident]=outcome['status'];inflight.discard(ident);state()
 async def worker():
  while controller_is_original():
   item=next(iterator,None)
   if item is None:return
   ident=item['row']['task_id'];inflight.add(ident);state()
   await one(item)
 async with asyncio.TaskGroup() as group:
  for _ in range(2):group.create_task(worker())
 save(S/'TERMINAL.json',dict(status='FINITE_PRECHECK_PASS_TERMINAL' if len(results)==len(items) else 'DEFERRED_REMAINING_TO_UPDATED_CONTROLLER',
  planned_tasks=len(items),observed_tasks=len(results),model_calls=0,teacher_dispatches=0))
 state()

if __name__=='__main__':
 for key in ['DEEPSEEK_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
 os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH']
 os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
 asyncio.run(main())

