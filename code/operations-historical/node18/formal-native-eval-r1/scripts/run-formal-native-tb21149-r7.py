"""One fixed 801-Trial Harbor Job; native TrialQueue owns continuous concurrency."""
import asyncio
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import urllib.request
from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.trial.config import EnvironmentConfig,VerifierConfig,TrialConfig
from importlib import import_module
_audit=import_module('audit-native-context-accounting-r2')
inspect_trial,summary=_audit.inspect_trial,_audit.summary

B=Path('/home/chenkeyi/.local/share/harbor-rsi')
R=B/'qwen35-new772-tb21-20261101'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):
    tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)


def apply_trial_overrides(trials,plan,profiles,namespace='q35new772n3'):
    effective=[]
    for trial,expected in zip(trials,plan['trials']):
        assert str(trial.task.path)==expected['task_path'] and trial.agent.model_name==expected['model_name']
        trial.trial_name=expected['trial_name']
        trial.agent=trial.agent.model_copy(deep=True)
        trial.agent.override_timeout_sec=expected['agent_override_timeout_sec']
        profile=profiles['terminal-bench/'+trial.task.path.name]
        env=EnvironmentConfig.model_validate(profile['environment'])
        assert all(getattr(env,k)is None for k in ['override_cpus','override_memory_mb','override_storage_mb','override_gpus'])
        env.kwargs.update(staging_root=str(R/'staging'),project_namespace=namespace)
        assert not env.force_build
        trial.environment=env
        trial.verifier=VerifierConfig.model_validate(profile['verifier'])
        assert trial.verifier.override_timeout_sec is None and trial.verifier.max_timeout_sec is None
        trial.agent.env.update(profile['agent_env'])
        bypass=[v for v in trial.agent.env.get('NO_PROXY','').split(',')if v]
        if '172.17.0.1'not in bypass:bypass.append('172.17.0.1')
        trial.agent.env['NO_PROXY']=trial.agent.env['no_proxy']=','.join(bypass)
        effective.append(trial.model_dump(mode='json'))
    assert len(effective)==len(plan['trials'])
    return effective


def selected_config(plan):
    original=R/'configs/formal-native-job.json'
    assert sha(original)==plan['config_sha256']
    deployment=read(R/'checks/FORMAL801_WHEEL_ONLY_DEPLOYMENT_R2.json')
    assert sha(R/'manifests/FORMAL_801_TRIAL_PLAN.json')==deployment['original_trial_plan_sha256']
    assert sha(original)==deployment['original_config_sha256']
    selected=R/'configs'/deployment['new_config']
    assert sha(selected)==deployment['new_config_sha256']
    old,new=read(original),read(selected)
    restored=json.loads(json.dumps(new))
    assert len(new['agents'])==len(old['agents'])==3
    for before,after,copy in zip(old['agents'],new['agents'],restored['agents']):
        assert after['kwargs']['wheel_sha256']==deployment['new_wheel_sha256']
        assert sha(Path(after['kwargs']['wheel_path']))==deployment['new_wheel_sha256']
        for key in ('wheel_path','wheel_sha256'):copy['kwargs'][key]=before['kwargs'][key]
    assert restored==old, 'Only the explicitly registered wheel identity may change'
    return selected


def validate_only():
    plan=read(R/'manifests/FORMAL_801_TRIAL_PLAN.json')
    config_file=selected_config(plan)
    cfg=JobConfig.model_validate_json(config_file.read_text())
    profiles_file=R/'configs/environment-profiles-agent-deps-r2.json'
    trials=[TrialConfig(task=task,agent=agent,environment=cfg.environment,verifier=cfg.verifier,
        trials_dir=R/'diagnostics/native-preview')for _ in range(cfg.n_attempts)for task in cfg.tasks for agent in cfg.agents]
    effective=apply_trial_overrides(trials,plan,read(profiles_file))
    write(R/'checks/NATIVE_801_TRIAL_CONFIG_PREFLIGHT_R7.json',dict(passed=True,actual_trials_started=0,
        source_sha256=sha(Path(__file__)),environment_profiles_sha256=sha(profiles_file),
        native_trial_configs=effective,models_must_still_complete_training_and_cold_admission=True))
    print(json.dumps(dict(passed=True,native_trial_configs=len(effective),actual_trials_started=0,
        original_12000_sec_preserved=sum(x['agent']['override_timeout_sec']==12000 for x in effective))))


def report(job_dir,plan):
    byname={x['trial_name']:x for x in plan['trials']};rows=[]
    cached_path=R/'checks/FORMAL_801_AUDIT_ROWS.jsonl'
    cached={x['trial_name']:x for x in (json.loads(line)for line in cached_path.read_text().splitlines())} if cached_path.exists() else {}
    for p in sorted(job_dir.glob('*/result.json')):
        row=cached.get(p.parent.name)
        if row is not None:
            assert sha(p)==row['result_sha256'],'A previously audited immutable Result changed'
        else:row=inspect_trial(p.parent)
        identity=byname[row['trial_name']]
        row.update(repetition=identity['repetition'],model_name=identity['model_name'])
        rows.append(row)
    output=dict(expected=801,terminal=len(rows),missing=801-len(rows),models={},updated_at=time.time(),
        raw_official_rewards_preserved=True,unknown_is_not_model_zero=True)
    for name in sorted({p['model_name']for p in plan['trials']}):
        selected=[r for r in rows if r['model_name']==name]
        stats=summary(selected,267);stats['unknown_or_pending']=267-stats['valid_scores']
        stats['rounds']={str(i):summary([r for r in selected if r['repetition']==i],89)for i in [1,2,3]}
        stats['at_least_one_confirmed_success_task_fraction']=len({r['task_id']for r in selected if r['task_success']})/89
        stats['score_is_final']=len(selected)==267
        output['models'][name]=stats
    tmp=cached_path.with_name(cached_path.name+'.tmp')
    tmp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in rows));tmp.replace(cached_path)
    write(R/'checks/FORMAL_801_STATUS.json',output)
    return output


