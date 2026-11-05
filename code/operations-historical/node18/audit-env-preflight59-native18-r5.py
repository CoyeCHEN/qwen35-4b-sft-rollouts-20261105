"""Post-native59 audit: three registered NOP rechecks and one bound classification."""
import importlib,json,os,subprocess,time
from pathlib import Path
base=importlib.import_module('environment_evidence_audit_r4');read=base.read;write=base.write;sha=base.sha
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'environment-preflight59-r1';Q=B/'extract-elf-recheck-r1';T=B/'torch271-recheck-r1'
UNITS=['qwen35-env-preflight59-native18-20261102-r1.service','qwen35-env-preflight59-extract-elf-recheck-native18-20261103-r1.service','qwen35-env-preflight59-torch271-recheck-native18-20261103-r1.service']
def inactive():
 return all(subprocess.check_output(['systemctl','--user','show',u,'-p','ActiveState','--value'],text=True,timeout=5).strip()in['inactive','failed']for u in UNITS)
def apply_bound_target_service_classification(cfg,result):
 if Path(cfg['task']['path']).name!='pypi-server'or result.get('status')!='FAIL':return result
 path=B/'classification-evidence/PYPI_SERVER_NOP_ZERO_CLASSIFICATION_R1.json';release=read(Q/'EXECUTION_RELEASE_R4.json')
 assert sha(path)==release['pypi_classification_receipt_sha256'];proof=read(path)
 assert proof['task_id']=='pypi-server'
 if result.get('native_trial_id')!=proof['native_trial_id']:return result
 assert result['native_job_id']==proof['native_job_id']and result['trial_path']==proof['trial_path']and result['result_sha256']==proof['raw_result_sha256']
 for item in proof['evidence_files']:assert sha(Path(item['path']))==item['sha256'],item['path']
 raw=read(Path(proof['raw_result_path']));assert raw['id']==proof['native_trial_id']and raw['config']['job_id']==proof['native_job_id']and Path(raw['config']['task']['path'])==Path(cfg['task']['path'])
 assert not raw.get('exception_info')and not raw.get('infrastructure_errors')and raw['verifier']['finished_at']
 assert raw['verifier_result']['return_code']==0 and raw['verifier_result']['rewards']['reward']==0
 # Only the bound, human-audited false positive may be removed. Every other
 # verifier/network/runtime failure and every UNKNOWN remains blocking.
 if result.get('failures')!=[proof['allowed_derived_failure']]or result.get('unknown_reasons'):return result
 runtime=result.get('actual_runtime')or{};cleanup=result.get('cleanup')or{}
 if not(runtime.get('passed')and runtime.get('model_generation_calls')==0 and cleanup.get('complete')):return result
 assert runtime['identity']==cleanup['identity']==proof['identity']and runtime['engine_id']==cleanup['engine_id']==proof['engine_id']and runtime['actual_image_id']==proof['official_image_id']
 corrected=dict(result,status='PASS',failures=[],classification_correction=dict(receipt_path=str(path),receipt_sha256=sha(path),original_derived_status=result['status'],original_derived_failures=result['failures'],official_reward_unchanged=0,raw_result_sha256=proof['raw_result_sha256'],reason='Bound official local target service absent under NOP; public verifier bootstrap completed'))
 return corrected

