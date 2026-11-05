"""Post-native59 audit with one explicitly admitted independent cleanup recheck."""
import importlib,json,subprocess,time
from pathlib import Path
base=importlib.import_module('environment_evidence_audit_r4');read=base.read;write=base.write;sha=base.sha
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'environment-preflight59-r1';Q=B/'extract-elf-recheck-r1'
UNITS=['qwen35-env-preflight59-native18-20261102-r1.service','qwen35-env-preflight59-extract-elf-recheck-native18-20261103-r1.service']
def inactive():
 return all(subprocess.check_output(['systemctl','--user','show',u,'-p','ActiveState','--value'],text=True,timeout=5).strip()in['inactive','failed']for u in UNITS)
def qualify(cfg,snapshots,plan):
 result=base.attempt(cfg,B,snapshots)
 if result['status']=='PASS':
  runtime=result['actual_runtime'];assert runtime['container_probe']['wheel_sha256']=='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'and runtime['container_probe']['model_generation_calls']==0
  d=Path(cfg['trials_dir'])/cfg['trial_name'];assert not any(p.stat().st_size for p in(d/'agent/openharness-rollout').glob('*calls*.jsonl'))
  if Path(cfg['task']['path']).name in plan['public_cache_binding']['task_images']:
   cache=read(d/'PUBLIC_DEPENDENCY_CACHE_PREPARATION_R1.json');assert cache['model_generation_calls']==0 and cache['official_dependency_versions_not_overridden']and cache['actual_private_cache']['passed']
 if result['status']not in['PENDING','RUNNING']:
  assert cfg['agent']['import_path']=='env_preflight_shared_agent_r2:OpenHarnessPreflightNopAgent'
  assert all(cfg['agent'].get(k)is None for k in['override_timeout_sec','max_timeout_sec'])
  assert all(cfg['environment'].get(k)is None for k in['override_cpus','override_memory_mb','override_storage_mb','override_gpus'])
 return result
def audit():
 out=B/'ENV_PREFLIGHT_59_MANIFEST_R2.json'
 if out.exists()and read(out).get('frozen'):return read(out)
 assert inactive(),'Do not overlap the live R1 writer or recheck Job'
 original=read(B/'ACTUAL_NATIVE_TRIALS_R1.json');recheck=read(Q/'ACTUAL_NATIVE_TRIALS_R1.json');assert len(original['trials'])==59 and len(recheck['trials'])==1 and Path(recheck['trials'][0]['task']['path']).name=='extract-elf'
 for root,actual,expected in[(B,original,59),(Q,recheck,1)]:
  marker=read(root/'NATIVE_ALL_TERMINAL_R1.json');assert marker['terminal']==expected and marker['native_job_id']==actual['native_job_id']
 plan=read(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json');recheck_plan=read(Q/'PLAN_R1.json');assert recheck['plan_sha256']==sha(Q/'PLAN_R1.json')
 assert sha(B/'ACTUAL_NATIVE_TRIALS_R1.json')==recheck_plan['original_actual_manifest_sha256']and original['native_job_id']==recheck_plan['original_native_job_id']
 assert recheck['source_sha256']==sha(R/'run-env59-extract-elf-recheck18-r1.py')
 old=read(B/'ENV_PREFLIGHT_59_MANIFEST.json');assert old['terminal']==59 and old['native_job_id']==original['native_job_id']
 assert sha(Path(recheck_plan['original_result_path']))==recheck_plan['original_result_sha256'];assert read(Q/'CLEANUP_COMPLETE_R1.json')['passed']
 configs=original['trials']+recheck['trials'];snapshots={e:base.inventory(e)for e in{c['environment']['kwargs']['endpoint']for c in configs}}
 inventory=B/'engine-inventory-history-r2'/(str(time.time_ns())+'.json');write(inventory,snapshots);rows=[]
 for item in plan['rows']:
  attempts=[]
  for cfg in configs:
   if Path(cfg['task']['path']).name!=item['task_id']:continue
   try:attempts.append(qualify(cfg,snapshots,plan))
   except Exception as exc:attempts.append(dict(status='UNKNOWN',trial_path=str(Path(cfg['trials_dir'])/cfg['trial_name']),unknown_reasons=[repr(exc)]))
  last=attempts[-1];status=last['status'];historical_cleanup=[a for a in attempts[:-1]if not(a.get('cleanup')or{}).get('complete')]
  if status=='PASS'and historical_cleanup:status='UNKNOWN'
  rows.append(dict(task_id=item['task_id'],status=status,official_identity=item['official_identity'],attempts=attempts,historical_cleanup_unconfirmed=bool(historical_cleanup)))
 passed=sum(r['status']=='PASS'for r in rows)
 assert len(rows)==len({r['task_id']for r in rows})==59
 if passed==59:assert len({r['attempts'][-1]['native_trial_id']for r in rows})==59
 value=dict(kind='ACTUAL_SHARED59_WITH_ONE_EXPLICIT_INDEPENDENT_RECHECK_R2',updated_at=time.time(),frozen=passed==59,expected_unique_tasks=59,passed=passed,failed=sum(r['status']=='FAIL'for r in rows),unknown=sum(r['status']=='UNKNOWN'for r in rows),running=0,pending=0,terminal=59,tasks=rows,agent_generation_calls=0,official_verifier_rewards_are_not_model_scores=True,original_task_agent_deadlines_preserved=True,official_tasks_resources_and_verifiers_unmodified=True,sampling_manifest_sha256=sha(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json'),original_r1_manifest_path=str(B/'ENV_PREFLIGHT_59_MANIFEST.json'),original_r1_manifest_sha256=sha(B/'ENV_PREFLIGHT_59_MANIFEST.json'),actual_native_trials_sha256=sha(B/'ACTUAL_NATIVE_TRIALS_R1.json'),native_job_id=original['native_job_id'],recheck_actual_native_trials_path=str(Q/'ACTUAL_NATIVE_TRIALS_R1.json'),recheck_actual_native_trials_sha256=sha(Q/'ACTUAL_NATIVE_TRIALS_R1.json'),recheck_native_job_id=recheck['native_job_id'],recheck_plan_sha256=sha(Q/'PLAN_R1.json'),original_failure_results_unmodified=True,audit_source_sha256=sha(Path(__file__)),engine_inventory_path=str(inventory),engine_inventory_sha256=sha(inventory))
 if out.exists():write(B/'manifest-history-r2'/(str(time.time_ns())+'-'+sha(out)+'.json'),read(out))
 write(out,value);return value
if __name__=='__main__':print(json.dumps({k:v for k,v in audit().items()if k!='tasks'}))
