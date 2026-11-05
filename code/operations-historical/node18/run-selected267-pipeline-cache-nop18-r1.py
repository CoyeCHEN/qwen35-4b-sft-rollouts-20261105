"""One independent official pipeline NOP; no winner/model generation/other tasks."""
import asyncio,importlib,importlib.metadata,json,os,sys,time
from pathlib import Path
from harbor.job import Job
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control');B=R/'environment-preflight59-r1';O=R/'lifecycle-boundary-r1/selected267-pipeline-cache-nop-r1'
shared=importlib.import_module('run-env-preflight59-native18-r1');hook=importlib.import_module('run-user-evaluation-native18-r6');evidence=importlib.import_module('environment_evidence_audit_r4');read=shared.read;sha=shared.sha;write=shared.write
def configuration(plan):
 cfg,items=shared.configuration(plan);cfg.tasks=[x for x in cfg.tasks if x.path.name=='torch-pipeline-parallelism'];assert len(cfg.tasks)==1
 cfg.job_name='qwen35-selected267-pipeline-cache-native-nop-20261103-r1';cfg.jobs_dir=O/'jobs';cfg.n_attempts=1;cfg.n_concurrent_trials=1;cfg.retry.max_retries=0
 return cfg,items

def configure_trial(trial,items,row):
 expected=dict(items['torch-pipeline-parallelism'],trial_name='torch-pipeline-parallelism__selected267-cache-native-nop-r1')
 shared.native.apply_trial_overrides([trial],dict(trials=[expected]),read(R/'environment-preflight30/environment-profiles-recheck-r2.json'),namespace='q35selected267')
 assert sha(Path(row['ipam']['path']))==row['ipam']['sha256'];trial.environment.extra_docker_compose.append(Path(row['ipam']['path']))
 assert trial.agent.import_path=='env_preflight_shared_agent_r2:OpenHarnessPreflightNopAgent' and trial.agent.override_timeout_sec is None and trial.agent.max_timeout_sec is None
 assert trial.environment.kwargs['project_namespace']=='q35selected267' and not trial.environment.force_build
 assert row['official_identity']['original_verifier']['timeout_sec']==900 and trial.verifier.override_timeout_sec is None and trial.verifier.max_timeout_sec is None
 assert trial.environment.kwargs.get('cleanup_timeout_sec',120)==120

