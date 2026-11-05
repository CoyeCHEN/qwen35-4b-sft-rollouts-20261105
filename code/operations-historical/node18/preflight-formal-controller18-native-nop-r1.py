"""One original-regex native NOP/Verifier Trial; excluded from formal801 and model budgets."""
import asyncio,hashlib,json,os,time
from pathlib import Path
from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.trial.config import EnvironmentConfig
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
async def main():
 assert read(R/'checks/FORMAL_CONTROLLER18_PATHS_ACCEPTANCE_R1.json')['passed']
 original=read(E/'configs/formal-native-job.json');task=next(x for x in original['tasks']if Path(x['path']).name=='regex-log')
 profile=read(E/'configs/environment-profiles-agent-deps-r2.json')['terminal-bench/regex-log']
 env=EnvironmentConfig.model_validate(profile['environment']);env.kwargs.update(endpoint='ssh://chenkeyi@127.0.0.1:18449',staging_root=str(E/'staging'),project_namespace='q35formal18nop')
 assert all(getattr(env,k)is None for k in ['override_cpus','override_memory_mb','override_storage_mb','override_gpus'])
 os.environ['PATH']=str(R/'formal-controller18-client-bin-r1')+':'+os.environ['PATH']
 cfg=JobConfig.model_validate(dict(job_name='formal-controller18-original-regex-nop-r1',jobs_dir=str(E/'diagnostics'),
  tasks=[task],agents=[dict(name='nop')],environment=env.model_dump(mode='json'),verifier=profile['verifier'],
  n_attempts=1,n_concurrent_trials=1,retry=dict(max_retries=0),seed=42))
 directory=cfg.jobs_dir/cfg.job_name;assert not directory.exists()
 source=Path(task['path']);hashes={n:sha(source/n)for n in ['instruction.md','task.toml','tests/test.sh']}
 job=await Job.create(cfg);result=await job.run();assert len(result.trial_results)==1
 files=list(directory.glob('*/result.json'));assert len(files)==1;p=files[0];raw=read(p)
 assert raw.get('exception_info')is None and not raw.get('infrastructure_errors')
 assert raw['verifier_result']['rewards']['reward']==0 and raw['verifier_result']['return_code']==0
 assert hashes=={n:sha(source/n)for n in hashes}
 assert p.stat().st_dev==R.stat().st_dev
 value=dict(passed=True,at=time.time(),kind='NATIVE_CONTROLLER18_ORIGINAL_TASK_NOP_VERIFIER_LEGAL_ZERO',
  native_job_id=str(result.id),trial_id=raw['id'],trial_name=raw['trial_name'],result_path=str(p),result_sha256=sha(p),
  reward=raw['verifier_result']['rewards'],verifier_return_code=raw['verifier_result']['return_code'],
  task_path=str(source),original_task_file_sha256=hashes,actual_host='18',hot_result_on_ssd=True,
  original_task_engine='149',engine_id='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5',actual_model_calls=0,
  formal801_or_teacher_attempt=False,original_resources_verifier_and_tests_unchanged=True,
  full_model_harness_joint_acceptance_not_claimed=True,source_sha256=sha(Path(__file__)))
 out=R/'checks/FORMAL_CONTROLLER18_NATIVE_NOP_ACCEPTANCE_R1.json';assert not out.exists();out.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))
if __name__=='__main__':asyncio.run(main())
