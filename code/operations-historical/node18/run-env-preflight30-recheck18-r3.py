"""Independent native NOP identities for explicitly registered failed environments."""
import asyncio, importlib, json, os, sys, time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101'); B=R/'environment-preflight30'; E=R/'formal-native-eval-r1'; C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
sys.path[:0]=[str(R),str(E/'scripts')]
from harbor.job import Job
from harbor.models.job.config import JobConfig
from environment_evidence_audit_r3 import read,write,sha
native=importlib.import_module('run-formal-native-tb2118-r2'); prep=importlib.import_module('evaluation-preparation18-r1')
async def main():
    admission=read(B/'RECHECK_ADMISSION_R3.json'); assert admission['unique_controller_owner']==read(C/'NATIVE_ADVANCE_OWNER.json') and admission['source_sha256']==sha(Path(__file__))
    cfg=JobConfig.model_validate_json(native.selected_config(read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')).read_text()); cfg.tasks=[t for t in cfg.tasks if t.path.name in admission['tasks']]
    assert len(cfg.tasks)==len(admission['tasks']); cfg.agents=[cfg.agents[0]]; cfg.agents[0].name=None; cfg.agents[0].import_path='env_preflight_shared_agent_r2:OpenHarnessPreflightNopAgent'
    cfg.job_name='qwen35-env-preflight30-native-recheck-20261102-r3'; cfg.jobs_dir=B/'jobs'; cfg.n_attempts=1; cfg.n_concurrent_trials=2; cfg.retry.max_retries=0
    os.environ['PATH']=native.D['transport']['private_client_bin']+':'+os.environ['PATH']; os.environ['OPENAI_API_KEY']='node18-local'; os.environ['TMPDIR']=str(R/'tmp'); os.environ['RSI_ENV_PREFLIGHT_SPEC_BASE']=str(B)
    assert not(cfg.jobs_dir/cfg.job_name).exists(); job=await Job.create(cfg)
    plan=[dict(x,trial_name=x['task_id']+'__env-preflight30-nop-r3') for x in read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')['trials'] if x['model_name']=='openai/qwen35-new772-m0' and x['repetition']==1 and x['task_id'] in admission['tasks']]
    profiles=read(B/'environment-profiles-recheck-r2.json'); native.apply_trial_overrides(job._trial_configs,dict(trials=plan),profiles,namespace='q35envpreflight30r3')
    for t in job._trial_configs: prep.append_ipam(t,'selected267',t.task.path.name,3)
    job._remaining_trial_configs=job._trial_configs
    actual=B/'ACTUAL_NATIVE_TRIALS_RECHECK_R3.json'; write(actual,dict(at=time.time(),native_job_id=str(job.id),trials=[t.model_dump(mode='json') for t in job._trial_configs],model_generation_calls=0,independent_recheck=True,source_sha256=sha(Path(__file__)),admission_sha256=sha(B/'RECHECK_ADMISSION_R3.json')))
    registry=B/'RECHECK_REGISTRY_R1.json'; previous=read(registry) if registry.exists() else dict(actual_trial_manifests=[]); assert str(actual) not in previous['actual_trial_manifests']; previous['actual_trial_manifests'].append(str(actual)); write(registry,previous)
    result=await job.run(); write(B/'RECHECK_ALL_TERMINAL_R3.json',dict(at=time.time(),terminal=len(result.trial_results),model_generation_calls=0))
if __name__=='__main__': asyncio.run(main())
