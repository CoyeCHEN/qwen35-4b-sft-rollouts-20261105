"""Incremental shared59 NOP evidence, using existing bounded Engine inventory/attempt audit."""
import importlib,json,time
from pathlib import Path
base=importlib.import_module('environment_evidence_audit_r4')
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'environment-preflight59-r1';read=base.read;sha=base.sha;write=base.write

def audit(final=False):
 plan=read(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json');out=B/'ENV_PREFLIGHT_59_MANIFEST.json'
 if out.exists()and read(out).get('frozen'):return read(out)
 path=B/'ACTUAL_NATIVE_TRIALS_R1.json';actual=read(path);configs=actual['trials'];assert len(configs)==59 and {Path(x['task']['path']).name for x in configs}=={x['task_id']for x in plan['rows']}
 snapshots={e:base.inventory(e)for e in{c['environment']['kwargs']['endpoint']for c in configs}}
 inventory=B/'engine-inventory-history'/(str(time.time_ns())+'.json');write(inventory,snapshots);rows=[]
 bytask={Path(x['task']['path']).name:x for x in configs}
 for item in plan['rows']:
  cfg=bytask[item['task_id']]
  try:
   assert cfg['agent']['import_path']=='env_preflight_shared_agent_r2:OpenHarnessPreflightNopAgent'and not cfg.get('install_only',False)
   result=base.attempt(cfg,B,snapshots)
   if result['status']=='PASS':
    runtime=result['actual_runtime'];assert runtime['container_probe']['wheel_sha256']=='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'
    assert runtime['container_probe']['model_generation_calls']==0
    directory=Path(cfg['trials_dir'])/cfg['trial_name'];assert not any(p.stat().st_size for p in(directory/'agent/openharness-rollout').glob('*calls*.jsonl'))
    if item['task_id']in plan['public_cache_binding']['task_images']:
     cache=read(directory/'PUBLIC_DEPENDENCY_CACHE_PREPARATION_R1.json');assert cache['model_generation_calls']==0 and cache['official_dependency_versions_not_overridden']and cache['actual_private_cache']['passed']
   if result.get('status')not in['PENDING','RUNNING']:
    for key in['override_timeout_sec','max_timeout_sec']:assert cfg['agent'].get(key)is None,'NOP Agent preserves original Task limit'
    for key in['override_cpus','override_memory_mb','override_storage_mb','override_gpus']:assert cfg['environment'].get(key)is None
  except Exception as error:result=dict(status='UNKNOWN',trial_path=str(Path(cfg['trials_dir'])/cfg['trial_name']),unknown_reasons=[repr(error)])
  rows.append(dict(task_id=item['task_id'],status=result['status'],official_identity=item['official_identity'],attempts=[result]))
 passed=sum(x['status']=='PASS'for x in rows);terminal=sum(x['status']not in['PENDING','RUNNING']for x in rows);complete=B/'NATIVE_ALL_TERMINAL_R1.json'
 if passed==59:
  assert len({r['attempts'][0]['native_trial_id']for r in rows})==59
  assert all(r['attempts'][0]['native_job_id']==actual['native_job_id']for r in rows)
 frozen=bool(final and passed==59 and complete.exists()and read(complete)['terminal']==59 and read(complete)['native_job_id']==actual['native_job_id'])
 value=dict(kind='ACTUAL_SHARED59_REMAINDER_NO_MODEL_ENVIRONMENT_ACCEPTANCE_R1',updated_at=time.time(),frozen=frozen,expected_unique_tasks=59,passed=passed,terminal=terminal,failed=sum(x['status']=='FAIL'for x in rows),unknown=sum(x['status']=='UNKNOWN'for x in rows),running=sum(x['status']=='RUNNING'for x in rows),pending=sum(x['status']=='PENDING'for x in rows),tasks=rows,agent_generation_calls=0,official_verifier_rewards_are_not_model_scores=True,official_tasks_resources_and_verifiers_unmodified=True,original_task_agent_deadlines_preserved=True,external_generation_source_review=plan['external_generation_scan'],sampling_manifest_sha256=sha(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json'),actual_native_trials_sha256=sha(path),native_job_id=actual['native_job_id'],runtime_probe_source_sha256=sha(R/'env_preflight30_probe_r1.py'),shared_nop_agent_source_sha256=sha(R/'env_preflight_shared_agent_r2.py'),audit_source_sha256=sha(Path(__file__)),engine_inventory_path=str(inventory),engine_inventory_sha256=sha(inventory),frozen_only_after_native_job_return=final)
 if out.exists():
  old=read(out)
  signature=lambda v:[(r['task_id'],r['status'],[a.get('result_sha256')for a in r['attempts']])for r in v['tasks']]
  if signature(old)!=signature(value):
   history=B/'manifest-history'/(str(time.time_ns())+'-'+sha(out)+'.json');history.parent.mkdir(exist_ok=True);history.write_bytes(out.read_bytes())
 write(out,value);return value
if __name__=='__main__':print(json.dumps({k:v for k,v in audit().items()if k!='tasks'}))
