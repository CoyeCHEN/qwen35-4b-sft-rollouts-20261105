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
import subprocess
from uuid import uuid4

from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
from harbor.trial.hooks import TrialEvent
import run_collection_stream_r4 as c
from collection_attempts_r6 import attempt_counts
from collection_readiness_r6 import D, DEPLOYMENT, CONFIG, CONFIG_SHA, choose, find_basic as basic_receipt, prepare_identity, initial, native_config, blocking_review, ensure_resident, release_cold_cache, verify_nop
from collection_readiness_r6 import image_info, archive_trial
from native_image_archive149_r1 import ImageCapacityError

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
 D.mkdir(parents=True,exist_ok=True)
 # The authorized writer remains on149 during this handoff. This lock is not
 # advertised as a distributed lock: other hosts are explicitly forbidden.
 if Path('/etc/machine-id').read_text().strip()!=DEPLOYMENT['controller_machine_id']:raise ValueError('Dispatch authority is bound to the declared controller host')
 lock=(R/'campaign-dispatch-authority-r6.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if (D/'CAMPAIGN.json').exists():raise FileExistsError('Observe the existing revision; no implicit replay')
 fence=read(R/'checks/controller-r5-admission-fence-r6.json')
 if sha(S/'DRAIN_REQUESTED.json')!=fence['drain_request_sha256']:raise ValueError('Old admission fence changed')
 if not fence['old_native_admission_disabled']:raise ValueError('Old controller still has dispatch authority')
 assert read(R/'checks/CANARY_GATE.json')['passed']
 assert sha(R/'configs/teacher-native-11tools-summary-r1.json')==c.TEACHER_SHA
 if not os.environ.get('DEEPSEEK_API_KEY'):raise ValueError('Authorized service environment absent')
 inherited=set(fence['inherited_teacher_trial_names'])
 for p in R.glob('stream/*/dispatches/*/dispatch.json'):
  d=read(p)
  if d['kind']=='teacher' and not (p.parents[2]/'trials'/d['trial_name']/'result.json').exists() and d['trial_name'] not in inherited:raise ValueError('Outstanding teacher outside the explicit native handoff')
 sources={name:sha(R/'scripts'/name) for name in ['run_collection_stream_r6.py','run_collection_stream_r4.py','collection_attempts_r6.py','collection_readiness_r6.py','collection_readiness_r4.py','collection_selection_r4.py','native_image_archive149_r1.py','tmax_runtime_adapter.py']}
 manifest=dict(native_concurrency=8,source_sha256=sha(Path(__file__)),helper_sha256=sources,
  teacher_config_sha256=c.TEACHER_SHA,wheel_sha256=c.WHEEL_SHA,
  selected_manifest_sha256={n:sha(R/'manifests'/n) for n in c.MANIFESTS},
  native_staging_concurrency=12,hot_setup_buffer=4,native_preparation_concurrency=2,
  teacher_permit='Native AGENT_START after installation through native END after verifier, artifact collection and cleanup',
  task_slot_ids=sorted(x['task_id'] for x in c.original_rows()),
  authority='User2026-10-30: eight actual teachers; bounded independent preparation; unchanged1000/2000/2 caps',
  backend='All newly admitted tasks use Campaign17 private SSD deployment before any image operation',
  deployment_config=str(CONFIG),deployment_config_sha256=CONFIG_SHA,
  attempt_reconciliation=str(R/'checks/attempt-environment-only-reconciliation-r6.json'),attempt_reconciliation_sha256=sha(R/'checks/attempt-environment-only-reconciliation-r6.json'),
  legacy_reader_hold='Four proved environment-only failures excluded from actual counts; additional model attempts for these IDs wait while old configuration-count readers are active',
  handoff_fence=str(R/'checks/controller-r5-admission-fence-r6.json'),handoff_fence_sha256=sha(R/'checks/controller-r5-admission-fence-r6.json'),
  attempt_counting='Teacher dispatch is frozen at AGENT_START after the global permit; setup-only failures retained separately without fabricated model attempts')
 freeze(D/'CAMPAIGN.json',manifest)
 freeze(R/'checks/CURRENT_DISPATCH_AUTHORITY_R6.json',dict(pid=os.getpid(),controller_revision='r6',controller_node='149',state_path=str(D/'state.json'),manifest=str(D/'CAMPAIGN.json'),manifest_sha256=sha(D/'CAMPAIGN.json'),previous_controller_native_lifecycle_only=True,teacher_global_cap=8))
 active={};stages={};stage_rows={};prep={};warming={};releasing={};archiving={};outcomes={p.stem:read(p) for p in (D/'preflight-failures').glob('*.json')};ready={};waits={};admitted_names=set();blocked_ready_receipts={}
 teacher_slots=asyncio.Semaphore(8);image_slot=asyncio.Semaphore(1);release_slots=asyncio.Semaphore(2);archive_slots=asyncio.Semaphore(2)
 last_dispatch=None;next_pool='calibforge';next_prepare_pool='calibforge';last_end=None

 def inherited_active():
  finalized=set()
  for line in (S/'teacher-lifecycle.jsonl').open():
   value=json.loads(line)
   if value['event']=='TEACHER_FINALIZED':finalized.add(value['trial_name'])
  return inherited-finalized

 def inherited_owned():
  # Include pre-install/gate waits until their native Result is written.
  return {name for name in fence['inherited_native_trial_names'] if not (S/'trials'/name/'result.json').exists()}

 def validate_sources():
  if any(sha(R/'scripts'/n)!=h for n,h in sources.items()):raise ValueError('Frozen source changed')
  if sha(R/'configs/teacher-native-11tools-summary-r1.json')!=c.TEACHER_SHA:raise ValueError('Frozen teacher changed')
 def refresh(rows):
  selected={x['task_id'] for x in rows}
  paths=sorted((D/'environment-outcomes').glob('*.json'))+sorted((D/'ready-revisions').glob('*/*.json'))
  for p in paths:
   value=read(p)
   ident=value['task_id']
   if ident not in selected or blocking_review(ident):continue
   if value['status']!='ENV_READY':continue
   if blocked_ready_receipts.get(ident)==sha(p):continue
   if 'raw_outcome' in value and sha(Path(value['raw_outcome']))!=value['raw_outcome_sha256']:raise ValueError('Accepted native proof changed')
   if value.get('engine_id')!=DEPLOYMENT['runtime']['engine_id'] or value.get('deployment_config_sha256')!=CONFIG_SHA:raise ValueError('Ready evidence belongs to a different deployment')
   if sha(Path(value['placement']))!=value['placement_sha256']:raise ValueError('Ready placement binding changed')
   for kind in ['install','nop']:
    if sha(Path(value['native_'+kind+'_trial'])/'result.json')!=value[kind+'_result_sha256']:raise ValueError('Native17 acceptance Result changed')
   if outcomes.get(ident,{}).get('status')=='ENV_READY' and outcomes[ident].get('placement_sha256')!=value['placement_sha256']:raise ValueError('Accepted current Task placement changed')
   outcomes[ident]=dict(value,accepted_ready_receipt=str(p),accepted_ready_receipt_sha256=sha(p))

 def config(row,kind):
  if sha(Path(row['deployment_assignment']))!=row['deployment_assignment_sha256']:raise ValueError('Frozen backend binding changed')
  return native_config(row,kind)

 async def admitted_teacher(e):
  nonlocal last_dispatch
  name=e.trial_name
  if name in active:return
  event('SETUP_READY_WAITING_FOR_TEACHER_SLOT',trial_name=name,task_id=stage_rows[name]['task_id'])
  await teacher_slots.acquire()
  try:
   # Old controller has no new-admission authority. Its healthy native Trials
   # retain global permits until their original END hooks finish cleanup.
   while len(active)+len(inherited_active())>=8:await asyncio.sleep(.25)
   validate_sources()
   if (D/'DRAIN_REQUESTED.json').exists():raise ValueError('Admission drained before agent run')
   row=stage_rows[name];counts=attempt_counts()
   if c.attempt_counts()[row['task_id']]>=2:raise ValueError('Proved actual ledger retained; task held until frozen legacy configuration-count readers retire')
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
   event('TEACHER_ADMITTED',trial_name=name,active_teacher_count=len(active)+len(inherited_active()),controller_revision='r6',runtime_node='17',runtime_engine_id=DEPLOYMENT['runtime']['engine_id'],**active[name])
  except BaseException:
   teacher_slots.release();raise

 async def ended_teacher(e):
  nonlocal last_end
  name=e.trial_name
  if name in active:
   row=active.pop(name);last_end=now()
   event('TEACHER_FINALIZED',trial_name=name,task_id=row['task_id'],native_finished_at=e.result.finished_at.isoformat() if e.result.finished_at else None,
    reward=(e.result.verifier_result.rewards if e.result.verifier_result else None),exception=bool(e.result.exception_info),
    infrastructure_errors=bool(e.result.infrastructure_errors),active_teacher_count=len(active)+len(inherited_active()),controller_revision='r6')
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
    if (D/'DRAIN_REQUESTED.json').exists():raise
    await asyncio.sleep(15)

 async def release(row):
  try:
   async with release_slots:proof=await asyncio.to_thread(release_cold_cache,row)
   save(S/'image-releases'/(row['task_id']+'.json'),proof)
  except Exception as error:save(S/'image-releases'/(row['task_id']+'.json'),dict(status='CACHE_RELEASE_REFUSED',reason=str(error)[:1000]))

 async def persist_trial(trial):
  try:
   async with archive_slots:proof=await asyncio.to_thread(archive_trial,trial)
   freeze(D/'ssd-trial-archives'/(trial.name+'.json'),proof)
  except Exception as error:save(D/'archive-errors'/(trial.name+'.json'),dict(reason=str(error)[:1400],native_raw_mirror_preserved=True))

 async def diagnostic(row,kind):
  cfg=config(row,kind)
  if kind=='install':cfg.agent.env={}
  directory=S/'dispatches'/str(uuid4());directory.mkdir(parents=True)
  (directory/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
  freeze(directory/'dispatch.json',dict(task_id=row['task_id'],pool=row['pool'],kind=kind,trial_name=cfg.trial_name,config_sha256=sha(directory/'trial-config.json'),model_calls=0))
  result=await preparation_queue.submit(cfg)
  archiving[cfg.trial_name]=asyncio.create_task(persist_trial(S/'trials'/cfg.trial_name))
  return result,S/'trials'/cfg.trial_name

 async def prepare(row):
  admitted=None;ident=row['task_id']
  try:
   admitted=prepare_identity(row);await resident(admitted)
   initial_proof=await asyncio.to_thread(initial,admitted)
   freeze(D/'initial-outcomes'/(ident+'.json'),initial_proof)
   result,installed=await diagnostic(admitted,'install')
   if result.exception_info or result.infrastructure_errors:raise ValueError('Native installation/lifecycle failure')
   result,nop=await diagnostic(admitted,'nop');reward=verify_nop(result,nop,admitted)
   value=dict(task_id=ident,pool=row['pool'],status='ENV_READY',admitted_task=admitted,native_install_trial=str(installed),native_nop_trial=str(nop),nop_reward=reward,teacher_success_not_implied=True,
    engine_id=DEPLOYMENT['runtime']['engine_id'],deployment_config_sha256=CONFIG_SHA,placement=admitted['deployment_assignment'],placement_sha256=admitted['deployment_assignment_sha256'],
    install_result_sha256=sha(installed/'result.json'),nop_result_sha256=sha(nop/'result.json'))
   freeze(D/'environment-outcomes'/(ident+'.json'),value);outcomes[ident]=value
   if len(ready)<16:ready[ident]=admitted
   else:releasing[ident]=asyncio.create_task(release(admitted))
  except Exception as error:
   value=dict(task_id=ident,pool=row['pool'],status='ENV_FAILED',reason=str(error)[:1000],error_type=type(error).__name__)
   freeze(D/'environment-failures'/(ident+'.json'),value)
   if outcomes.get(ident,{}).get('status')!='ENV_READY':outcomes[ident]=value
   if admitted:releasing[ident]=asyncio.create_task(release(admitted))

 async def warm(row):
  admitted=dict(outcomes[row['task_id']]['admitted_task']);admitted['slot_id']=row['slot_id']
  try:await resident(admitted);ready[row['task_id']]=admitted
  except Exception as error:waits[row['task_id']]=dict(kind='IMAGE_MATERIALIZATION_FAILED',reason=str(error)[:1000],checked_at=now())

 async def stage(row):
  ident=row['task_id'];row=dict(row)
  cfg=config(row,'teacher');stage_rows[cfg.trial_name]=row
  directory=S/'staging-dispatches'/str(uuid4());directory.mkdir(parents=True)
  (directory/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
  freeze(directory/'setup.json',dict(task_id=ident,pool=row['pool'],trial_name=cfg.trial_name,config_sha256=sha(directory/'trial-config.json'),model_calls_before_admission=0))
  try:
   result=await teacher_queue.submit(cfg)
   archiving[cfg.trial_name]=asyncio.create_task(persist_trial(S/'trials'/cfg.trial_name))
   if cfg.trial_name not in admitted_names:
    value=dict(task_id=ident,pool=row['pool'],status='ENV_FAILED',reason='Native teacher setup failed before model admission; raw native Result retained',native_result=str(S/'trials'/cfg.trial_name/'result.json'),model_calls=0)
    freeze(D/'setup-failures'/(cfg.trial_name+'.json'),value)
    prior=outcomes.get(ident,{})
    blocked_ready_receipts[ident]=prior.get('accepted_ready_receipt_sha256',sha(D/'environment-outcomes'/(ident+'.json')))
    outcomes[ident]=dict(value,status='ENV_BLOCKED',reason='Native setup failed; retain old readiness and wait for new validated Ready evidence before another setup')
  except Exception as error:save(S/'errors'/(ident+'-teacher.json'),dict(reason=str(error)[:1000]))
  finally:
   releasing[ident]=asyncio.create_task(release(row))
   stage_rows.pop(cfg.trial_name,None)

 last_state=0
 while True:
  for mapping in [stages,prep,warming,releasing,archiving]:
   for ident,task in list(mapping.items()):
    if task.done():
     try:task.result()
     except Exception as error:waits[ident]=dict(kind='TASK_OBSERVATION_ERROR',reason=str(error)[:1000],checked_at=now())
     del mapping[ident]
  rows=c.frozen_rows();refresh(rows);counts=attempt_counts();legacy_counts=c.attempt_counts();second=c.audited_second_attempts()
  inherited_ids={fence['native_trial_task_ids'][n] for n in inherited_owned()}
  prime_ids={x['task_id'] for x in read(D/'PREFLIGHT_PLAN.json')['tasks']} if not (D/'PREFLIGHT_TERMINAL.json').exists() else set()
  owned=set(stages)|set(prep)|set(warming)|set(releasing)|inherited_ids|prime_ids
  eligible=[x for x in rows if not blocking_review(x['task_id']) and outcomes.get(x['task_id'],{}).get('status')=='ENV_READY'
   and legacy_counts[x['task_id']]<2
   and (counts[x['task_id']]==0 or (counts[x['task_id']]==1 and x['task_id'] in second))]
  eligible_ids={x['task_id'] for x in eligible}
  for ident in list(ready):
   if ident not in eligible_ids and ident not in owned:
    releasing[ident]=asyncio.create_task(release(ready.pop(ident)));owned.add(ident)
  draining=(D/'DRAIN_REQUESTED.json').exists()
  if not draining:
   # Already-resident accepted tasks are admitted before any cold preparation.
   candidates=[x for x in eligible if x['task_id'] not in owned]
   for row in candidates:
    if len(ready)>=16:break
    ident=row['task_id']
    if ident in ready:continue
    admitted=dict(outcomes[ident]['admitted_task']);admitted['slot_id']=row['slot_id']
    if await asyncio.to_thread(image_info,admitted['image_id']) is not None:ready[ident]=admitted
   for _ in range(12-len(stages) if len(archiving)<16 else 0):
    choices=[x for x in eligible if x['task_id'] in ready and x['task_id'] not in owned]
    if not choices:break
    row=next((x for x in choices if x['pool']==next_pool),choices[0]);ident=row['task_id']
    admitted=ready.pop(ident);stages[ident]=asyncio.create_task(stage(admitted));owned.add(ident)
    next_pool='tmax' if row['pool']=='calibforge' else 'calibforge'
   for row in candidates:
    ident=row['task_id']
    if len(warming)>=2 or len(ready)>=16:break
    if ident in owned or ident in ready:continue
    warming[ident]=asyncio.create_task(warm(row));owned.add(ident)
   # Fresh environments use their own bounded native queue and never occupy
   # the eight teacher permits. Existing accepted buffers take priority.
   fresh=[row for row in rows if row['task_id'] not in owned and row['task_id'] not in outcomes and counts[row['task_id']]<2 and (not counts[row['task_id']] or row['task_id'] in second) and not blocking_review(row['task_id']) and basic_receipt(row) is not None]
   while fresh and len(prep)<2:
    row=next((x for x in fresh if x['pool']==next_prepare_pool),fresh[0]);fresh.remove(row);ident=row['task_id']
    prep[ident]=asyncio.create_task(prepare(row));owned.add(ident);next_prepare_pool='tmax' if row['pool']=='calibforge' else 'calibforge'
  if draining and not stages and not prep and not warming and not archiving:
   freeze(D/'DRAINED.json',dict(status='DRAINED_WITH_NO_ACTIVE_TEACHERS',checked_at=now()));return
  loop=asyncio.get_running_loop()
  if loop.time()-last_state>=2:
   reasons=[]
   total=len(active)+len(inherited_active())
   if total<8:
    for slot in range(total,8):
     reason=('CLI_SETUP_OR_NATIVE_AGENT_GATE' if len(stages)>len(active) else 'READY_ENVIRONMENT_IMAGE_NOT_YET_RESIDENT' if warming else 'INSUFFICIENT_AUDITED_ELIGIBLE_READY_TASKS')
     reasons.append(dict(slot=slot+1,reason=reason))
   combined=dict(active)
   for name in inherited_active():combined[name]=dict(fence['inherited_active_metadata'][name],controller_revision='r5',native_lifecycle_only=True)
   save(D/'state.json',dict(status='DRAINING_NATIVE_TEACHERS' if draining else 'STREAMING_NATIVE_TEACHER_SLOTS',pid=os.getpid(),campaign_scope='collection-r4',controller_revision='r6',checked_at=now(),native_concurrency=8,
    actual_teacher_trials=total,active_teacher_trials=combined,inherited_native_teacher_trials=len(inherited_active()),runtime_node='17',runtime_engine_id=DEPLOYMENT['runtime']['engine_id'],active_task_pipelines=list(stages),
    teacher_setup_or_gate_waiting=max(0,len(stages)-len(active)),teacher_native_staging=len(stages),ready_buffer=len(ready),
    eligible_native_ready_tasks=len(eligible),preparing_environments=list(prep),warming_images=list(warming),image_waits=waits,
    empty_teacher_slots=reasons,last_teacher_dispatch_at=last_dispatch,last_teacher_finalized_at=last_end,
    submitted_attempts=sum(counts.values()),teacher_independent_tasks=len(counts),environment_outcomes=dict(Counter(x['status'] for x in outcomes.values())),
    legacy_configuration_reservations=sum(legacy_counts.values()),proved_environment_only_reservations=sum(legacy_counts.values())-sum(counts.values()),legacy_reader_compatibility_holds=[ident for ident in legacy_counts if legacy_counts[ident]>=2 and counts[ident]<2],
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
