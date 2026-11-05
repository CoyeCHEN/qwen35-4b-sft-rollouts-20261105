"""One native Harbor shared59 NOP Job; bounded2, fixed Task resources, no Agent generation."""
import asyncio,importlib,json,os,shlex,subprocess,time,urllib.request
from pathlib import Path
from harbor.job import Job
from harbor.models.job.config import JobConfig
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'environment-preflight59-r1';E=R/'formal-native-eval-r1';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
native=importlib.import_module('run-formal-native-tb2118-r2');audit=importlib.import_module('audit-env-preflight59-native18-r1');read=audit.read;sha=audit.sha;write=audit.write

def configuration(plan):
 source=read(E/'manifests/FORMAL_801_TRIAL_PLAN.json');cfg=JobConfig.model_validate_json(native.selected_config(source).read_text());names={x['task_id']for x in plan['rows']};cfg.tasks=[t for t in cfg.tasks if t.path.name in names]
 assert len(names)==len(cfg.tasks)==59
 cfg.agents=cfg.agents[:1];agent=cfg.agents[0];agent.name=None;agent.import_path='env_preflight_shared_agent_r2:OpenHarnessPreflightNopAgent';agent.override_timeout_sec=agent.max_timeout_sec=None
 assert agent.kwargs['wheel_sha256']=='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'
 contract=agent.kwargs['config'];assert set(contract['tools'])=={'read','bash','edit','write','grep','find','ls','edit_patch','trajectory_read','bash_job'}and contract['finish']['enabled']and contract['toolResultBudget']['enabled']
 cfg.install_only=False
 cfg.job_name='qwen35-env-preflight59-native18-20261102-r1';cfg.jobs_dir=B/'jobs';cfg.n_attempts=1;cfg.n_concurrent_trials=2;cfg.retry.max_retries=0
 items={x['task_id']:dict(x,trial_name=x['task_id']+'__env-preflight59-nop-r1',agent_override_timeout_sec=None)for x in source['trials']if x['model_name']=='openai/qwen35-new772-m0'and x['repetition']==1 and x['task_id']in names}
 assert set(items)==names
 return cfg,items

def configure_trials(trials,items,plan):
 ordered=[items[t.task.path.name]for t in trials];assert len({t.task.path.name for t in trials})==59
 native.apply_trial_overrides(trials,dict(trials=ordered),read(R/'environment-preflight30/environment-profiles-recheck-r2.json'),namespace='q35envpreflight59r1')
 bytask={x['task_id']:x for x in plan['rows']}
 for trial in trials:
  item=bytask[trial.task.path.name];assert sha(Path(item['ipam']['path']))==item['ipam']['sha256'];trial.environment.extra_docker_compose.append(Path(item['ipam']['path']));assert trial.agent.override_timeout_sec is None and trial.agent.max_timeout_sec is None
 return ordered