async def main():
 native_python=R/'env/harbor-native-eval-boundary-r1/bin/python'
 assert Path(sys.prefix).resolve()==native_python.parent.parent.resolve() and importlib.metadata.version('harbor')=='0.23.0+rsi.2'
 admission=read(O/'ADMISSION_R1.json');owner=read(C/'NATIVE_ADVANCE_OWNER.json');assert admission['native_python']==str(native_python);assert admission['unique_controller_owner']==owner and admission['source_sha256']==sha(Path(__file__))
 assert(Path('/proc')/str(owner['pid'])/'stat').read_text().rsplit(')',1)[1].split()[19]==owner['start_ticks']
 assert sha(Path(hook.__file__))==admission['formal_worker_sha256']
 plan=read(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json');assert sha(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json')=='76c5e01fcb0bc26809e7ae058f92c4933fd57ae32bdf91e4c8c4462331552a48'
 cache_path,cache_plan,spec=hook.pipeline_cache_plan(admission)
 row=next(x for x in plan['rows']if x['task_id']=='torch-pipeline-parallelism')
 for path,digest in [(Path(row['official_identity']['path'])/'task.toml',row['official_identity']['task_toml_sha256']),(Path(row['official_identity']['path'])/'instruction.md',row['official_identity']['instruction_sha256'])]+[(Path(x['path']),x['sha256'])for x in row['verifier_source_files']]:assert sha(path)==digest
 cfg,items=configuration(plan)
 guard=R/'formal-controller18-docker-admission-r5/bin/docker';policy=C/'ENV_PREFLIGHT30_DOCKER_ADMISSION_POLICY_R5.json'
 assert sha(guard)==admission['docker_wrapper_sha256']=='e49628bfe9a49d9a2c845fceee53f388bc5d45272ab6136a076bf3f735287a6c' and sha(policy)==admission['docker_policy_sha256']=='a92eab38738cff4245138c6d86087973f0f8e04cddc0297ef5c4113f729b3d35'
 gate=read(C/'ENV_PREFLIGHT30_GATE_RELEASE_R1.json');m=read(Path(gate['manifest_path']));assert sha(Path(gate['manifest_path']))==gate['manifest_sha256']and m['frozen']and m['passed']==30
 assert 'q35selected267'in read(policy)['accepted_resume_prefixes']
 os.environ['PATH']=str(guard.parent)+':'+shared.native.D['transport']['private_client_bin']+':'+os.environ['PATH'];os.environ['OPENAI_API_KEY']='node18-local';os.environ['TMPDIR']=str(R/'tmp');os.environ['RSI_ENV_PREFLIGHT_SPEC_BASE']=str(B)
 assert not(cfg.jobs_dir/cfg.job_name).exists(),'Preserve original native NOP identity'
 job=await Job.create(cfg);assert len(job._trial_configs)==1
 trial=job._trial_configs[0];configure_trial(trial,items,row)
 job._remaining_trial_configs=job._trial_configs
 async def cache(event):
  assert event.result.environment_setup.finished_at and event.result.agent_setup.finished_at and event.result.agent_execution is None and event.result.agent_result is None
  await hook.prepare_pipeline_cache(event,admission)
 job.on_agent_started(cache)
 write(O/'ACTUAL_NATIVE_TRIAL_R1.json',dict(native_job_id=str(job.id),trial=trial.model_dump(mode='json'),source_sha256=sha(Path(__file__)),native_python=str(native_python),native_prefix=sys.prefix,harbor_version=importlib.metadata.version('harbor'),formal_worker_sha256=sha(Path(hook.__file__)),public_cache_plan_sha256=sha(cache_path),model_generation_calls=0,not_part_of_shared59_or_model267=True))
 result=await job.run();assert len(result.trial_results)==1
 directory=Path(trial.trials_dir)/trial.trial_name;raw_path=directory/'result.json';raw=read(raw_path)
 try:
  inventory=evidence.inventory(trial.environment.kwargs['endpoint']);write(O/'FINAL_ENGINE_INVENTORY_R1.json',inventory)
  attempt=evidence.attempt(trial.model_dump(mode='json'),B,{inventory['endpoint']:inventory})
 except Exception as error:attempt=dict(status='UNKNOWN',reason=repr(error))
 out=dict(passed=False,at=time.time(),native_python=str(native_python),native_prefix=sys.prefix,harbor_version=importlib.metadata.version('harbor'),source_sha256=sha(Path(__file__)),formal_worker_sha256=sha(Path(hook.__file__)),native_job_id=str(job.id),native_trial_uuid=raw['id'],result_path=str(raw_path),result_sha256=sha(raw_path),raw_reward=(raw.get('verifier_result')or{}).get('rewards'),exception=raw.get('exception_info'),infrastructure_errors=raw.get('infrastructure_errors'),attempt=attempt,actual_model_generation_calls=0,not_part_of_shared59_or_model267=True,public_cache_plan_sha256=sha(cache_path))
 metadata=(raw.get('agent_result')or{}).get('metadata')or{};out['actual_model_generation_calls']=metadata.get('model_generation_calls')
 provider=next(directory.glob('remote-docker-*.jsonl'));last=json.loads(provider.read_text().splitlines()[-1]);out['native_cleanup_ack']=last
 proof=read(directory/'PUBLIC_DEPENDENCY_CACHE_PREPARATION_R1.json')if(directory/'PUBLIC_DEPENDENCY_CACHE_PREPARATION_R1.json').exists()else None;out['public_cache_preparation']=proof
 out['passed']=attempt['status']=='PASS'and out['raw_reward']=={'reward':0.0}and raw.get('exception_info')is None and not raw.get('infrastructure_errors')and proof is not None and proof['model_generation_calls']==0 and metadata.get('model_generation_calls')==0 and metadata.get('env_preflight_only') and last['action']=='cleaned'
 write(O/'PIPELINE_CACHE_NATIVE_NOP_ACCEPTANCE_R1.json',out);print(json.dumps(dict(passed=out['passed'],result_path=str(raw_path),raw_reward=out['raw_reward'],actual_model_generation_calls=0)));assert out['passed']
if __name__=='__main__':asyncio.run(main())
