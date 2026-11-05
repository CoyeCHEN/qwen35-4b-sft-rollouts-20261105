"""Read-only candidate plan: terminal NOP failures with confirmed scoped cleanup."""
import argparse,hashlib,json,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'synthetic32'
NOP={'env_preflight30_agent_r1:OpenHarnessPreflightNopAgent','env_preflight_shared_agent_r2:OpenHarnessPreflightNopAgent','env_preflight_synthetic32_agent_r3:OpenHarnessPreflightNopAgent'}
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def plan():
 source=B/'ENV_PREFLIGHT_32_MANIFEST.json';m=read(source);deployment=read(B/'SYNTHETIC32_DEPLOYMENT_R3.json');byid={t['task_id']:t for t in deployment['tasks']};assert len(byid)==32
 registry=B/'env-runtime/RECHECK_REGISTRY_R1.json';paths=[B/'prep-ACTUAL_NATIVE_TRIALS_R1.json']+([Path(s)for s in read(registry)['actual_trial_manifests']]if registry.exists()else[]);registered=[]
 for path in paths:
  if path.exists():registered+=read(path)['trials']
 inventory_path=Path(m['batch_inventory_path']);assert sha(inventory_path)==m['batch_inventory_sha256'];inventory=read(inventory_path);snap=inventory['engines'][deployment['endpoint']];queries=snap['queries'];assert all(v['ok']for v in queries.values())and queries['engine']['data']['ID']==deployment['engine_id'];assert time.time()-snap['checked_at']<120,'Require fresh actual resource query'
 selected=[];skipped=[]
 for row in m['tasks']:
  if row['status']!='FAIL':continue
  task=row['task_id'];item=byid[task]
  if item['required_independent_recheck']:skipped.append(dict(task_id=task,reason='Explicit missing-prebuilt recipe lane owns this task; do not duplicate its recheck'));continue
  entries=[c for c in registered if Path(c['task']['path']).name==task]
  if any(not(Path(c['trials_dir'])/c['trial_name']/'result.json').exists()for c in entries):skipped.append(dict(task_id=task,reason='Another registered NOP is pending/running; preserve it'));continue
  attempt=row['attempts'][-1];trial=Path(attempt['trial_path']);result=trial/'result.json';raw=read(result);assert sha(result)==attempt['result_sha256'];assert raw['config']['agent']['import_path']in NOP
  if not(raw.get('exception_info')or raw.get('infrastructure_errors')or attempt.get('failures')):continue
  providers=list(trial.glob('remote-docker-*.jsonl'))
  if len(providers)!=1:skipped.append(dict(task_id=task,reason='Provider identity evidence incomplete'));continue
  identity=providers[0].stem.removeprefix('remote-docker-');remaining={kind:[r.get('ID',r.get('Name'))for r in queries[kind]['data']if r['identity']==identity]for kind in ['container','network','volume']}
  if any(remaining.values()):skipped.append(dict(task_id=task,reason='Prior failed NOP resources still present',identity=identity,resources=remaining));continue
  selected.append(dict(task_id=task,original_trial_path=str(trial),original_trial_uuid=raw['id'],original_result_sha256=sha(result),original_exception=(raw.get('exception_info')or{}).get('exception_type'),original_failure_phase=raw.get('failure_phase'),provider_identity=identity,scoped_resources_absent=True,cleanup_batch_snapshot_path=str(inventory_path),cleanup_batch_snapshot_sha256=sha(inventory_path),model_attempts=0))
 value=dict(schema='synthetic32-terminal-environment-failure-candidates-r4',at=time.time(),tasks=[x['task_id']for x in selected],eligibility=selected,skipped=skipped,source_environment_manifest_sha256=sha(source),deployment_manifest_sha256=sha(B/'SYNTHETIC32_DEPLOYMENT_R3.json'),fixed_dataset_tasks=32,model_generation_calls=0,no_original_results_modified=True,no_job_dispatch=True,source_sha256=sha(Path(__file__))if Path(__file__).is_file()else'CHECK_ONLY_STDIN');print(json.dumps(value,indent=2));return value
if __name__=='__main__':plan()