async def main():
    plan=read(R/'manifests/FORMAL_801_TRIAL_PLAN.json')
    config_file=selected_config(plan)
    identities=read(R/'manifests/OFFICIAL_89_TASK_IDENTITIES.json')
    assert identities['all_images_present'] and len(identities['tasks'])==89
    # Only the authenticated sole training controller can publish this completed-stage handoff.
    admission=read(R/'manifests/THREE_MODEL_COLD_SERVING_ADMISSION.json')
    e2e=read(R/'checks/CONTEXT_RECOVERY_FULL_WHEEL_E2E_ACCEPTANCE_R1.json')
    setup=read(R/'checks/NEW11_INSTALL_PREFLIGHT_ALL_TERMINAL_R1.json')
    assert e2e['passed']and len(e2e['cases'])==6 and setup['passed']and setup['ready']==89
    assert admission['new_m1_epoch5_verified'] and admission['new_m2_epoch5_verified']
    assert admission['native_cold_servers_independently_started']
    assert admission['old_four_still_deferred']
    cfg=JobConfig.model_validate_json(config_file.read_text())
    job_dir=cfg.jobs_dir/cfg.job_name
    assert not job_dir.exists(),'Preserve existing native Job; never silently recreate/retry/delete Trials'
    profiles_path=R/'configs/environment-profiles-agent-deps-r2.json'
    profiles=read(profiles_path)
    assert sha(profiles_path)==admission['environment_profiles_sha256']
    os.environ['SSH_AUTH_SOCK']=str(B/'near-r3-20261015/auth.sock')
    os.environ['OPENAI_API_KEY']='node18-local'
    assert subprocess.check_output(['docker','--host',cfg.environment.kwargs['endpoint'],
        'info','--format','{{.ID}}'],text=True,timeout=20).strip()==identities['docker_engine_id']
    assert stat.S_IMODE((R/'staging').stat().st_mode)==0o700
    assert read(R/'checks/OFFICIAL_89_FULL_SOURCE_REVALIDATION_R1.json')['passed']
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for agent in cfg.agents:
        model=agent.kwargs['config']['model']
        expected=admission['models'][model['id']]
        with opener.open(model['baseUrl'].removesuffix('/v1')+'/model_info',timeout=15)as response:
            actual=json.loads(response.read())
        assert actual['model_path']==expected['model_path']
        assert actual['weight_version']==expected['weight_version']
        assert actual.get('has_image_understanding'),'Image-capable service is required for the fixed89'
    with (R/'native-evaluation-authority.lock').open('a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        job=await Job.create(cfg)
        assert len(job._trial_configs)==len(job._remaining_trial_configs)==801
        effective=apply_trial_overrides(job._trial_configs,plan,profiles)
        job._remaining_trial_configs=job._trial_configs
        write(R/'manifests/ACTUAL_801_NATIVE_TRIAL_CONFIGS.json',dict(job_id=str(job._id),trials=effective,
            trial_plan_sha256=sha(R/'manifests/FORMAL_801_TRIAL_PLAN.json'),environment_profiles_sha256=sha(profiles_path),
            source_sha256=sha(Path(__file__)),effective_config_sha256=sha(config_file),
            deployment_sha256=sha(R/'checks/FORMAL801_WHEEL_ONLY_DEPLOYMENT_R2.json'),all_original_tasks_and_resources_unchanged=True))
        audit_lock=asyncio.Lock()
        async def ended(event):
            # Observation failures never cancel other healthy native Trials.
            try:
                async with audit_lock:await asyncio.to_thread(report,job.job_dir,plan)
            except Exception as error:
                with(R/'logs/audit-errors.jsonl').open('a')as stream:stream.write(json.dumps(dict(at=time.time(),error=repr(error)))+'\n')
        job.on_trial_ended(ended)
        result=await job.run()
        final=report(job.job_dir,plan)
        assert final['terminal']==801
        membership=Counter((p['model_name'],p['task_id'])for p in plan['trials'])
        actual=Counter()
        for p in job.job_dir.glob('*/result.json'):
            row=read(p);identity=next(x for x in plan['trials']if x['trial_name']==row['trial_name'])
            actual[(identity['model_name'],identity['task_id'])]+=1
        assert actual==membership
        subprocess.run([sys.executable,str(R/'scripts/compare-formal801-readonly-r6.py')],check=True,timeout=14400)
        subprocess.run([sys.executable,str(R/'scripts/compare-epoch3-epoch5-readonly149-r4.py')],check=True,timeout=14400)
        detailed=read(R/'checks/TB21_N3_FULL_COMPARISON.json')
        assert detailed['complete'] and detailed['terminal']==801
        write(R/'checks/FORMAL_801_ALL_TERMINAL.json',dict(completed=True,actual_terminal=801,
            status_sha256=sha(R/'checks/FORMAL_801_STATUS.json'),native_job_id=str(result.id),
            full_comparison_sha256=sha(R/'checks/TB21_N3_FULL_COMPARISON.json'),
            old_four_may_now_resume=True,score_quality_must_be_reported_separately=True))


if __name__=='__main__':
    if sys.argv[1:] not in ([], ['--validate-only']):
        raise SystemExit('Usage: run-formal-native-tb21149-r7.py [--validate-only]')
    validate_only() if sys.argv[1:]==['--validate-only'] else asyncio.run(main())
