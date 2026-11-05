"""Independent one-Task NOP after exact terminal cleanup; no model generation."""
import asyncio,importlib,json,os,time
from pathlib import Path
from harbor.job import Job
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'environment-preflight59-r1';Q=B/'extract-elf-recheck-r1';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
worker=importlib.import_module('run-env-preflight59-native18-r1');cleanup=importlib.import_module('cleanup-env59-extract-elf18-r1');native=worker.native;read=worker.read;write=worker.write;sha=worker.sha

def configuration(plan):
 cfg,items=worker.configuration(read(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json'));cfg.tasks=[t for t in cfg.tasks if t.path.name=='extract-elf'];assert len(cfg.tasks)==1
 cfg.job_name='qwen35-env-preflight59-extract-elf-recheck-20261103-r1';cfg.jobs_dir=Q/'jobs';cfg.n_concurrent_trials=1
 items={'extract-elf':dict(items['extract-elf'],trial_name='extract-elf__env-preflight59-nop-recheck-r1')}
 return cfg,items

def configure_trials(trials,items,plan):
 assert len(trials)==1 and trials[0].task.path.name=='extract-elf';ordered=[items[t.task.path.name]for t in trials]
 native.apply_trial_overrides(trials,dict(trials=ordered),read(R/'environment-preflight30/environment-profiles-recheck-r2.json'),namespace='q35envpreflight59r1')
 item=next(x for x in read(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json')['rows']if x['task_id']=='extract-elf');assert sha(Path(item['ipam']['path']))==item['ipam']['sha256'];trials[0].environment.extra_docker_compose.append(Path(item['ipam']['path']))
 assert trials[0].agent.override_timeout_sec is None and trials[0].agent.max_timeout_sec is None
 return ordered

async def main():
 admission=read(Q/'ADMISSION_R1.json');assert admission['unique_controller_owner']==read(C/'NATIVE_ADVANCE_OWNER.json')and admission['source_sha256']==sha(Path(__file__))
 plan=read(Q/'PLAN_R1.json');assert sha(Q/'PLAN_R1.json')==admission['plan_sha256'];cleanup.original(plan)
 for path,digest in admission['required_source_sha256'].items():assert sha(Path(path))==digest,path
 receipt=read(Q/'CLEANUP_COMPLETE_R1.json');assert receipt['passed']and receipt['original_identity']==plan['original_identity']and receipt['original_result_sha256']==plan['original_result_sha256']and not any(receipt['resources_after'].values())
 guard=R/'formal-controller18-docker-admission-env59-r1/bin/docker';assert sha(guard)==admission['docker_guard_sha256'];os.environ['PATH']=str(guard.parent)+':'+native.D['transport']['private_client_bin']+':'+os.environ['PATH'];os.environ['OPENAI_API_KEY']='node18-local';os.environ['TMPDIR']=str(R/'tmp');os.environ['RSI_ENV_PREFLIGHT_SPEC_BASE']=str(B)
 snapshots=worker.audit.base.inventory(native.D['task_engine']['native_endpoint']);assert all(v['ok']for v in snapshots['queries'].values())and snapshots['queries']['engine']['data']['ID']==plan['engine_id']
 assert not any(x['identity']==plan['original_identity']for k in ['container','network','volume']for x in snapshots['queries'][k]['data'])
 storage=importlib.import_module('run-accepted-common30-disk-recovery18-r2')
 async def disk_gate(phase):
  import shlex
  command=['python3','-c',storage.DISK_PROBE,json.dumps(dict(staging_root=native.D['task_engine']['staging_root'],docker_root_dir=snapshots['queries']['engine']['data']['DockerRootDir']))]
  p=await asyncio.create_subprocess_exec('ssh','-p','18449','chenkeyi@127.0.0.1',shlex.join(command),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
  try:out,err=await asyncio.wait_for(p.communicate(),45)
  except TimeoutError:
   if p.returncode is None:p.kill()
   await p.wait();write(Q/'storage-gates'/(str(time.time_ns())+'.json'),dict(phase=phase,status='UNKNOWN',error='SSH fsync probe timeout; remote cleanup unconfirmed'));raise RuntimeError('STORAGE_UNKNOWN')from None
  write(Q/'storage-gates'/(str(time.time_ns())+'.json'),dict(phase=phase,return_code=p.returncode,stdout=out.decode(errors='replace'),stderr=err.decode(errors='replace')));assert p.returncode==0;proof=json.loads(out)
  assert all(proof[k]for k in['passed','fsync_file_passed','fsync_directory_passed','readback_passed','probe_file_removed'])and proof['minimum_available_bytes']==64*1024**3
 cfg,items=configuration(plan);assert not(cfg.jobs_dir/cfg.job_name).exists(),'Never recreate native Job';await disk_gate('before-native-job')
 job=await Job.create(cfg);configure_trials(job._trial_configs,items,plan);job._remaining_trial_configs=job._trial_configs
 async def started(event):await disk_gate('before-environment:'+event.trial_name)
 job.on_trial_started(started);write(Q/'ACTUAL_NATIVE_TRIALS_R1.json',dict(native_job_id=str(job.id),trials=[t.model_dump(mode='json')for t in job._trial_configs],source_sha256=sha(Path(__file__)),plan_sha256=sha(Q/'PLAN_R1.json'),independent_recheck=True,agent_generation_calls=0))
 result=await job.run();assert len(result.trial_results)==1
 write(Q/'NATIVE_ALL_TERMINAL_R1.json',dict(terminal=1,native_job_id=str(job.id),agent_generation_calls=0,source_sha256=sha(Path(__file__))))
if __name__=='__main__':asyncio.run(main())
