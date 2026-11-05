"""One bounded native install-only89 Job; no model execution or official scoring."""
import asyncio
import hashlib
from importlib import import_module
import json
import os
from pathlib import Path
import sys
import time
from harbor.job import Job
from harbor.models.job.config import JobConfig

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
B=R.parent
apply_trial_overrides=import_module('run-formal-native-tb21149-r6').apply_trial_overrides
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,value):
    q=p.with_name(p.name+'.tmp');q.write_text(json.dumps(value,indent=2)+'\n');q.replace(p)


def configuration():
    config=load(R/'configs/formal-native-job-r2.json')
    prior=load(R/'manifests/EPOCH3_DIAGNOSTIC_PREREGISTRATION.json')['tasks']
    tasks={Path(t['path']).name:t for t in config['tasks']}
    names=prior+sorted(set(tasks)-set(prior))
    assert len(names)==89 and len(set(names))==89
    config.update(job_name='qwen35-new772-new11-install-preflight',n_attempts=1,
        install_only=True,n_concurrent_trials=4,tasks=[tasks[n]for n in names],agents=config['agents'][:1])
    plan=dict(trials=[dict(trial_name=n+'__new11-install-r1',task_path=tasks[n]['path'],
        task_id=n,model_name=config['agents'][0]['model_name'],agent_override_timeout_sec=max(10800,
        __import__('tomllib').loads((Path(tasks[n]['path'])/'task.toml').read_text())['agent']['timeout_sec']))
        for n in names])
    return JobConfig.model_validate(config),plan


def report(folder,plan):
    expected={x['trial_name']:x for x in plan['trials']};rows=[]
    for p in sorted(folder.glob('*/result.json')):
        result=load(p);artifact=p.parent/'agent/artifact.json'
        installed=load(artifact)if artifact.exists()else None
        success=bool(result.get('exception_info')is None and installed and
            installed['wheel_sha256']=='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18')
        # Install-only explicitly ends before agent execution and verifier.
        assert result.get('verifier_result') is None
        rows.append(dict(task_id=expected[p.parent.name]['task_id'],trial_name=p.parent.name,
            result_sha256=sha(p),ready=success,install_artifact=installed,
            install_artifact_sha256=sha(artifact)if artifact.exists()else None,
            failure_phase=result.get('failure_phase'),
            exception_type=(result.get('exception_info')or{}).get('exception_type'),
            exception_message=(result.get('exception_info')or{}).get('exception_message'),
            no_model_attempt=True,no_official_score=True))
    ready=[r['task_id']for r in rows if r['ready']]
    value=dict(expected=89,terminal=len(rows),ready=len(ready),ready_task_ids=ready,
        failed=[r['task_id']for r in rows if not r['ready']],actual_model_attempts=0,
        official_scores=0,source_sha256=sha(__file__),updated_at=time.time(),rows=rows)
    save(R/'checks/NEW11_INSTALL_PREFLIGHT_STATUS_R1.json',value)
    return value


async def main():
    cfg,plan=configuration()
    assert not(cfg.jobs_dir/cfg.job_name).exists(),'Never recreate an existing native preflight Job'
    profiles=R/'configs/environment-profiles-agent-deps-r2.json'
    dependency=load(R/'checks/AGENT_PUBLIC_DEPENDENCY_DEPLOYMENT_R1.json')
    assert sha(profiles)==dependency['new_profiles_sha256']
    assert sha(R/'configs/agent-deps/rg')==dependency['rg_sha256']
    os.environ['SSH_AUTH_SOCK']=str(B/'near-r3-20261015/auth.sock')
    os.environ['OPENAI_API_KEY']='node18-local'
    job=await Job.create(cfg)
    assert len(job._trial_configs)==89
    effective=apply_trial_overrides(job._trial_configs,plan,load(profiles),namespace='q35new772install')
    job._remaining_trial_configs=job._trial_configs
    save(R/'manifests/NEW11_INSTALL_ACTUAL_TRIALS_R1.json',dict(trials=effective,
        profiles_sha256=sha(profiles),source_sha256=sha(__file__),actual_model_attempts_expected=0))
    lock=asyncio.Lock()
    async def ended(event):
        try:
            async with lock:await asyncio.to_thread(report,job.job_dir,plan)
        except Exception as error:
            with(R/'logs/install-preflight-audit-errors.jsonl').open('a')as f:
                f.write(json.dumps(dict(at=time.time(),error=repr(error)))+'\n')
    job.on_trial_ended(ended)
    await job.run()
    final=report(job.job_dir,plan);assert final['terminal']==89
    save(R/'checks/NEW11_INSTALL_PREFLIGHT_ALL_TERMINAL_R1.json',dict(
        completed=True,terminal=89,ready=final['ready'],failed=final['failed'],
        passed=final['ready']==89,status_sha256=sha(R/'checks/NEW11_INSTALL_PREFLIGHT_STATUS_R1.json'),
        actual_model_attempts=0,official_scores=0))


if __name__=='__main__':asyncio.run(main())
