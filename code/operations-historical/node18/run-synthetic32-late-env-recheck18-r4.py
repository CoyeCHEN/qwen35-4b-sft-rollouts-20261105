"""One independent native NOP job for explicitly registered terminal env failures."""
import asyncio,importlib,os,time
from pathlib import Path
from harbor.job import Job
m=importlib.import_module('synthetic32-native-config18-r3');R=m.R;B=m.B;C=m.C;read=m.read;write=m.write;sha=m.sha
async def main():
 a=read(B/'LATE_ENV_RECHECK_ADMISSION_R4.json');assert a['unique_controller_owner']==read(C/'NATIVE_ADVANCE_OWNER.json')and a['source_sha256']==sha(Path(__file__))
 plan=read(Path(a['candidate_plan_path']));assert sha(Path(a['candidate_plan_path']))==a['candidate_plan_sha256'];assert set(a['tasks'])==set(plan['tasks'])and a['tasks'];d=m.deployment();assert plan['deployment_manifest_sha256']==sha(B/'SYNTHETIC32_DEPLOYMENT_R3.json')
 fresh=importlib.import_module('prepare-synthetic32-late-fail-plan18-r4').plan();assert set(a['tasks']).issubset(fresh['tasks']),'A pending/running NOP or cleanup uncertainty appeared after registration'
 for item in plan['eligibility']:assert sha(Path(item['original_trial_path'])/'result.json')==item['original_result_sha256']and item['scoped_resources_absent']and item['model_attempts']==0
 os.environ['PATH']=m.native.D['transport']['private_client_bin']+':'+os.environ['PATH'];os.environ['OPENAI_API_KEY']='node18-local';os.environ['TMPDIR']=str(R/'tmp');os.environ['RSI_ENV_PREFLIGHT_SPEC_BASE']=str(B/'env-runtime-r4')
 byid={x['task_id']:x for x in d['tasks']};specdir=B/'env-runtime-r4/specs';specdir.mkdir(parents=True,exist_ok=True)
 for task in a['tasks']:
  item=byid[task];assert not item['required_independent_recheck'];spec=dict(read(B/'env-runtime/specs'/(task+'.json')),deployment_manifest_sha256=sha(B/'SYNTHETIC32_DEPLOYMENT_R3.json'),image_identity_mode=item['mode'],expected_image_id=(item.get('expected_image_identity')or{}).get('image_id'),image_public_files=[],original_recipe_sha256=item['recipe_sha256']);p=specdir/(task+'.json')
  if p.exists():assert read(p)==spec
  else:write(p,spec)
 frozen,cfg=m.configuration('prep');cfg.tasks=[t for t in cfg.tasks if t.path.name in a['tasks']];cfg.job_name='qwen35-user-synthetic32-late-env-recheck-20261102-r4';assert len(cfg.tasks)==len(a['tasks'])and not(cfg.jobs_dir/cfg.job_name).exists()
 job=await Job.create(cfg);m.configure_trials(job,'prep',frozen)
 for t in job._trial_configs:t.trial_name=t.task.path.name+'__synthetic32-late-env-recheck-r4';t.environment.extra_docker_compose[-1]=Path(byid[t.task.path.name]['overlays']['eval']['path']);t.environment.kwargs['project_namespace']='q35synth32prepr4'
 job._remaining_trial_configs=job._trial_configs;p=B/'prep-LATE_RECHECK_ACTUAL_NATIVE_TRIALS_R4.json';write(p,dict(at=time.time(),native_job_id=str(job.id),trials=[t.model_dump(mode='json')for t in job._trial_configs],model_generation_calls=0,candidate_plan_sha256=a['candidate_plan_sha256']))
 registry=B/'env-runtime/RECHECK_REGISTRY_R1.json';value=read(registry)if registry.exists()else dict(actual_trial_manifests=[]);assert str(p)not in value['actual_trial_manifests'];value['actual_trial_manifests'].append(str(p));write(registry,value)
 result=await job.run();write(B/'LATE_RECHECK_ALL_TERMINAL_R4.json',dict(at=time.time(),terminal=len(result.trial_results),model_generation_calls=0))
if __name__=='__main__':asyncio.run(main())