def qualify(cfg,snapshots,plan,direct_torch271=False):
 result=apply_bound_target_service_classification(cfg,base.attempt(cfg,B,snapshots))
 if result['status']=='PASS':
  runtime=result['actual_runtime'];assert runtime['container_probe']['wheel_sha256']=='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'and runtime['container_probe']['model_generation_calls']==0
  d=Path(cfg['trials_dir'])/cfg['trial_name'];assert not any(p.stat().st_size for p in(d/'agent/openharness-rollout').glob('*calls*.jsonl'))
  if Path(cfg['task']['path']).name in plan['public_cache_binding']['task_images']:
   if direct_torch271:
    assert Path(cfg['task']['path']).name in{'pytorch-model-cli','pytorch-model-recovery'}
    repair=read(T/'PLAN_R1.json');policy=read(d/'PUBLIC_CACHE_POLICY_R1.json');assert policy['task_id']==Path(cfg['task']['path']).name and policy['plan_sha256']==sha(T/'PLAN_R1.json')and policy['source_sha256']==sha(R/'run-env59-torch271-recheck18-r1.py')and policy['agent_generation_calls']==0
    assert all(policy[k]==v for k,v in repair['cache_policy'].items())and policy['project_torch270_archive_materialization']is False and policy['official_torch_pin']=='2.7.1'
    assert not(d/'PUBLIC_DEPENDENCY_CACHE_PREPARATION_R1.json').exists(),'A project270 archive was unexpectedly materialized'
    source=next(x for x in repair['rows']if x['task_id']==policy['task_id'])
    for item in source['official_verifier_sources']:assert sha(Path(item['path']))==item['sha256']
   else:
    cache=read(d/'PUBLIC_DEPENDENCY_CACHE_PREPARATION_R1.json');assert cache['model_generation_calls']==0 and cache['official_dependency_versions_not_overridden']and cache['actual_private_cache']['passed']
 if result['status']not in['PENDING','RUNNING']:
  assert cfg['agent']['import_path']=='env_preflight_shared_agent_r2:OpenHarnessPreflightNopAgent'
  assert all(cfg['agent'].get(k)is None for k in['override_timeout_sec','max_timeout_sec'])
  assert all(cfg['environment'].get(k)is None for k in['override_cpus','override_memory_mb','override_storage_mb','override_gpus'])
 return result
