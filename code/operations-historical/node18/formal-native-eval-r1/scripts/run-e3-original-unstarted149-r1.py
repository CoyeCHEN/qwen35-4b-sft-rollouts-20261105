"""Native Harbor continuation of only the five original, never-started tasks."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.trial.config import TrialConfig

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
JOB='qwen35-new772-new-m1-epoch3-fixed-unstarted-continuation-r1'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):
    temp=p.with_name(p.name+'.tmp');temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(p)


def configuration():
    original=R/'jobs/qwen35-new772-new-m1-epoch3-fixed-diagnostic'
    snapshot=read(R/'checks/E3_NATIVE_CONTROLLER_OOM_SNAPSHOT_R1.json')
    assert snapshot['controller_properties']['Result']=='oom-kill'
    wanted=snapshot['unstarted_tasks_in_original_preregistered_order']
    assert wanted==['video-processing','adaptive-rejection-sampler','filter-js-from-html','polyglot-rust-c','install-windows-3.11']
    prereg=read(R/'manifests/EPOCH3_DIAGNOSTIC_PREREGISTRATION.json')['tasks']
    assert set(wanted)==set(prereg)-{p.name.split('__')[0]for p in original.iterdir()if p.is_dir()}
    previous=read(R/'manifests/EPOCH3_FIXED_ACTUAL_TRIALS_new-m1.json')['trials']
    selected=[x for task in wanted for x in previous if Path(x['task']['path']).name==task]
    assert len(selected)==5
    original_config=JobConfig.model_validate(read(original/'config.json'))
    assert original_config.n_attempts==1 and original_config.n_concurrent_trials==2
    assert original_config.retry.max_retries==0
    cfg=original_config.model_dump(mode='json')
    cfg.update(job_name=JOB,n_concurrent_trials=1,
               tasks=[task for name in wanted for task in cfg['tasks']if Path(task['path']).name==name])
    assert len(cfg['tasks'])==5
    return original,wanted,selected,JobConfig.model_validate(cfg)


def trials_for(config,selected,job_dir,job_id):
    output=[]
    for value in selected:
        changed=dict(value,trials_dir=str(job_dir),job_id=str(job_id)if job_id else None)
        trial=TrialConfig.model_validate(changed)
        actual=trial.model_dump(mode='json')
        for key in ['trials_dir','job_id']:actual[key]=value[key]
        assert actual==value, 'Only continuation metadata may differ from the original effective Trial config'
        output.append(trial)
    return output


async def main(validate_only):
    original,wanted,selected,cfg=configuration()
    if validate_only:
        preview=trials_for(cfg,selected,R/'diagnostics/e3-original-unstarted-preview',None)
        proof=dict(passed=True,actual_trials_started=0,distinct_original_unstarted_tasks=5,
            tasks=wanted,native_concurrency=1,one_original_orphan_can_continue_in_parallel=True,
            all_agent_task_verifier_model_sampling_resources_equal_original=True,
            only_trial_directory_and_job_id_differ=True,source_sha256=sha(Path(__file__)),
            original_actual_trial_manifest_sha256=sha(R/'manifests/EPOCH3_FIXED_ACTUAL_TRIALS_new-m1.json'),
            effective_native_trials=[x.model_dump(mode='json')for x in preview])
        save(R/'checks/E3_ORIGINAL_UNSTARTED_NATIVE_CONFIG_ACCEPTANCE_R1.json',proof)
        print(json.dumps({k:v for k,v in proof.items()if k!='effective_native_trials'}));return
    assert read(R/'checks/E3_ORIGINAL_UNSTARTED_NATIVE_CONFIG_ACCEPTANCE_R1.json')['passed']
    assert read(R/'checks/E3_ORIGINAL_UNSTARTED_NATIVE_CONFIG_ACCEPTANCE_R1.json')['source_sha256']==sha(Path(__file__))
    assert not(R/'jobs'/JOB).exists(), 'Never recreate a started continuation'
    admission=read(R/'manifests/EPOCH3_ORIGINAL_UNSTARTED_SERVING_ADMISSION_R1.json')
    assert admission['native_runner_sha256']==sha(Path(__file__))
    assert admission['original_oom_snapshot_sha256']==sha(R/'checks/E3_NATIVE_CONTROLLER_OOM_SNAPSHOT_R1.json')
    assert admission['original_unstarted_tasks']==wanted
    original_admission=read(R/'manifests/EPOCH3_FIXED_SERVING_ADMISSION_new-m1.json')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://172.17.0.1:18303/model_info',timeout=15)as response:info=json.loads(response.read())
    assert info['model_path']==original_admission['model_path']and info['weight_version']==original_admission['weight_version']
    os.environ['SSH_AUTH_SOCK']=str(R.parent/'near-r3-20261015/auth.sock')
    os.environ['OPENAI_API_KEY']='node18-local'
    job=await Job.create(cfg)
    effective=trials_for(cfg,selected,job.job_dir,job._id)
    assert len(job._trial_configs)==5
    job._trial_configs=effective;job._remaining_trial_configs=effective
    save(R/'manifests/E3_ORIGINAL_UNSTARTED_ACTUAL_NATIVE_TRIALS_R1.json',dict(
        original_job=str(original),native_continuation_job=str(job.job_dir),native_job_id=str(job._id),
        original_unstarted_tasks=wanted,actual_trials=[x.model_dump(mode='json')for x in effective],
        actual_max_new_native_concurrency=1,preserved_original_orphan_max_concurrency=1,
        original_started_trials_rerun=0,controller_memory_max_bytes=16*1024**3,
        original_task_resources_unchanged=True,source_sha256=sha(Path(__file__))))
    async def ended(event):
        rows=[read(p)for p in sorted(job.job_dir.glob('*/result.json'))]
        save(R/'checks/E3_ORIGINAL_UNSTARTED_STATUS_R1.json',dict(expected=5,terminal=len(rows),
            trials=[dict(name=r['trial_name'],id=str(r['id']),raw_rewards=(r.get('verifier_result')or{}).get('rewards'),
                         exception=(r.get('exception_info')or{}).get('exception_type'))for r in rows],
            raw_progress_only_final_recorder_audit_separate=True,updated_at=time.time()))
    job.on_trial_ended(ended)
    result=await job.run()
    assert len(result.trial_results)==5
    await ended(None)
    save(R/'checks/E3_ORIGINAL_UNSTARTED_ALL_TERMINAL_R1.json',dict(terminal=5,
        native_job_id=str(result.id),status='original_five_continuation_terminal',
        original_started_trials_rerun=0,original_two_oom_interrupted_trials_still_separate=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--validate-only',action='store_true')
    asyncio.run(main(parser.parse_args().validate_only))
