"""Two independent official Torch271 NOPs, K1; no unrelated270 materialization."""
import asyncio,importlib,json,os,shlex,time
from pathlib import Path
from harbor.job import Job
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'environment-preflight59-r1';T=B/'torch271-recheck-r1';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
worker=importlib.import_module('run-env-preflight59-native18-r1');cleanup=importlib.import_module('cleanup-env59-torch27118-r1');native=worker.native;read=worker.read;write=worker.write;sha=worker.sha
def configuration(plan):
 cfg,items=worker.configuration(read(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json'));names={x['task_id']for x in plan['rows']};assert names==cleanup.TASKS
 cfg.tasks=[t for t in cfg.tasks if t.path.name in names];assert len(cfg.tasks)==2
 cfg.job_name='qwen35-env-preflight59-torch271-recheck-20261103-r1';cfg.jobs_dir=T/'jobs';cfg.n_concurrent_trials=1
 items={name:dict(items[name],trial_name=name+'__env-preflight59-nop-recheck-r1')for name in names};return cfg,items
def configure_trials(trials,items,plan):
 assert len(trials)==2 and {t.task.path.name for t in trials}==cleanup.TASKS;ordered=[items[t.task.path.name]for t in trials]
 native.apply_trial_overrides(trials,dict(trials=ordered),read(R/'environment-preflight30/environment-profiles-recheck-r2.json'),namespace='q35envpreflight59r1')
 bytask={x['task_id']:x for x in read(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json')['rows']}
 for t in trials:
  item=bytask[t.task.path.name];assert sha(Path(item['ipam']['path']))==item['ipam']['sha256'];t.environment.extra_docker_compose.append(Path(item['ipam']['path']));assert t.agent.override_timeout_sec is None and t.agent.max_timeout_sec is None
 return ordered
async def main():
 admission=read(T/'ADMISSION_R1.json');assert admission['unique_controller_owner']==read(C/'NATIVE_ADVANCE_OWNER.json')and admission['source_sha256']==sha(Path(__file__))and admission['plan_sha256']==sha(T/'PLAN_R1.json')
 for path,digest in admission['required_source_sha256'].items():assert sha(Path(path))==digest,path
 plan=read(T/'PLAN_R1.json');[cleanup.original(plan,item)for item in plan['rows']];receipt=read(T/'CLEANUP_COMPLETE_R1.json');assert receipt['passed']and len(receipt['rows'])==2 and all(not any(r['resources_after'].values())for r in receipt['rows'])
 assert {r['task_id']for r in receipt['rows']}==cleanup.TASKS and receipt['source_sha256']==sha(Path(cleanup.__file__))
 originals={x['task_id']:x for x in plan['rows']}
 for row in receipt['rows']:
  assert row['identity']==originals[row['task_id']]['identity']and row['original_result_sha256']==originals[row['task_id']]['original_result_sha256']and row['plan_sha256']==sha(T/'PLAN_R1.json')and row['source_sha256']==sha(Path(cleanup.__file__))
 assert plan['cache_policy']['project_torch270_archive_materialization']is False and plan['cache_policy']['official_torch_pin']=='2.7.1'
 guard=R/'formal-controller18-docker-admission-env59-r1/bin/docker';assert sha(guard)==admission['docker_guard_sha256'];os.environ['PATH']=str(guard.parent)+':'+native.D['transport']['private_client_bin']+':'+os.environ['PATH'];os.environ['OPENAI_API_KEY']='node18-local';os.environ['TMPDIR']=str(R/'tmp');os.environ['RSI_ENV_PREFLIGHT_SPEC_BASE']=str(B)
 for check in range(2):
  snap=await asyncio.to_thread(worker.audit.base.inventory,native.D['task_engine']['native_endpoint']);write(T/'inventory-admission-history'/(str(time.time_ns())+'.json'),snap)
  if all(v['ok']for v in snap['queries'].values()):break
 assert all(v['ok']for v in snap['queries'].values())and snap['queries']['engine']['data']['ID']==plan['engine_id'],'Two bounded inventory checks did not establish Engine/resources; no native Job created'
 assert not any(r['identity']in{x['identity']for x in plan['rows']}for k in['container','network','volume']for r in snap['queries'][k]['data'])
 storage=importlib.import_module('run-accepted-common30-disk-recovery18-r2')
 async def disk_gate(phase):
  command=['python3','-c',storage.DISK_PROBE,json.dumps(dict(staging_root=native.D['task_engine']['staging_root'],docker_root_dir=snap['queries']['engine']['data']['DockerRootDir']))];p=await asyncio.create_subprocess_exec('ssh','-p','18449','chenkeyi@127.0.0.1',shlex.join(command),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
  try:out,err=await asyncio.wait_for(p.communicate(),45)
  except TimeoutError:
   if p.returncode is None:p.kill()
   await p.wait();write(T/'storage-gates'/(str(time.time_ns())+'.json'),dict(phase=phase,status='UNKNOWN',error='SSH fsync probe timeout; remote cleanup unconfirmed'));raise RuntimeError('STORAGE_UNKNOWN')from None
  write(T/'storage-gates'/(str(time.time_ns())+'.json'),dict(phase=phase,return_code=p.returncode,stdout=out.decode(errors='replace'),stderr=err.decode(errors='replace')));assert p.returncode==0;value=json.loads(out);assert all(value[k]for k in['passed','fsync_file_passed','fsync_directory_passed','readback_passed','probe_file_removed'])and value['minimum_available_bytes']==64*1024**3
 cfg,items=configuration(plan);assert not(cfg.jobs_dir/cfg.job_name).exists(),'Never recreate a native NOP Job';await disk_gate('before-native-job');job=await Job.create(cfg);configure_trials(job._trial_configs,items,plan);job._remaining_trial_configs=job._trial_configs
 async def started(event):await disk_gate('before-environment:'+event.trial_name)
 async def policy(event):
  assert event.config.task.path.name in cleanup.TASKS and event.result.agent_setup.finished_at and event.result.agent_execution is None
  d=Path(event.config.trials_dir)/event.trial_name;assert not(d/'PUBLIC_DEPENDENCY_CACHE_PREPARATION_R1.json').exists()
  write(d/'PUBLIC_CACHE_POLICY_R1.json',dict(**plan['cache_policy'],task_id=event.config.task.path.name,plan_sha256=sha(T/'PLAN_R1.json'),source_sha256=sha(Path(__file__)),agent_generation_calls=0))
 job.on_trial_started(started);job.on_agent_started(policy)
 write(T/'ACTUAL_NATIVE_TRIALS_R1.json',dict(native_job_id=str(job.id),trials=[t.model_dump(mode='json')for t in job._trial_configs],source_sha256=sha(Path(__file__)),plan_sha256=sha(T/'PLAN_R1.json'),independent_recheck=True,agent_generation_calls=0,project_torch270_archive_materialization=False))
 result=await job.run();assert len(result.trial_results)==2;write(T/'NATIVE_ALL_TERMINAL_R1.json',dict(terminal=2,native_job_id=str(job.id),agent_generation_calls=0,source_sha256=sha(Path(__file__))))
if __name__=='__main__':asyncio.run(main())