def audit():
 out=B/'ENV_PREFLIGHT_59_MANIFEST_R2.json'
 if out.exists()and read(out).get('frozen'):return read(out)
 assert inactive(),'Do not overlap any of the three live native Jobs'
 original=read(B/'ACTUAL_NATIVE_TRIALS_R1.json');extract=read(Q/'ACTUAL_NATIVE_TRIALS_R1.json');torch=read(T/'ACTUAL_NATIVE_TRIALS_R1.json')
 assert len(original['trials'])==59 and len(extract['trials'])==1 and Path(extract['trials'][0]['task']['path']).name=='extract-elf'
 assert len(torch['trials'])==2 and {Path(c['task']['path']).name for c in torch['trials']}=={'pytorch-model-cli','pytorch-model-recovery'}
 sources=[(B,original,59,'run-env-preflight59-native18-r1.py',False),(Q,extract,1,'run-env59-extract-elf-recheck18-r1.py',False),(T,torch,2,'run-env59-torch271-recheck18-r1.py',True)]
 for root,actual,expected,worker,direct in sources:
  marker=read(root/'NATIVE_ALL_TERMINAL_R1.json');assert marker['terminal']==expected and marker['native_job_id']==actual['native_job_id']and actual['source_sha256']==sha(R/worker)
 plan=read(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json');old=read(B/'ENV_PREFLIGHT_59_MANIFEST.json');assert old['terminal']==59 and old['native_job_id']==original['native_job_id']
 for root,actual in[(Q,extract),(T,torch)]:
  repair=read(root/'PLAN_R1.json');assert actual['plan_sha256']==sha(root/'PLAN_R1.json')and repair['original_actual_manifest_sha256']==sha(B/'ACTUAL_NATIVE_TRIALS_R1.json')and repair['original_native_job_id']==original['native_job_id']and read(root/'CLEANUP_COMPLETE_R1.json')['passed']
  originals=[repair]if root==Q else repair['rows']
  for item in originals:
   path=Path(item['original_result_path'])if root==Q else Path(next(c for c in original['trials']if Path(c['task']['path']).name==item['task_id'])['trials_dir'])/next(c for c in original['trials']if Path(c['task']['path']).name==item['task_id'])['trial_name']/'result.json'
   digest=item['original_result_sha256'];assert sha(path)==digest
 tagged=[(cfg,actual['native_job_id'],direct)for root,actual,n,worker,direct in sources for cfg in actual['trials']]
 snapshots={e:base.inventory(e)for e in{c['environment']['kwargs']['endpoint']for c,j,direct in tagged}};inventory=B/'engine-inventory-history-r2'/(str(time.time_ns())+'.json');write(inventory,snapshots);rows=[]
 for item in plan['rows']:
  attempts=[]
  for cfg,expected_job,direct in tagged:
   if Path(cfg['task']['path']).name!=item['task_id']:continue
   try:
    result=qualify(cfg,snapshots,plan,direct)
    assert result.get('native_job_id')==expected_job,'Raw Result does not belong to its registered native Job'
    attempts.append(result)
   except Exception as exc:attempts.append(dict(status='UNKNOWN',trial_path=str(Path(cfg['trials_dir'])/cfg['trial_name']),unknown_reasons=[repr(exc)]))
  last=attempts[-1];status=last['status'];historical=[a for a in attempts[:-1]if not(a.get('cleanup')or{}).get('complete')]
  if status=='PASS'and historical:status='UNKNOWN'
  rows.append(dict(task_id=item['task_id'],status=status,official_identity=item['official_identity'],attempts=attempts,historical_cleanup_unconfirmed=bool(historical)))
 passed=sum(r['status']=='PASS'for r in rows);assert len(rows)==len({r['task_id']for r in rows})==59
 if passed==59:assert len({r['attempts'][-1]['native_trial_id']for r in rows})==59
 value=dict(kind='ACTUAL_SHARED59_WITH_THREE_EXPLICIT_INDEPENDENT_RECHECKS_R3',updated_at=time.time(),frozen=passed==59,expected_unique_tasks=59,passed=passed,failed=sum(r['status']=='FAIL'for r in rows),unknown=sum(r['status']=='UNKNOWN'for r in rows),running=0,pending=0,terminal=59,native_attempts=62,tasks=rows,agent_generation_calls=0,official_verifier_rewards_are_not_model_scores=True,original_task_agent_deadlines_preserved=True,official_tasks_resources_and_verifiers_unmodified=True,sampling_manifest_sha256=sha(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json'),original_r1_manifest_path=str(B/'ENV_PREFLIGHT_59_MANIFEST.json'),original_r1_manifest_sha256=sha(B/'ENV_PREFLIGHT_59_MANIFEST.json'),actual_native_trials_sha256=sha(B/'ACTUAL_NATIVE_TRIALS_R1.json'),native_job_id=original['native_job_id'],rechecks=[dict(actual_native_trials_path=str(root/'ACTUAL_NATIVE_TRIALS_R1.json'),actual_native_trials_sha256=sha(root/'ACTUAL_NATIVE_TRIALS_R1.json'),native_job_id=actual['native_job_id'],plan_sha256=sha(root/'PLAN_R1.json'),tasks=n)for root,actual,n in[(Q,extract,1),(T,torch,2)]],pypi_classification_receipt_sha256=sha(B/'classification-evidence/PYPI_SERVER_NOP_ZERO_CLASSIFICATION_R1.json'),original_failure_results_unmodified=True,audit_source_sha256=sha(Path(__file__)),engine_inventory_path=str(inventory),engine_inventory_sha256=sha(inventory))
 if out.exists():write(B/'manifest-history-r2'/(str(time.time_ns())+'-'+sha(out)+'.json'),read(out))
 write(out,value);return value
if __name__=='__main__':
 frozen=read(Q/'EXECUTION_RELEASE_R4.json');assert frozen['required_source_sha256'][str(Path(__file__).resolve())]==sha(Path(__file__))
 guard=R/'formal-controller18-docker-admission-env59-r1/bin/docker';assert sha(guard)==frozen['docker_guard_sha256']
 deployment=R/'configs/formal-controller18-deployment-r2.json';plan=read(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json');assert sha(deployment)==plan['native_deployment_sha256']
 prefix=str(guard.parent)+':'+read(deployment)['transport']['private_client_bin']+':';assert os.environ['PATH'].startswith(prefix),'Audit subprocess must have explicit project-only transport PATH'
 print(json.dumps({k:v for k,v in audit().items()if k!='tasks'}))
