import asyncio,importlib,os,time
from pathlib import Path
from harbor.job import Job
from environment_evidence_audit_r3 import read,write,sha
m=importlib.import_module('synthetic32-native-config18-r1');R=m.R;B=m.B;C=m.C
async def main():
 a=read(B/'RECHECK_ADMISSION_R2.json');assert a['unique_controller_owner']==read(C/'NATIVE_ADVANCE_OWNER.json')and a['source_sha256']==sha(Path(__file__))
 os.environ['PATH']=m.native.D['transport']['private_client_bin']+':'+os.environ['PATH'];os.environ['OPENAI_API_KEY']='node18-local';os.environ['RSI_ENV_PREFLIGHT_SPEC_BASE']=str(B/'env-runtime');os.environ['TMPDIR']=str(R/'tmp')
 frozen,cfg=m.configuration('prep');cfg.tasks=[t for t in cfg.tasks if t.path.name in a['tasks']];assert len(cfg.tasks)==len(a['tasks']);cfg.job_name='qwen35-user-synthetic32-env-recheck-20261102-r2';assert not(cfg.jobs_dir/cfg.job_name).exists()
 job=await Job.create(cfg);m.configure_trials(job,'prep',frozen);byid={x['task_id']:x for x in frozen['tasks']}
 for t in job._trial_configs:
  item=byid[t.task.path.name];t.trial_name=t.task.path.name+'__synthetic32-env-recheck-r2';t.environment.extra_docker_compose[-1]=Path(item['overlays']['eval']['path']);t.environment.kwargs['project_namespace']='q35synth32prepr2'
 job._remaining_trial_configs=job._trial_configs;p=B/'prep-RECHECK_ACTUAL_NATIVE_TRIALS_R2.json';write(p,dict(at=time.time(),native_job_id=str(job.id),trials=[t.model_dump(mode='json')for t in job._trial_configs],model_generation_calls=0))
 registry=B/'env-runtime/RECHECK_REGISTRY_R1.json';value=read(registry)if registry.exists()else dict(actual_trial_manifests=[]);assert str(p)not in value['actual_trial_manifests'];value['actual_trial_manifests'].append(str(p));write(registry,value)
 result=await job.run();write(B/'RECHECK_ALL_TERMINAL_R2.json',dict(at=time.time(),terminal=len(result.trial_results),model_generation_calls=0))
if __name__=='__main__':asyncio.run(main())
