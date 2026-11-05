"""Finite zero-model native CLI/official-verifier acceptance on the SSD engine."""
import asyncio,datetime,fcntl,hashlib,json,os
from pathlib import Path
from uuid import uuid4
from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
import run_collection_stream_r4 as c
from collection_readiness_r4 import prepared,verify_nop,blocking_review

R=c.R;S=R/'stream/private17-native-acceptance-r1';ID='task_007016_4f9de434'
SOCKET='/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/engine17-r1/socket/docker.sock'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def freeze(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,indent=2)
async def main():
 S.mkdir(parents=True,exist_ok=True);lock=(S/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if (S/'PLAN.json').exists():raise FileExistsError('Inspect existing native acceptance; no replay')
 assert not c.attempt_counts().get(ID,0) and not blocking_review(ID)
 resource=R/'checks/private-ssd-engine17-original-resource-acceptance-r2.json';basic=json.loads(resource.read_text())
 assert basic['status']=='ORIGINAL_TASK_RESOURCES_INITIAL_STATE_AND_NETWORK_ACCEPTED_NATIVE_CLI_NOP_PENDING' and basic['cleanup_confirmed']
 row=next(x for x in c.frozen_rows() if x['task_id']==ID);row['slot_id']=ID
 admitted=prepared(row,(resource,basic))
 environment=dict(import_path='harbor_remote_docker:RemoteDockerEnvironment',delete=True,force_build=False,
  kwargs=dict(endpoint='ssh://chenkeyi@180.163.192.17:22',remote_socket_path=SOCKET,
  staging_root='/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/staging-private-engine17-r1',
  project_namespace='cftmaxprivate17r120261030',agent_runtime_volume=True,verifier_test_volume=True))
 freeze(S/'PLAN.json',dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=os.getpid(),source_sha256=sha(Path(__file__)),
  task_id=ID,model_calls=0,teacher_dispatches=0,original_resources=basic['task_resources'],engine_id=basic['engine_id'],
  resource_acceptance=str(resource),resource_acceptance_sha256=sha(resource),environment=environment,
  teacher_config_sha256=c.TEACHER_SHA,wheel_sha256=c.WHEEL_SHA,admitted_task=admitted))
 c.S=S;queue=TrialQueue(n_concurrent=1,retry_config=RetryConfig(max_retries=0))
 out=dict(task_id=ID,pool='tmax',node='17',engine_id=basic['engine_id'],status='ENV_FAILED',model_calls=0,
  teacher_config_sha256=c.TEACHER_SHA,wheel_sha256=c.WHEEL_SHA,environment=environment,admitted_task=admitted,environment_and_storage_accepted=False)
 try:
  for kind in ['install','nop']:
   cfg=c.native_config(admitted,kind);cfg.environment=cfg.environment.model_validate(dict(environment,extra_docker_compose=cfg.environment.extra_docker_compose))
   if kind=='install':cfg.agent.env={}
   d=S/'dispatches'/str(uuid4());d.mkdir(parents=True);(d/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
   freeze(d/'dispatch.json',dict(task_id=ID,pool='tmax',kind=kind,trial_name=cfg.trial_name,config_sha256=sha(d/'trial-config.json'),model_calls=0))
   result=await queue.submit(cfg);trial=S/'trials'/cfg.trial_name
   out[kind+'_trial']=str(trial);out[kind+'_result_sha256']=sha(trial/'result.json')
   if result.exception_info or result.infrastructure_errors:raise ValueError('Native '+kind+' failed: '+str(result.exception_info)+str(result.infrastructure_errors))
   if kind=='nop':out['nop_reward']=verify_nop(result,trial,admitted)
  out.update(status='ENV_READY',environment_and_storage_accepted=True,model_verifier_recorder_joint_accepted=False,
    qualification='ZERO_MODEL_NATIVE_ENVIRONMENT_ONLY; one registered real teacher canary still required')
 except Exception as error:out.update(error_type=type(error).__name__,reason=str(error)[:2200])
 freeze(S/'environment-outcomes'/(ID+'.json'),out)
 freeze(R/'checks/private17-native-task-acceptance-r1.json',out)
 print(json.dumps({k:out.get(k) for k in ['status','node','engine_id','environment_and_storage_accepted','nop_reward','reason']}),flush=True)
if __name__=='__main__':
 for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
 os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH']
 os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
 asyncio.run(main())
