"""Three explicitly original-recipe NOP rechecks; no model generation."""
import asyncio,importlib,os,time
from pathlib import Path
from harbor.job import Job
m=importlib.import_module('synthetic32-native-config18-r3');R=m.R;B=m.B;C=m.C;read=m.read;write=m.write;sha=m.sha
async def main():
 a=read(B/'RECHECK_ADMISSION_R3.json');assert a['unique_controller_owner']==read(C/'NATIVE_ADVANCE_OWNER.json')and a['source_sha256']==sha(Path(__file__))
 os.environ['PATH']=m.native.D['transport']['private_client_bin']+':'+os.environ['PATH'];os.environ['OPENAI_API_KEY']='node18-local';os.environ['RSI_ENV_PREFLIGHT_SPEC_BASE']=str(B/'env-runtime-r3');os.environ['TMPDIR']=str(R/'tmp')
 d=m.deployment();tasks={x['task_id']for x in d['tasks']if x['required_independent_recheck']};assert len(tasks)==3 and set(a['tasks'])==tasks;m.make_specs(read(B/'FROZEN_USER_SYNTHETIC32_SOURCE_R2.json'),tasks)
 frozen,cfg=m.configuration('prep');cfg.tasks=[t for t in cfg.tasks if t.path.name in tasks];cfg.job_name='qwen35-user-synthetic32-original-recipe-recheck-20261102-r3';assert not(cfg.jobs_dir/cfg.job_name).exists();job=await Job.create(cfg);m.configure_trials(job,'prep',frozen)
 for t in job._trial_configs:t.trial_name=t.task.path.name+'__synthetic32-recipe-recheck-r3';t.environment.extra_docker_compose[-1]=Path(next(x for x in d['tasks']if x['task_id']==t.task.path.name)['overlays']['eval']['path'])
 job._remaining_trial_configs=job._trial_configs;p=B/'prep-RECHECK_ACTUAL_NATIVE_TRIALS_R3.json';write(p,dict(at=time.time(),native_job_id=str(job.id),trials=[t.model_dump(mode='json')for t in job._trial_configs],model_generation_calls=0,deployment_manifest_sha256=sha(B/'SYNTHETIC32_DEPLOYMENT_R3.json')))
 registry=B/'env-runtime/RECHECK_REGISTRY_R1.json';value=read(registry)if registry.exists()else dict(actual_trial_manifests=[]);assert str(p)not in value['actual_trial_manifests'];value['actual_trial_manifests'].append(str(p));write(registry,value)
 result=await job.run();write(B/'RECHECK_ALL_TERMINAL_R3.json',dict(at=time.time(),terminal=len(result.trial_results),model_generation_calls=0))
if __name__=='__main__':asyncio.run(main())
