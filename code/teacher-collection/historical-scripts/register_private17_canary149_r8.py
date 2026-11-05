"""Publish an accepted placement before warming the149 legacy admission bridge."""
import datetime,fcntl,hashlib,json,os
from pathlib import Path
import run_collection_stream_r4 as c
from collection_readiness_r4 import ensure_resident
from native_image_archive149_r1 import image_info
R=c.R;ID='task_007040_9f9b1fb1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def freeze(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,indent=2)
def main():
 lock=(R/'checks/private17-canary-registration-r8.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 proof=R/'checks/private17-native-task-acceptance-r8.json';accepted=json.loads(proof.read_text())
 assert accepted['status']=='ENV_READY' and accepted['environment_and_storage_accepted'] and accepted['node']=='17'
 assert accepted['engine_id']=='59c8ba22-0aa4-4aed-bc43-4e1b5989fa22' and accepted['teacher_config_sha256']==c.TEACHER_SHA and accepted['wheel_sha256']==c.WHEEL_SHA
 assert not c.attempt_counts().get(ID,0)
 state=json.loads((R/'campaign-state.json').read_text());assert ID not in state['active_task_pipelines']
 admitted=accepted['admitted_task'];assert admitted['task_id']==ID
 # The resident-ready selector cannot stage this item until its image appears.
 # Fail explicitly if another owner has already made it resident.
 assert image_info(admitted['image_id']) is None,'Image already resident; preserve the existing queue placement instead of racing it'
 old=R/'checks/native-reserve-acceptance-r4'/(ID+'.json');previous=json.loads(old.read_text())
 assert previous['status']=='ENV_READY'
 for key in ['task_id','image_id','prepared_task_toml_sha256','instruction_sha256','verifier_files']:
  assert previous['admitted_task'][key]==admitted[key],key
 assignment=R/'manifests/runtime-deployments17-r1'/(ID+'.json')
 deployment=dict(task_id=ID,admission='ONE_REGISTERED_MODEL_CANARY',native_acceptance_proof=str(proof),native_acceptance_proof_sha256=sha(proof),
  admitted_task_identity=admitted,environment=accepted['environment'],registered_at=now(),node='17',engine_id=accepted['engine_id'],
  global_teacher_permit_owner_pid=3552766,global_teacher_limit=8,teacher_config_sha256=c.TEACHER_SHA,wheel_sha256=c.WHEEL_SHA,
  existing_ready_proof=str(old),existing_ready_proof_sha256=sha(old),placement_published_before_legacy_warm=True,teacher_dispatches_by_preparer=0)
 freeze(assignment,deployment)
 warm=ensure_resident(admitted)
 freeze(R/'checks/private17-first-canary-legacy149-warm-r8.json',dict(checked_at=now(),task_id=ID,placement_already_frozen=str(assignment),placement_sha256=sha(assignment),native_image_materialization=warm,model_calls=0))
 freeze(R/'checks/private17-canary-registration-r8.json',dict(checked_at=now(),status='ACCEPTED17_ASSIGNMENT_PUBLISHED_BEFORE_IMAGE_READY_SIGNAL',task_id=ID,assignment=str(assignment),assignment_sha256=sha(assignment),preserved_existing_ready_proof=str(old),preserved_existing_ready_proof_sha256=sha(old),teacher_dispatches_by_preparer=0,global_teacher_cap=8))
 print(json.dumps(dict(status='ACCEPTED17_PLACEMENT_PUBLISHED_THEN_IMAGE_WARMED',task_id=ID,model_calls=0)),flush=True)
if __name__=='__main__':
 for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
 os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH'];os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
 main()
