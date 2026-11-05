"""Finite native prechecks for original resident TMax tasks; zero model calls."""
import asyncio,datetime,fcntl,hashlib,json,os
from pathlib import Path
from uuid import uuid4
from harbor.trial.queue import TrialQueue
from harbor.models.job.config import RetryConfig
import run_collection_stream_r4 as c
from collection_readiness_r4 import basic_receipt,prepared,blocking_review,verify_nop
from native_image_archive149_r1 import image_info
R=c.R
S=R/'stream/tmax-resident-buffer-preflight-r1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def freeze(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:f.write(json.dumps(x,indent=2))
def read(p):return json.loads(p.read_text())
async def main():
 S.mkdir(parents=True,exist_ok=True);lock=(S/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 counts=c.attempt_counts();known=set()
 for scope in ['collection-r3','collection-r4','collection-r2']:
  known.update(p.stem for p in (R/'stream'/scope/'environment-outcomes').glob('*.json'))
 known.update(p.stem for p in (R/'checks/native-reserve-acceptance-r4').glob('*.json'))
 controller=read(R/'campaign-state.json');owned=set(controller.get('preparing_environments',[]))|set(controller.get('active_task_pipelines',[]))|set(controller.get('warming_images',[]))
 rows=[]
 for row in c.frozen_rows():
  ident=row['task_id']
  if row['pool']!='tmax' or counts.get(ident,0) or ident in known or ident in owned or blocking_review(ident):continue
  basic=basic_receipt(row)
  if basic is None or image_info(basic[1]['image_id']) is None:continue
  rows.append(row)
 freeze(S/'PLAN.json',dict(tasks=rows,source_sha256=sha(Path(__file__)),native_concurrency=2,model_calls=0,teacher_dispatches=0,
  selection='All original fixed active TMax tasks with accepted basic receipts, resident exact images, no teacher attempts or existing native acceptance; manifest order; no model outcome used',
  image_policy='Keep accepted images resident for the sole teacher controller; no image pulls, imports or global pruning'))
 c.S=S;queue=TrialQueue(n_concurrent=2,retry_config=RetryConfig(max_retries=0));results={};active=set();iterator=iter(rows)
 def state():
  x=dict(status='PREPARING_RESIDENT_TMAX_BUFFER' if active else 'BETWEEN_RESIDENT_PRECHECKS',pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),planned_tasks=len(rows),observed_tasks=len(results),active_task_ids=sorted(active),counts={k:list(results.values()).count(k) for k in set(results.values())},model_calls=0,teacher_dispatches=0)
  p=S/'state.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,indent=2));tmp.replace(p)
 async def one(row):
  ident=row['task_id'];out=dict(task_id=ident,pool='tmax',status='ENV_FAILED',model_calls=0,teacher_attempts=0)
  try:
   if c.attempt_counts().get(ident,0):raise ValueError('Task started elsewhere; no duplicate precheck')
   admitted=prepared(row,basic_receipt(row))
   if image_info(admitted['image_id']) is None:raise ValueError('Original image is no longer resident; no implicit import')
   for kind in ['install','nop']:
    cfg=c.native_config(admitted,kind);cfg.environment.kwargs['project_namespace']='cftmaxresidentbufferr120261030'
    if kind=='install':cfg.agent.env={}
    d=S/'dispatches'/str(uuid4());d.mkdir(parents=True);(d/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
    freeze(d/'dispatch.json',dict(task_id=ident,pool='tmax',kind=kind,trial_name=cfg.trial_name,config_sha256=sha(d/'trial-config.json'),model_calls=0))
    result=await queue.submit(cfg);trial=S/'trials'/cfg.trial_name
    out['native_'+kind+'_trial']=str(trial);out[kind+'_result_sha256']=sha(trial/'result.json')
    if result.exception_info or result.infrastructure_errors:raise ValueError('Native '+kind+' infrastructure failure')
    if kind=='nop':out['nop_reward']=verify_nop(result,trial,admitted)
   out.update(status='ENV_READY',admitted_task=admitted,teacher_success_not_implied=True)
  except Exception as error:out.update(error_type=type(error).__name__,reason=str(error)[:1000])
  raw=S/'environment-outcomes'/(ident+'.json');freeze(raw,out)
  if out['status']=='ENV_READY':
   freeze(R/'checks/native-reserve-acceptance-r4'/(ident+'.json'),dict(out,kind='ORIGINAL_SELECTED_TASK_NATIVE_ENVIRONMENT_ACCEPTANCE',raw_outcome=str(raw),raw_outcome_sha256=sha(raw),image_retained_for_teacher_buffer=True))
  results[ident]=out['status'];active.discard(ident);state()
 async def worker():
  while True:
   row=next(iterator,None)
   if row is None:return
   active.add(row['task_id']);state();await one(row)
 async with asyncio.TaskGroup() as group:
  for _ in range(2):group.create_task(worker())
 freeze(S/'TERMINAL.json',dict(status='FINITE_RESIDENT_PRECHECK_PASS_TERMINAL',planned_tasks=len(rows),observed_tasks=len(results),counts={k:list(results.values()).count(k) for k in set(results.values())},model_calls=0))
 state()
if __name__=='__main__':
 for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
 os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH'];os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
 asyncio.run(main())
