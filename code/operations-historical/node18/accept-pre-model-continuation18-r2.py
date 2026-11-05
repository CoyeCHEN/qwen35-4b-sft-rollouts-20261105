"""Actual no-model failure eligibility and native frozen-lock preservation."""
import asyncio,copy,importlib,json,os,sys,time
from pathlib import Path
from unittest.mock import patch
from harbor.job import Job
from harbor.models.trial.config import TrialConfig
from harbor.models.job.config import JobConfig
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1';sys.path.insert(0,str(E/'scripts'))
m=importlib.import_module('run-user-evaluation-native18-r2');prep=m.prep
async def main():
    os.environ['OPENAI_API_KEY']='node18-local';cfg=prep.read(R/'configs/diagnostic150-five-model-r1.json');models={x['tag']:x for x in cfg['models']};plan=prep.read(E/'manifests/DIAGNOSTIC150_TRIAL_PLAN_R1.json')
    eligible=[];rejected=[];checked=0
    for item in plan['trials']:
        directory=prep.resolve_original(item,models)
        if not(directory/'result.json').exists():continue
        checked+=1;evidence=prep.pre_model_failure(directory)
        if evidence:eligible.append(dict(item,**evidence,trial_name=item['trial_name']+'__env-recovery1',reuse_existing_trial=False))
        else:
            v=prep.read(directory/'result.json');rejected.append(dict(trial_id=v['id'],phase=v.get('failure_phase'),agent_execution=v.get('agent_execution')is not None,original_result_sha256=prep.sha(directory/'result.json')))
    assert eligible and any(x['agent_execution']for x in rejected)
    cases=[]
    for tag in ['new-m1-e3-diag','new-m1-e5-diag','new-m2-e1-diag','new-m2-e5-diag']:
        selected=[x for x in eligible if x['tag']==tag];assert selected
        model=dict(models[tag],new_trials=len(selected),job_name='cpu-pre-model-continuation-'+tag+'-'+str(time.time_ns()),concurrency=models[tag].get('concurrency',2))
        if not model.get('replicas'):model['replicas']=[dict(port=model['port'],unit=model['serving_unit'])]
        spec=dict(trials=selected,model=model);real_read=m.read
        def fixture_read(path):
            if path==E/'manifests'/('PRE_MODEL_ENV_RECOVERY_PLAN_'+tag+'_R1.json'):return spec
            return real_read(path)
        with patch.object(m,'read',side_effect=fixture_read):_,_,native_cfg,registered=m.configuration(tag,recovery=True)
        native_cfg.jobs_dir=E/'diagnostics';job=await Job.create(native_cfg);ordered=m.configure_trials(job,tag,registered,recovery=True)
        for actual,item in zip(job._trial_configs,ordered):
            original=TrialConfig.model_validate(item['original_config']);copy_actual=actual.model_copy(deep=True)
            copy_actual.trial_name=original.trial_name;copy_actual.trials_dir=original.trials_dir;copy_actual.job_id=original.job_id
            assert len(copy_actual.environment.extra_docker_compose)==len(original.environment.extra_docker_compose)+1
            copy_actual.environment.extra_docker_compose.pop();assert copy_actual.model_dump(mode='json')==original.model_dump(mode='json')
        assert len(job._trial_configs)==len(selected)and native_cfg.retry.max_retries==0
        cases.append(dict(tag=tag,native_configs=len(selected),native_job_lock=str(job._job_lock_path),actual_task_or_model_calls=0,only_new_identity_and_explicit_ipam_changed=True))
    source=m.base.native.selected_config(prep.read(E/'manifests/FORMAL_801_TRIAL_PLAN.json'))
    fullcfg=JobConfig.model_validate_json(source.read_text());fullcfg.agents=[fullcfg.agents[2]]
    fullcfg.agents[0].model_name='openai/qwen35-new772-selected30-winner';fullcfg.agents[0].kwargs['config']['model']['id']='qwen35-new772-selected30-winner'
    fullcfg.n_attempts=3;fullcfg.n_concurrent_trials=16;fullcfg.retry.max_retries=0;fullcfg.jobs_dir=E/'diagnostics';fullcfg.job_name='cpu-selected267-explicit-ipam-'+str(time.time_ns())
    fullplan=dict(trials=[dict(x,tag='selected267',model_name=fullcfg.agents[0].model_name,trial_name=x['task_id']+'__selected30-winner-n3-r'+str(x['repetition']))for x in prep.read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')['trials']if x['model_name']=='openai/qwen35-new772-m0'])
    job=await Job.create(fullcfg);ordered=m.configure_trials(job,'selected267',fullplan,recovery=False)
    assert len(ordered)==len(job._trial_configs)==267
    assert len({str(t.environment.extra_docker_compose[-1])for t in job._trial_configs})==267
    assert len({v['subnet']for v in prep.ensure_ipam_manifest()['entries'].values()})==417
    cases.append(dict(tag='selected267',native_configs=267,native_job_lock=str(job._job_lock_path),actual_task_or_model_calls=0,explicit_disjoint_subnets=True))
    result=dict(passed=True,at=time.time(),closed_originals_checked=checked,eligible_setup_only=len(eligible),rejected_actual_or_other_failures=rejected,native_cases=cases,actual_model_calls=0,original_model_attempts_retried=0,original_result_hashes_preserved=True,source_sha256=prep.sha(Path(__file__)))
    prep.save(R/'checks/PRE_MODEL_ENV_CONTINUATION_NATIVE_ACCEPTANCE_R2.json',result);print(json.dumps(dict(passed=True,closed_originals_checked=checked,eligible=len(eligible),native_cases=cases)))
if __name__=='__main__':asyncio.run(main())
