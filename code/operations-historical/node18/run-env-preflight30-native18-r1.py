"""Exactly the frozen30 tasks, actual CLI install + native NOP + official verifier."""
import asyncio,hashlib,importlib,json,os,sys,time
from pathlib import Path
from collections import Counter
from harbor.job import Job
from harbor.models.job.config import JobConfig
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1';BASE=R/'environment-preflight30';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control');sys.path[:0]=[str(R),str(E/'scripts')]
native=importlib.import_module('run-formal-native-tb2118-r2');prep=importlib.import_module('evaluation-preparation18-r1')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(v,indent=2)+'\n');t.replace(p)
async def main():
 admission=read(BASE/'ADMISSION_R1.json');owner=read(C/'NATIVE_ADVANCE_OWNER.json');assert owner==admission['unique_controller_owner']and sha(Path(__file__))==admission['source_sha256']
 assert(C/'USER_ENV_PREFLIGHT30_PAUSE_R1.json').exists()and not(C/'ENV_PREFLIGHT30_GATE_RELEASE_R1.json').exists()
 sampling=read(E/'manifests/DIAGNOSTIC30_SAMPLING_MANIFEST_R1.json');assert sha(E/'manifests/DIAGNOSTIC30_SAMPLING_MANIFEST_R1.json')=='cf3e08b04fb455c3ef1c2c23a501cbf2a649328235f33f6b83cce6ff44f41858'
 source=native.selected_config(read(E/'manifests/FORMAL_801_TRIAL_PLAN.json'));cfg=JobConfig.model_validate_json(source.read_text());cfg.agents=[cfg.agents[0]];cfg.agents[0].name=None;cfg.agents[0].import_path='env_preflight30_agent_r1:OpenHarnessPreflightNopAgent'
 selected={x['task_id']:x for x in sampling['selected_task_identities']};cfg.tasks=[t for t in cfg.tasks if t.path.name in selected];assert len(cfg.tasks)==30
 cfg.job_name='qwen35-env-preflight30-native-nop-20261102-r1';cfg.jobs_dir=BASE/'jobs';cfg.n_attempts=1;cfg.n_concurrent_trials=2;cfg.retry.max_retries=0
 cfg.environment.kwargs.update(endpoint=native.D['task_engine']['native_endpoint'],transfer_timeout_sec=native.D['task_engine']['transfer_timeout_sec'])
 os.environ['PATH']=native.D['transport']['private_client_bin']+':'+os.environ['PATH'];os.environ['OPENAI_API_KEY']='node18-local';os.environ['TMPDIR']=str(R/'tmp')
 endpoints=[];deployment=read(R/'configs/diagnostic150-five-model-r1.json')
 for model in deployment['models']:
  replicas=model.get('replicas')or[dict(port=model['port'])]
  for rep in replicas:endpoints.append(dict(url='http://172.17.0.1:'+str(rep['port'])+'/model_info',model_path=model['model_path'],weight_version=model['weight_version']))
 specdir=BASE/'specs';specdir.mkdir(parents=True,exist_ok=True);profiles=read(E/'configs/environment-profiles-agent-deps-r2.json')
 for task,identity in selected.items():
  p=Path(identity['path']);assert sha(p/'instruction.md')==identity['instruction_sha256']and sha(p/'task.toml')==identity['task_toml_sha256']
  for item in identity['official_tests']:assert sha(p/item['path'])==item['sha256']
  public=[]
  for file in profiles['terminal-bench/'+task]['environment']['extra_docker_compose']:
   doc=read(Path(file))
   for service in doc.get('services',{}).values():
    for mount in service.get('volumes',[]):
     if not isinstance(mount,dict)or mount.get('type')!='bind':continue
     source=Path(mount['source']);target=Path(mount['target']);assert source.exists()
     files=[source]if source.is_file()else[f for f in source.rglob('*')if f.is_file()]
     for f in sorted(files):public.append(dict(source=str(f),target=str(target if source.is_file()else target/f.relative_to(source)),sha256=sha(f),bytes=f.stat().st_size))
  write(specdir/(task+'.json'),dict(task_id=task,identity=identity,original_environment=identity['original_environment'],expected_image_id=identity['image_id'],engine_id=native.D['task_engine']['id'],public_files=public,model_endpoints=endpoints,wheel_sha256='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'))
 assert not(cfg.jobs_dir/cfg.job_name).exists(),'No recreation of existing native Job'
 job=await Job.create(cfg);plan=[]
 frozen=[x for x in read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')['trials']if x['model_name']=='openai/qwen35-new772-m0'and x['repetition']==1];bytask={x['task_id']:x for x in frozen}
 for t in job._trial_configs:plan.append(dict(bytask[t.task.path.name],trial_name=t.task.path.name+'__env-preflight30-nop-r1'))
 native.apply_trial_overrides(job._trial_configs,dict(trials=plan),profiles,namespace='q35envpreflight30r1')
 for t in job._trial_configs:prep.append_ipam(t,'selected267',t.task.path.name,2)
 job._remaining_trial_configs=job._trial_configs
 write(BASE/'ACTUAL_NATIVE_TRIALS_R1.json',dict(native_job_id=str(job.id),expected=30,trials=[t.model_dump(mode='json')for t in job._trial_configs],utility_agent_only=True,model_generation_calls=0,source_sha256=sha(Path(__file__)),sampling_manifest_sha256=sha(E/'manifests/DIAGNOSTIC30_SAMPLING_MANIFEST_R1.json')))
 def raw():
  rows=[]
  for p in job.job_dir.glob('*/result.json'):
   x=read(p);rows.append(dict(task_id=x['task_name'],trial_name=x['trial_name'],trial_id=x['id'],result_path=str(p),result_sha256=sha(p),reward=(x.get('verifier_result')or{}).get('rewards'),exception=(x.get('exception_info')or{}).get('exception_type'),infrastructure_errors=x.get('infrastructure_errors')))
  write(BASE/'NATIVE_PROGRESS_R1.json',dict(at=time.time(),native_job_id=str(job.id),terminal=len(rows),expected=30,rows=rows,actual_model_generation_calls=0,not_environment_pass_until_full_audit=True))
 async def ended(event):raw()
 job.on_trial_ended(ended);raw();result=await job.run();raw();assert len(result.trial_results)==30
 write(BASE/'NATIVE_ALL_TERMINAL_R1.json',dict(at=time.time(),native_job_id=str(job.id),terminal=30,model_generation_calls=0,full_audit_required=True))
if __name__=='__main__':asyncio.run(main())