async def main():
 admission=read(B/'ADMISSION_R1.json');plan=read(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json');owner=read(C/'NATIVE_ADVANCE_OWNER.json')
 assert admission['unique_controller_owner']==owner and admission['source_sha256']==sha(Path(__file__))
 assert(Path('/proc')/str(owner['pid'])/'stat').read_text().rsplit(')',1)[1].split()[19]==owner['start_ticks']
 assert admission['sampling_manifest_sha256']==sha(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json')
 proof=B/'PUBLIC_CACHE_MATERIALIZER_DEPLOYMENT_R1.json';assert sha(proof)==admission['public_cache_materializer_deployment_sha256']
 verified=read(proof);assert verified['source_sha256']==plan['public_cache_binding']['materializer_sha256']and verified['archive_receipt_sha256']==plan['public_cache_binding']['archive_receipt_sha256']
 for path,digest in admission['required_source_sha256'].items():assert sha(Path(path))==digest,path
 assert sha(E/'manifests/OFFICIAL_89_TASK_IDENTITIES.json')==plan['official89_manifest_sha256']and sha(R/'environment-preflight30/environment-profiles-recheck-r2.json')==plan['runtime_profiles_sha256']and sha(native.DEPLOYMENT)==plan['native_deployment_sha256']
 assert len(plan['rows'])==59 and not plan['blocked_external_generation_tasks']and plan['external_generation_scan']['known_llm_indications']==0
 shared=read(R/'environment-preflight30/ENV_PREFLIGHT_30_MANIFEST.json');assert shared['frozen']and shared['passed']==30 and sha(R/'environment-preflight30/ENV_PREFLIGHT_30_MANIFEST.json')==plan['shared30_manifest_sha256'];assert not({x['task_id']for x in shared['tasks']}&{x['task_id']for x in plan['rows']})
 roles=Path(plan['source_role_deployment']['path']);assert sha(roles)==plan['source_role_deployment']['sha256'];opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 for item in plan['rows']:
  official=item['official_identity'];taskroot=Path(official['path']);assert sha(taskroot/'task.toml')==official['task_toml_sha256']and sha(taskroot/'instruction.md')==official['instruction_sha256']
  for source in item['verifier_source_files']:assert sha(Path(source['path']))==source['sha256']
  spec=Path(item['spec']['path']);assert sha(spec)==item['spec']['sha256']
  for source in read(spec)['public_files']:assert Path(source['source']).is_file()and Path(source['source']).stat().st_size==source['bytes']
 for observed in read(roles)['effective_metadata']:
  with opener.open('http://127.0.0.1:'+str(observed['port'])+'/model_info',timeout=5)as response:live=json.load(response)
  assert live['model_path']==observed['model_info']['model_path']and live['weight_version']==observed['model_info']['weight_version']
 guard=R/'formal-controller18-docker-admission-env59-r1/bin/docker';assert sha(guard)==admission['docker_guard_sha256'];assert sha(C/'ENV_PREFLIGHT59_DOCKER_ADMISSION_POLICY_R1.json')==admission['docker_policy_sha256']
 os.environ['PATH']=str(guard.parent)+':'+native.D['transport']['private_client_bin']+':'+os.environ['PATH'];os.environ['OPENAI_API_KEY']='node18-local';os.environ['TMPDIR']=str(R/'tmp');os.environ['RSI_ENV_PREFLIGHT_SPEC_BASE']=str(B)
 engine=json.loads(subprocess.check_output(['docker','--host',native.D['task_engine']['native_endpoint'],'info','--format','{{json .}}'],text=True,timeout=20));assert engine['ID']==native.D['task_engine']['id']
 storage=importlib.import_module('run-accepted-common30-disk-recovery18-r2');assert sha(Path(storage.__file__))==admission['storage_probe_worker_sha256']
 async def disk_gate(phase):
  command=['python3','-c',storage.DISK_PROBE,json.dumps(dict(staging_root=native.D['task_engine']['staging_root'],docker_root_dir=engine['DockerRootDir']))]
  proc=await asyncio.create_subprocess_exec('ssh','-p','18449','chenkeyi@127.0.0.1',shlex.join(command),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
  try:out,err=await asyncio.wait_for(proc.communicate(),45)
  except TimeoutError:
   if proc.returncode is None:proc.kill()
   await proc.wait();write(B/'storage-gates'/(str(time.time_ns())+'.json'),dict(phase=phase,status='UNKNOWN',error='SSH fsync probe timed out; remote temporary-file cleanup unconfirmed'));raise RuntimeError('ENV59_STORAGE_GATE_UNKNOWN')from None
  record=dict(at=time.time(),phase=phase,return_code=proc.returncode,stdout=out.decode(errors='replace'),stderr=err.decode(errors='replace'));write(B/'storage-gates'/(str(time.time_ns())+'.json'),record);assert proc.returncode==0,record
  checked=json.loads(out);assert all(checked[k]for k in['passed','fsync_file_passed','fsync_directory_passed','readback_passed','probe_file_removed'])and checked['minimum_available_bytes']==64*1024**3
 cfg,items=configuration(plan);assert not(cfg.jobs_dir/cfg.job_name).exists(),'Never recreate a native NOP Job';await disk_gate('before-native-job')
 job=await Job.create(cfg);configure_trials(job._trial_configs,items,plan);job._remaining_trial_configs=job._trial_configs
 async def started(event):await disk_gate('before-environment:'+event.trial_name)
 async def cache(event):
  task=event.config.task.path.name;binding=plan['public_cache_binding']
  if task not in binding['task_images']:return
  assert event.result.environment_setup.finished_at and event.result.agent_setup.finished_at and event.result.agent_execution is None
  directory=Path(event.config.trials_dir)/event.trial_name;files=list(directory.glob('remote-docker-*.jsonl'));assert len(files)==1;record=json.loads(files[0].open().readline())
  command=['python3',binding['remote_materializer_path'],'--task-id',task,'--identity',record['identity'],'--workspace',record['workspace'],'--receipt-sha256',binding['archive_receipt_sha256']]
  proc=await asyncio.create_subprocess_exec('ssh','-p','18449','chenkeyi@127.0.0.1',shlex.join(command),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE);out,err=await asyncio.wait_for(proc.communicate(),600);assert proc.returncode==0,err.decode(errors='replace')[-3000:]
  proof=json.loads(out);assert proof['source_sha256']==binding['materializer_sha256']and proof['archive_sha256']==binding['archive_sha256']and proof['actual_private_cache']['passed']and proof['model_generation_calls']==0 and proof['official_dependency_versions_not_overridden'];write(directory/'PUBLIC_DEPENDENCY_CACHE_PREPARATION_R1.json',proof)
 job.on_trial_started(started);job.on_agent_started(cache)
 write(B/'ACTUAL_NATIVE_TRIALS_R1.json',dict(native_job_id=str(job.id),trials=[t.model_dump(mode='json')for t in job._trial_configs],source_sha256=sha(Path(__file__)),sampling_manifest_sha256=sha(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json'),agent_generation_calls=0))
 lock=asyncio.Lock()
 async def ended(event):
  try:
   async with lock:await asyncio.to_thread(audit.audit)
  except Exception as error:
   with(B/'audit-errors.jsonl').open('a')as stream:stream.write(json.dumps(dict(at=time.time(),error=repr(error)))+'\n')
 job.on_trial_ended(ended);await asyncio.to_thread(audit.audit);result=await job.run();assert len(result.trial_results)==59
 write(B/'NATIVE_ALL_TERMINAL_R1.json',dict(terminal=59,native_job_id=str(job.id),agent_generation_calls=0,source_sha256=sha(Path(__file__))))
 final=await asyncio.to_thread(audit.audit,True);print(json.dumps({k:final[k]for k in['passed','failed','unknown','terminal','frozen']}))
if __name__=='__main__':asyncio.run(main())
