"""Publish one accepted environment to the existing eight-slot native controller."""
import datetime,fcntl,hashlib,json,os,time
from pathlib import Path
import run_collection_stream_r4 as c
from collection_readiness_r4 import ensure_resident
R=c.R;ID='task_007016_4f9de434'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def freeze(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,indent=2)
def main():
 lock=(R/'checks/private17-canary-registration-r1.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 proof=R/'checks/private17-native-task-acceptance-r3.json'
 while not proof.exists():time.sleep(15)
 x=json.loads(proof.read_text())
 if x['status']!='ENV_READY' or not x['environment_and_storage_accepted']:
  freeze(R/'checks/private17-canary-registration-r1.json',dict(checked_at=now(),status='ENVIRONMENT_ACCEPTANCE_FAILED_NO_TEACHER_REGISTERED',native_proof=str(proof),native_proof_sha256=sha(proof),model_calls=0));return
 assert x['node']=='17' and x['engine_id']=='59c8ba22-0aa4-4aed-bc43-4e1b5989fa22'
 assert x['teacher_config_sha256']==c.TEACHER_SHA and x['wheel_sha256']==c.WHEEL_SHA and not c.attempt_counts().get(ID,0)
 row=next(z for z in c.frozen_rows() if z['task_id']==ID)
 assert not (R/'manifests/runtime-deployments17-r1'/ (ID+'.json')).exists()
 admitted=x['admitted_task'];assert admitted['task_id']==ID and row['slot_id']==admitted['slot_id']
 # r5 retains its149 residency gate before stage reads the explicit deployment.
 # This single217MB legacy bridge is recorded; no false cross-engine image proof.
 warm=ensure_resident(admitted)
 freeze(R/'checks/private17-first-canary-legacy149-warm-r1.json',dict(checked_at=now(),task_id=ID,model_calls=0,reason='Existing r5 pre-stage residency gate remains149-specific. Native teacher setup/agent/verifier run on17 via the explicit assignment; one original image bridge retained for this canary.',native_image_materialization=warm))
 assert not c.attempt_counts().get(ID,0)
 deployment=dict(task_id=ID,admission='ONE_REGISTERED_MODEL_CANARY',native_acceptance_proof=str(proof),native_acceptance_proof_sha256=sha(proof),
  admitted_task_identity=admitted,environment=x['environment'],registered_at=now(),node='17',engine_id=x['engine_id'],
  global_teacher_permit_owner_pid=3552766,global_teacher_limit=8,teacher_config_sha256=c.TEACHER_SHA,wheel_sha256=c.WHEEL_SHA,
  actual_teacher_dispatch_by_this_script=0,model_calls_by_this_script=0)
 assignment=R/'manifests/runtime-deployments17-r1'/(ID+'.json');freeze(assignment,deployment)
 accepted=dict(x,kind='ORIGINAL_SELECTED_TASK_NATIVE_ENVIRONMENT_ACCEPTANCE',native_install_trial=x['install_trial'],native_nop_trial=x['nop_trial'],raw_outcome=str(proof),raw_outcome_sha256=sha(proof))
 freeze(R/'checks/native-reserve-acceptance-r4'/(ID+'.json'),accepted)
 freeze(R/'checks/private17-canary-registration-r1.json',dict(checked_at=now(),status='ONE_ORIGINAL_SELECTED_CANARY_READY_FOR_EXISTING_CONTROLLER',task_id=ID,assignment=str(assignment),assignment_sha256=sha(assignment),teacher_dispatches_by_this_script=0,global_teacher_cap=8,backend='Private17 SSD Engine; existing global native queue; same direct authorized DeepSeek service'))
 print(json.dumps(dict(status='CANARY_REGISTERED_EXISTING_NATIVE_QUEUE',task_id=ID,model_calls=0)),flush=True)
if __name__=='__main__':
 for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
 os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH']
 os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
 main()
