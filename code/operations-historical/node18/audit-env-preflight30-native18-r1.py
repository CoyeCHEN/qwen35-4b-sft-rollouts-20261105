"""Derive each environment pass from real runtime, verifier, logs and cleanup."""
import hashlib,json,re,subprocess,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1';BASE=R/'environment-preflight30'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(v,indent=2)+'\n');t.replace(p)
def main():
 sample=E/'manifests/DIAGNOSTIC30_SAMPLING_MANIFEST_R1.json';identities=read(sample)['selected_task_identities'];actual=read(BASE/'ACTUAL_NATIVE_TRIALS_R1.json')if(BASE/'ACTUAL_NATIVE_TRIALS_R1.json').exists()else dict(trials=[]);bytask={Path(x['task']['path']).name:x for x in actual['trials']};rows=[]
 for identity in identities:
  task=identity['task_id'];row=dict(task_id=task,status='PENDING',official_identity=identity,attempts=[])
  cfg=bytask.get(task)
  if cfg is None:rows.append(row);continue
  d=Path(cfg['trials_dir'])/cfg['trial_name'];result=d/'result.json'
  if not result.exists():
   if d.exists():row['status']='RUNNING'
   row['native_trial_path']=str(d);rows.append(row);continue
  raw=read(result);reasons=[];proof=d/'agent/ENV_PREFLIGHT_RUNTIME.json';runtime=read(proof)if proof.exists()else None
  if not runtime or not runtime.get('passed'):reasons.append('actual_cli_runtime_probe_not_passed')
  verifier=raw.get('verifier_result')or{};reward=(verifier.get('rewards')or{}).get('reward')
  if raw.get('exception_info'):reasons.append('native_exception:'+str(raw['exception_info'].get('exception_type')))
  if raw.get('infrastructure_errors'):reasons.append('native_infrastructure_errors')
  if raw.get('verifier')is None or not raw['verifier'].get('finished_at'):reasons.append('official_verifier_not_completed')
  if verifier.get('return_code')!=0 or reward not in [0,1]:reasons.append('official_verifier_missing_or_invalid_reward')
  verifier_files=[p for p in(d/'verifier').rglob('*')if p.is_file()];logs=[]
  if not verifier_files:reasons.append('verifier_logs_not_collected')
  for p in verifier_files:
   logs.append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)))
   if p.suffix in ['.txt','.log']or'output'in p.name or'stdout'in p.name or'stderr'in p.name:
    text=p.read_text(errors='replace')
    if re.search(r'(Temporary failure in name resolution|Could not resolve host|curl: \((6|7|18|22|28|35|60)\)|Failed to download|Failed to fetch|No matching distribution found|Could not fetch URL|SSL certificate problem)',text,re.I):reasons.append('verifier_download_or_network_failure:'+p.name)
  artifact=d/'artifacts/manifest.json'
  if not artifact.exists():reasons.append('artifact_manifest_not_collected')
  cleanup=None
  if runtime:
   args=['docker','--host',runtime['endpoint']];label='label=io.harbor.remote-docker.identity='+runtime['identity']
   found={kind:subprocess.check_output(args+[kind,'ls','--filter',label,'-q'],text=True,timeout=15).split()for kind in ['container','network','volume']}
   # container ls includes stopped containers via explicit -a below.
   found['container']=subprocess.check_output(args+['container','ls','-a','--filter',label,'-q'],text=True,timeout=15).split()
   cleanup=dict(checked_at=time.time(),resources=found,complete=not any(found.values()))
   if not cleanup['complete']:reasons.append('owned_resources_remain_after_native_cleanup')
  attempt=dict(native_trial_id=raw['id'],native_job_id=raw['config'].get('job_id'),trial_path=str(d),result_sha256=sha(result),runtime_proof_path=str(proof)if runtime else None,runtime_proof_sha256=sha(proof)if runtime else None,actual_runtime=runtime,official_verifier=verifier,verifier_timing=raw.get('verifier'),verifier_logs=logs,artifact_manifest_sha256=sha(artifact)if artifact.exists()else None,cleanup=cleanup,failures=reasons,model_generation_calls=0,official_verifier_reward_not_a_model_score=True)
  row.update(status='PASS'if not reasons else'FAIL',attempts=[attempt],latest_failure_reasons=reasons);rows.append(row)
 value=dict(kind='ACTUAL_SHARED30_NO_MODEL_ENVIRONMENT_ACCEPTANCE',updated_at=time.time(),frozen=False,sampling_manifest_sha256=sha(sample),tasks=rows,expected_unique_tasks=30,passed=sum(x['status']=='PASS'for x in rows),failed=sum(x['status']=='FAIL'for x in rows),running=sum(x['status']=='RUNNING'for x in rows),actual_model_generation_calls=0,shared_environment_not_150_repetitions=True,official_tasks_tests_verifiers_unmodified=True,source_sha256=sha(Path(__file__)))
 assert len(rows)==len({x['task_id']for x in rows})==30
 write(BASE/'ENV_PREFLIGHT_30_MANIFEST.json',value);print(json.dumps({k:value[k]for k in ['passed','failed','running','frozen','actual_model_generation_calls']}));return value
if __name__=='__main__':main()
