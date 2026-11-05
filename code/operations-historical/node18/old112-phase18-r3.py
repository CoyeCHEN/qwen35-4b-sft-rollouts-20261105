"""Fixed old14x8 readout admitted by real selected267, separate from new evaluation."""
import importlib,json,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');P=R/'old-four-arm';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
cold=importlib.import_module('cold-old112-serving18-r3');core=importlib.import_module('old-four-after-selected267-phase18-r3')
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
 runtime_path=P/'checks/OLD112_NATIVE_BOUNDARY_ACCEPTANCE_R1.json'
 if not runtime_path.exists():
  state['old112_behavior']=dict(status='WAIT_OLD112_NATIVE_LIFECYCLE_BOUNDARY_ACCEPTANCE',reason='Verifier requires actual native command completion or termination acknowledgement');return
 runtime=read(runtime_path)
 remote_env=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-old-m2-four-arm-20261101/env/harbor-native-boundary-r1')
 expected={'harbor/trial/agent_lifecycle.py':'f229f1799acb390c872b601dbeca52ad9d194b0dd3f2e8c70bd558aff11282e7','harbor/trial/process_supervisor.py':'d9a679c91bd3e835f54ad62852b5fb8206a0dffd5dd9eb755090ce6d5a4d34b0','harbor/trial/trial.py':'e0ec81210a041765d4a6ac83c6c3e7b0859236ec872c731b1595044a4cf8f065'}
 if not runtime.get('passed')or not runtime.get('actual_runtime_fixture_passed')or not runtime.get('dependency_versions_match_base')or runtime.get('native_python')!=str(remote_env/'bin/python')or runtime.get('harbor_version')!='0.23.0+rsi.2':
  raise RuntimeError('Old112 native lifecycle interpreter/version/fixture acceptance differs')
 if runtime.get('harness_wheel_sha256')!='f84f810e8a61545d685fb6722593886a0c88cc829b2ab9ca7c3476fe11e1209e':
  raise RuntimeError('Old112 must preserve its frozen original ten-tool Harness wheel')
 items=runtime.get('installed_source_files',[])
 if len(items)!=3 or {x['relative_path']for x in items}!=set(expected)or any(x['sha256']!=expected[x['relative_path']]or x['path']!=str(remote_env/'lib/python3.12/site-packages'/x['relative_path'])for x in items):
  raise RuntimeError('Old112 native lifecycle installed source identities differ')
 formal=R/'checks/FORMAL267_NATIVE_BOUNDARY_ACCEPTANCE_R1.json'
 if not formal.exists()or runtime.get('harbor_wheel_sha256')!=read(formal)['harbor_wheel_sha256']:
  raise RuntimeError('Old112 must use the same accepted native Harbor wheel bytes')
 for key in ['base_runtime_manifest_sha256','fixture_result_sha256']:
  if len(bytes.fromhex(runtime.get(key,'')))!=32:raise RuntimeError('Old112 native lifecycle evidence SHA is missing')
 path=R/'checks/OLD_READOUT_SELECTED267_RELEASE_R1.json'
 if not path.exists():
  importlib.import_module('freeze-old-readout-selected267-deployment18-r1').freeze(owner)
 release=read(path);assert release['forced_command_is_project_key_only']and release['formal801_required']is False
 actual=remote('status');assert actual['capability']=='old112_only_no801'
 verified=actual.get('native_boundary_identity',{})
 if actual.get('native_boundary_acceptance_sha256')!=sha(runtime_path)or not verified.get('passed')or verified.get('native_python')!=runtime['native_python']or verified.get('harbor_version')!=runtime['harbor_version']or verified.get('harbor_wheel_sha256')!=runtime['harbor_wheel_sha256']or verified.get('harness_wheel_sha256')!=runtime['harness_wheel_sha256']or verified.get('installed_source_sha256')!=expected:
  state['old112_behavior']=dict(status='WAIT_AUTHENTICATED_OLD112_NATIVE_BOUNDARY_BINDING');return
 save(C/'OLD112_REMOTE_NATIVE_STATUS_R2.json',actual)
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
