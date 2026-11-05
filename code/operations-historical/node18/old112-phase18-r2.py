"""Fixed old14x8 readout admitted by real selected267, separate from new evaluation."""
import importlib,json,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');P=R/'old-four-arm';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
cold=importlib.import_module('cold-old112-serving18-r2');core=importlib.import_module('old-four-after-selected267-phase18-r2')
TAGS=['old-M1','old-M2']+[a+'-epoch'+str(e)for a in'ABCD'for e in(1,3,5)]
read=core.read;sha=core.sha;save=core.save

def active(item):return any('ActiveState='+x+'\n'in item['systemd']for x in['active','activating','deactivating'])
def completion_proof(owner):
 gate=core.selected267_gate();assert gate['passed']
 return dict(kind='ACTUAL_SELECTED267_COMPLETION_FROM_UNIQUE18',unique_controller_owner=owner,gate=gate,
  validation_boundary='actual Raw Result/Recorder/native-closed validation on node18; authenticated project SSH handoff to149')
def proof_sha(proof):
 import hashlib
 return hashlib.sha256(json.dumps(proof,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def advance(owner,state,remote,request):
 gate=core.selected267_gate()
 if not gate['passed']:state['old112_behavior']=dict(status='WAIT_ACTUAL_SELECTED267_AUDIT',gate=gate);return
 path=R/'checks/OLD_READOUT_SELECTED267_RELEASE_R1.json'
 if not path.exists():
  importlib.import_module('freeze-old-readout-selected267-deployment18-r1').freeze(owner)
 release=read(path);assert release['forced_command_is_project_key_only']and release['formal801_required']is False
 actual=remote('status');assert actual['capability']=='old112_only_no801';save(C/'OLD112_REMOTE_NATIVE_STATUS_R2.json',actual)
 if not ensure_shared8(owner,state,actual,release,request):return
 env_sha=actual['modes']['old-env8']['complete_manifest_sha256']
 experiments=read(P/'manifests/experiments.json');completed=[];running=[t for t in TAGS if active(actual['modes']['old-'+t])]
 for tag in TAGS:
  mode='old-'+tag;item=actual['modes'][mode]
  if item['complete']:
   done=item['complete'];assert done['actual_terminal']==8 and done['model_tag']==tag and done['source_sha256']==release['native_runner_sha256']
   if active(item):state['old112_behavior']=dict(status='WAIT_NATIVE_JOB_AND_CLEANUP_CLOSE',model=tag);return
   marker=C/('OLD112_SERVER_CLOSED_R2_'+tag+'.json')
   if not marker.exists():cold.stop(tag);save(marker,dict(at=time.time(),native_terminal=8,remote_terminal=done))
   completed.append(tag);continue
  if running:state['old112_behavior']=dict(status='NATIVE_OLD112_JOB_OR_POSTHOC_AUDIT_RUNNING',model=running[0],native_progress=actual['modes']['old-'+running[0]],completed_models=completed);return
  if(C/'native-phase-requests'/(mode+'.json')).exists():state['old112_behavior']=dict(status='EXISTING_NATIVE_OLD112_REQUEST_REQUIRES_INSPECTION',model=tag,observed=item);return
  if not tag.startswith('old-'):
   arm,epoch=tag.split('-epoch');checkpoint=Path(experiments['arms'][arm]['output_dir'])/('checkpoint-'+str(106*int(epoch)))
   if not(checkpoint/'CHECKPOINT_COMPLETE.json').exists():continue
  cold.start(tag)
  try:live=cold.info(tag)
  except OSError:state['old112_behavior']=dict(status='NATIVE_OLD112_COLD_SERVER_STARTING',model=tag);return
  proof=completion_proof(owner)
  request(mode,dict(model_tag=tag,actual_selected267_completed=True,selected267_completion_proof=proof,selected267_completion_proof_sha256=proof_sha(proof),
   model_path=live['model_path'],model_manifest=live['model_manifest'],weight_version=live['weight_version'],gpu_uuid=cold.GPU,
   old112_plan_sha256=release['old112_plan_sha256'],runtime_binding_sha256=release['runtime_binding_sha256'],runtime_profiles_sha256=release['runtime_profiles_sha256'],
   native_runner_sha256=release['native_runner_sha256'],old_env_manifest_sha256=env_sha,original_ten_tools_finish_off=True,original_task_agent_limits=True,actual_model_info=live['actual_model_info']),owner)
  state['old112_behavior']=dict(status='NATIVE_OLD112_EIGHT_TASK_JOB_SUBMITTED',model=tag,completed_models=completed);return
 state['old112_behavior']=dict(status='WAIT_REGISTERED_OLD_NATIVE_CHECKPOINTS',completed_models=completed)
 if len(completed)==14:
  state['old112_behavior']['status']='ALL_112_NATIVE_TRIALS_TERMINAL';marker=C/'OLD112_NATIVE_ALL_TERMINAL_R2.json'
  if not marker.exists():save(marker,dict(completed=True,actual_terminal=112,models=completed,actual_selected267_completed=True,formal801_required=False,score_coverage_and_behavior_validity_reported_separately=True,original_native_results_and_recorders_retained=True))


def ensure_shared8(owner,state,actual,release,request):
 item=actual['modes']['old-env8']
 if item['complete']and active(item):state['old112_behavior']=dict(status='WAIT_SHARED_NOP8_NATIVE_WORKER_CLOSED');return False
 if item['complete']:
  proof=item['complete'];assert proof['frozen']and proof['passed']==8 and proof['actual_model_generation_calls']==0 and proof['old_wheel_sha256']=='f84f810e8a61545d685fb6722593886a0c88cc829b2ab9ca7c3476fe11e1209e'
  state['old112_shared8_environment']=dict(status='ACTUAL8_OF8_PASSED',manifest_sha256=item['complete_manifest_sha256'],model_generation_calls=0);return True
 if active(item):state['old112_behavior']=dict(status='SHARED_OLD_WHEEL_NOP8_ACTUAL_ENVIRONMENT_ACCEPTANCE_RUNNING',progress=item['progress']);return False
 if(C/'native-phase-requests/old-env8.json').exists():state['old112_behavior']=dict(status='SHARED_OLD_WHEEL_NOP8_REQUIRES_INSPECTION',progress=item['progress'],unit=item['systemd']);return False
 cold.start('old-M1')
 try:live=cold.info('old-M1')
 except OSError:state['old112_behavior']=dict(status='OLD_M1_COLD_SERVICE_STARTING_FOR_NO_GENERATION_NOP8');return False
 proof=completion_proof(owner)
 request('old-env8',dict(model_tag='environment-nop8',actual_model_attempts_expected=0,actual_selected267_completed=True,selected267_completion_proof=proof,selected267_completion_proof_sha256=proof_sha(proof),
  model_path=live['model_path'],model_manifest=live['model_manifest'],weight_version=live['weight_version'],gpu_uuid=cold.GPU,
  old112_plan_sha256=release['old112_plan_sha256'],runtime_binding_sha256=release['runtime_binding_sha256'],runtime_profiles_sha256=release['runtime_profiles_sha256'],
  native_runner_sha256=release['environment_nop_runner_sha256'],original_ten_tools_finish_off=True,original_task_agent_limits=True,actual_model_info=live['actual_model_info']),owner)
 state['old112_behavior']=dict(status='SHARED_OLD_WHEEL_NOP8_SUBMITTED',model_generation_calls=0);return False
