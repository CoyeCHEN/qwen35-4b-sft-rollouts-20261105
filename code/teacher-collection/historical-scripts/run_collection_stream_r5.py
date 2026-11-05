"""One native Harbor campaign: eight teacher lifecycles, bounded setup buffers.

Harbor owns environments, setup, agent execution, verification and collection.
AGENT_START/END hooks admit teachers only after installation and release their
permits after native finalization. No model transport or agent-loop changes.
"""
import asyncio
from collections import Counter
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
from uuid import uuid4

from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
from harbor.trial.hooks import TrialEvent
import run_collection_stream_r4 as c
from collection_readiness_r4 import basic_receipt, prepared, blocking_review, ensure_resident, release_cold_cache, verify_nop
from native_image_archive149_r1 import ImageCapacityError, image_info

R=c.R
S=R/'stream/collection-r4'

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2));tmp.replace(p)
def freeze(p,value):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:f.write(json.dumps(value,indent=2))
def event(kind,**fields):
 with (S/'teacher-lifecycle.jsonl').open('a') as f:f.write(json.dumps(dict(event=kind,observed_at=now(),**fields))+'\n')

async def main():
 S.mkdir(parents=True,exist_ok=True)
 lock=(R/'campaign-stream-controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if (S/'CAMPAIGN.json').exists():raise FileExistsError('Observe the existing campaign; never replay dispatches')
 assert read(R/'checks/CANARY_GATE.json')['passed']
 assert sha(R/'configs/teacher-native-11tools-summary-r1.json')==c.TEACHER_SHA
 if not os.environ.get('DEEPSEEK_API_KEY'):raise ValueError('Authorized service environment absent')
 for p in R.glob('stream/*/dispatches/*/dispatch.json'):
  d=read(p)
  if d['kind']=='teacher' and not (p.parents[2]/'trials'/d['trial_name']/'result.json').exists():raise ValueError('Outstanding teacher requires observation, not replay')
 sources={name:sha(R/'scripts'/name) for name in ['run_collection_stream_r5.py','run_collection_stream_r4.py','collection_readiness_r4.py','collection_selection_r4.py','native_image_archive149_r1.py','tmax_runtime_adapter.py']}
 manifest=dict(native_concurrency=8,source_sha256=sha(Path(__file__)),helper_sha256=sources,
  teacher_config_sha256=c.TEACHER_SHA,wheel_sha256=c.WHEEL_SHA,
  selected_manifest_sha256={n:sha(R/'manifests'/n) for n in c.MANIFESTS},
  native_staging_concurrency=12,hot_setup_buffer=4,native_preparation_concurrency=2,
  teacher_permit='Native AGENT_START after installation through native END after verifier, artifact collection and cleanup',
  task_slot_ids=sorted(x['task_id'] for x in c.original_rows()),
  authority='User2026-10-30: eight actual teachers; bounded independent preparation; unchanged1000/2000/2 caps',
  backend='149 native Remote Docker; future17 assignments require separately accepted immutable deployment evidence',
  attempt_counting='Teacher dispatch is frozen at AGENT_START after the global permit; setup-only failures retained separately without fabricated model attempts')
 freeze(S/'CAMPAIGN.json',manifest)
 active={};stages={};stage_rows={};prep={};warming={};releasing={};outcomes={};ready={};waits={};admitted_names=set()
 teacher_slots=asyncio.Semaphore(8);image_slot=asyncio.Semaphore(1);release_slots=asyncio.Semaphore(2)
 last_dispatch=None;next_pool='calibforge';last_end=None

 def validate_sources():
  if any(sha(R/'scripts'/n)!=h for n,h in sources.items()):raise ValueError('Frozen source changed')
  if sha(R/'configs/teacher-native-11tools-summary-r1.json')!=c.TEACHER_SHA:raise ValueError('Frozen teacher changed')
 def refresh(rows):
  selected={x['task_id'] for x in rows}
  paths=[]
  for scope in ['collection-r2','collection-r3']:
   paths.extend((R/'stream'/scope/'environment-outcomes').glob('*.json'))
  paths.extend((R/'checks/native-reserve-acceptance-r4').glob('*.json'))
  paths.extend((R/'checks/native-environment-reviews-r10').glob('*.json'))
  for p in paths:
   ident=p.stem
   if ident not in selected or ident in outcomes or blocking_review(ident):continue
   value=read(p)
   if value['status']!='ENV_READY':continue
   if 'raw_outcome' in value and sha(Path(value['raw_outcome']))!=value['raw_outcome_sha256']:raise ValueError('Accepted native proof changed')
   if 'admitted_task' not in value:
    basic=basic_receipt(next(x for x in rows if x['task_id']==ident))
    if basic is None:continue
    value=dict(value,admitted_task=prepared(next(x for x in rows if x['task_id']==ident),basic))
   outcomes[ident]=value

 def config(row,kind):
  result=c.native_config(row,kind)
  # Native queue provides the global teacher gate; keep model/tool options.
  result.trials_dir=S/'trials'
  if row.get('deployment_assignment'):
   assignment=Path(row['deployment_assignment'])
   if sha(assignment)!=row['deployment_assignment_sha256']:raise ValueError('Frozen staged deployment changed')
   deployment=read(assignment);proof=Path(deployment['native_acceptance_proof'])
   if sha(proof)!=deployment['native_acceptance_proof_sha256']:raise ValueError('Native17 acceptance changed')
   accepted=read(proof)
   if accepted['node']!='17' or not accepted['environment_and_storage_accepted'] or accepted['teacher_config_sha256']!=c.TEACHER_SHA or accepted['wheel_sha256']!=c.WHEEL_SHA:raise ValueError('Unaccepted17 deployment')
   if deployment['task_id']!=row['task_id'] or deployment['admission'] not in ['ONE_REGISTERED_MODEL_CANARY','ACCEPTED_BULK']:raise ValueError('Unregistered17 task assignment')
   if deployment['admission']=='ACCEPTED_BULK' and not accepted.get('model_verifier_recorder_joint_accepted'):raise ValueError('17 joint acceptance pending')
   result.environment=result.environment.model_validate(deployment['environment'])
  return result

 async def admitted_teacher(e):
  nonlocal last_dispatch
  name=e.trial_name
  if name in active:return
  event('SETUP_READY_WAITING_FOR_TEACHER_SLOT',trial_name=name,task_id=stage_rows[name]['task_id'])
  await teacher_slots.acquire()
  try:
   validate_sources()
   if (S/'DRAIN_REQUESTED.json').exists():raise ValueError('Admission drained before agent run')
   row=stage_rows[name];counts=c.attempt_counts()
   if counts[row['task_id']]>=2 or sum(counts.values())>=2000:raise ValueError('Authorized teacher budget exhausted')
   current=next(x for x in c.frozen_rows() if x['slot_id']==row['slot_id'])
   if current['task_id']!=row['task_id']:raise ValueError('Sampling slot changed before agent admission')
   directory=S/'dispatches'/str(uuid4());directory.mkdir(parents=True)
   cfg=directory/'trial-config.json';cfg.write_text(e.config.model_dump_json(indent=2))
   selected=c.frozen_rows();digest=hashlib.sha256(json.dumps(selected,sort_keys=True).encode()).hexdigest()
   snapshot=S/'selection-snapshots'/(digest+'.json')
   if not snapshot.exists():freeze(snapshot,selected)
   last_dispatch=now()
   freeze(directory/'dispatch.json',dict(task_id=row['task_id'],pool=row['pool'],kind='teacher',trial_name=name,
    config_sha256=sha(cfg),admitted_task=row,teacher_config_sha256=c.TEACHER_SHA,wheel_sha256=c.WHEEL_SHA,
    selection_snapshot=str(snapshot),selection_snapshot_sha256=sha(snapshot),dispatched_at=last_dispatch))
   active[name]=dict(task_id=row['task_id'],pool=row['pool'],agent_admitted_at=last_dispatch)
   admitted_names.add(name)
   event('TEACHER_ADMITTED',trial_name=name,active_teacher_count=len(active),**active[name])
  except BaseException:
   teacher_slots.release();raise

 async def ended_teacher(e):
  nonlocal last_end
  name=e.trial_name
  if name in active:
   row=active.pop(name);last_end=now()
   event('TEACHER_FINALIZED',trial_name=name,task_id=row['task_id'],native_finished_at=e.result.finished_at.isoformat() if e.result.finished_at else None,
    reward=(e.result.verifier_result.rewards if e.result.verifier_result else None),exception=bool(e.result.exception_info),
    infrastructure_errors=bool(e.result.infrastructure_errors),active_teacher_count=len(active))
   teacher_slots.release()

 teacher_queue=TrialQueue(n_concurrent=12,retry_config=RetryConfig(max_retries=0))
 teacher_queue.add_hook(TrialEvent.AGENT_START,admitted_teacher)
 teacher_queue.add_hook(TrialEvent.END,ended_teacher)
 preparation_queue=TrialQueue(n_concurrent=2,retry_config=RetryConfig(max_retries=0))

 async def resident(row):
  ident=row['task_id']
  while True:
   try:
    async with image_slot:proof=await asyncio.to_thread(ensure_resident,row)
    save(S/'image-materializations'/(ident+'.json'),proof);waits.pop(ident,None);return
   except ImageCapacityError as error:
    waits[ident]=dict(kind='IMAGE_CAPACITY',reason=str(error),checked_at=now())
    if (S/'DRAIN_REQUESTED.json').exists():raise
    await asyncio.sleep(15)

 async def release(row):
  try:
   async with release_slots:proof=await asyncio.to_thread(release_cold_cache,row)
   save(S/'image-releases'/(row['task_id']+'.json'),proof)
  except Exception as error:save(S/'image-releases'/(row['task_id']+'.json'),dict(status='CACHE_RELEASE_REFUSED',reason=str(error)[:1000]))

 async def diagnostic(row,kind):
  cfg=config(row,kind)
  if kind=='install':cfg.agent.env={}
  directory=S/'dispatches'/str(uuid4());directory.mkdir(parents=True)
  (directory/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
  freeze(directory/'dispatch.json',dict(task_id=row['task_id'],pool=row['pool'],kind=kind,trial_name=cfg.trial_name,config_sha256=sha(directory/'trial-config.json'),model_calls=0))
  result=await preparation_queue.submit(cfg)
  return result,S/'trials'/cfg.trial_name

 async def prepare(row):
  admitted=None;ident=row['task_id']
  try:
   admitted=prepared(row,basic_receipt(row));await resident(admitted)
   result,installed=await diagnostic(admitted,'install')
   if result.exception_info or result.infrastructure_errors:raise ValueError('Native installation/lifecycle failure')
   result,nop=await diagnostic(admitted,'nop');reward=verify_nop(result,nop,admitted)
   value=dict(task_id=ident,pool=row['pool'],status='ENV_READY',admitted_task=admitted,native_install_trial=str(installed),native_nop_trial=str(nop),nop_reward=reward,teacher_success_not_implied=True)
   save(S/'environment-outcomes'/(ident+'.json'),value);outcomes[ident]=value
   ready[ident]=admitted
  except Exception as error:
   value=dict(task_id=ident,pool=row['pool'],status='ENV_FAILED',reason=str(error)[:1000],error_type=type(error).__name__)
   save(S/'environment-outcomes'/(ident+'.json'),value);outcomes[ident]=value
   if admitted:releasing[ident]=asyncio.create_task(release(admitted))

 async def warm(row):
  admitted=dict(outcomes[row['task_id']]['admitted_task']);admitted['slot_id']=row['slot_id']
  try:await resident(admitted);ready[row['task_id']]=admitted
  except Exception as error:waits[row['task_id']]=dict(kind='IMAGE_MATERIALIZATION_FAILED',reason=str(error)[:1000],checked_at=now())

 async def stage(row):
  ident=row['task_id'];row=dict(row)
  assignment=R/'manifests/runtime-deployments17-r1'/(ident+'.json')
  if assignment.exists():
   deployment=read(assignment)
   row.update(deployment_assignment=str(assignment),deployment_assignment_sha256=sha(assignment))
   row.update(deployment['admitted_task_identity'])
   if row['task_id']!=ident:raise ValueError('Deployment changed Task identity')
  cfg=config(row,'teacher');stage_rows[cfg.trial_name]=row
  directory=S/'staging-dispatches'/str(uuid4());directory.mkdir(parents=True)
  (directory/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
  freeze(directory/'setup.json',dict(task_id=ident,pool=row['pool'],trial_name=cfg.trial_name,config_sha256=sha(directory/'trial-config.json'),model_calls_before_admission=0))
  try:
   result=await teacher_queue.submit(cfg)
   if cfg.trial_name not in admitted_names:
    value=dict(task_id=ident,pool=row['pool'],status='ENV_FAILED',reason='Native teacher setup failed before model admission; raw native Result retained',native_result=str(S/'trials'/cfg.trial_name/'result.json'),model_calls=0)
    save(S/'environment-outcomes'/(ident+'.json'),value);outcomes[ident]=value
  except Exception as error:save(S/'errors'/(ident+'-teacher.json'),dict(reason=str(error)[:1000]))
  finally:
   releasing[ident]=asyncio.create_task(release(row))
   stage_rows.pop(cfg.trial_name,None)

 last_state=0
 while True:
  for mapping in [stages,prep,warming,releasing]:
   for ident,task in list(mapping.items()):
    if task.done():
     try:task.result()
     except Exception as error:waits[ident]=dict(kind='TASK_OBSERVATION_ERROR',reason=str(error)[:1000],checked_at=now())
     del mapping[ident]
  rows=c.frozen_rows();refresh(rows);counts=c.attempt_counts();second=c.audited_second_attempts()
  owned=set(stages)|set(prep)|set(warming)|set(releasing)
  eligible=[x for x in rows if not blocking_review(x['task_id']) and outcomes.get(x['task_id'],{}).get('status')=='ENV_READY'
   and (counts[x['task_id']]==0 or (counts[x['task_id']]==1 and x['task_id'] in second))]
  eligible_ids={x['task_id'] for x in eligible}
  for ident in list(ready):
   if ident not in eligible_ids and ident not in owned:
    releasing[ident]=asyncio.create_task(release(ready.pop(ident)));owned.add(ident)
  draining=(S/'DRAIN_REQUESTED.json').exists()
  if not draining:
   # Already-resident accepted tasks are admitted before any cold preparation.
   candidates=[x for x in eligible if x['task_id'] not in owned]
   for row in candidates:
    ident=row['task_id']
    if ident in ready:continue
    admitted=dict(outcomes[ident]['admitted_task']);admitted['slot_id']=row['slot_id']
    if await asyncio.to_thread(image_info,admitted['image_id']) is not None:ready[ident]=admitted
   for _ in range(12-len(stages)):
    choices=[x for x in eligible if x['task_id'] in ready and x['task_id'] not in owned]
    if not choices:break
    row=next((x for x in choices if x['pool']==next_pool),choices[0]);ident=row['task_id']
    admitted=ready.pop(ident);stages[ident]=asyncio.create_task(stage(admitted));owned.add(ident)
    next_pool='tmax' if row['pool']=='calibforge' else 'calibforge'
   for row in candidates:
    ident=row['task_id']
    if len(warming)>=2 or len(ready)>=8:break
    if ident in owned or ident in ready:continue
    warming[ident]=asyncio.create_task(warm(row));owned.add(ident)
   # Fresh environments use their own bounded native queue and never occupy
   # the eight teacher permits. Existing accepted buffers take priority.
   for row in rows:
    if len(prep)>=2:break
    ident=row['task_id']
    if ident in owned or ident in outcomes or basic_receipt(row) is None:continue
    prep[ident]=asyncio.create_task(prepare(row));owned.add(ident)
  if draining and not stages and not prep and not warming:
   freeze(S/'DRAINED.json',dict(status='DRAINED_WITH_NO_ACTIVE_TEACHERS',checked_at=now()));return
  loop=asyncio.get_running_loop()
  if loop.time()-last_state>=2:
   reasons=[]
   if len(active)<8:
    for slot in range(len(active),8):
     reason=('CLI_SETUP_OR_NATIVE_AGENT_GATE' if len(stages)>len(active) else 'READY_ENVIRONMENT_IMAGE_NOT_YET_RESIDENT' if warming else 'INSUFFICIENT_AUDITED_ELIGIBLE_READY_TASKS')
     reasons.append(dict(slot=slot+1,reason=reason))
   save(R/'campaign-state.json',dict(status='DRAINING_NATIVE_TEACHERS' if draining else 'STREAMING_NATIVE_TEACHER_SLOTS',pid=os.getpid(),campaign_scope='collection-r4',controller_revision='r5',checked_at=now(),native_concurrency=8,
    actual_teacher_trials=len(active),active_teacher_trials=active,active_task_pipelines=list(stages),
    teacher_setup_or_gate_waiting=max(0,len(stages)-len(active)),teacher_native_staging=len(stages),ready_buffer=len(ready),
    eligible_native_ready_tasks=len(eligible),preparing_environments=list(prep),warming_images=list(warming),image_waits=waits,
    empty_teacher_slots=reasons,last_teacher_dispatch_at=last_dispatch,last_teacher_finalized_at=last_end,
    submitted_attempts=sum(counts.values()),teacher_independent_tasks=len(counts),environment_outcomes=dict(Counter(x['status'] for x in outcomes.values())),
    teacher_tasks_cap=1000,complete_attempts_cap=2000,per_task_attempts_cap=2,teacher_config_sha256=c.TEACHER_SHA,wheel_sha256=c.WHEEL_SHA,
    corpus_freeze='PENDING_ALL_TASKS_AND_TARGET_AUDITS'))
   last_state=loop.time()
  await asyncio.sleep(.5)

if __name__=='__main__':
 os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH']
 os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
 async def entry():
  task=asyncio.current_task();asyncio.get_running_loop().add_signal_handler(signal.SIGTERM,task.cancel)
  await main()
 asyncio.run(entry())
