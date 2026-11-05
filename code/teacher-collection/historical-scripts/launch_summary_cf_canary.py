"""One authorized second attempt for the CF task with a summary-contract violation."""
from collections import Counter
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

from harbor.agents.installed.open_harness import OpenHarnessAgent
from harbor.models.job.config import JobConfig

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
TASK='data-science_20260514_134238_004'
JOB='cf-summary-contract-canary-20261030'
SOCKET='cf-tmax-teacher-20261029'
HARBOR='/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/harbor'


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    destination=ROOT/'checks/canary-summary-cf-submission.json'
    if destination.exists() or (ROOT/'jobs'/JOB).exists():
        raise FileExistsError('Existing submission identity must be observed, never replayed')
    contract=read(ROOT/'manifests/TEACHER_CONTRACT_SUMMARY_R1.json')
    teacher_file=ROOT/'configs/teacher-native-11tools-summary-r1.json'
    wheel=ROOT/'wheels/open_harness_ai-0.3.0+rsi.summary.20261030-py3-none-any.whl'
    if sha(teacher_file)!=contract['config_sha256'] or sha(wheel)!=contract['wheel_sha256']:
        raise ValueError('Reviewed summary contract identity differs')
    proof=read(ROOT/'checks/summary-r1-offline-teacher-contract.json')
    if not proof['passed'] or proof['teacher_config_sha256']!=contract['config_sha256']:
        raise ValueError('Installed-wheel offline contract proof absent')
    old_job=ROOT/'jobs/cf-tmax-canary-remaining14-20261030'
    originals=[read(p) for p in old_job.glob('*/result.json') if TASK in str(p)]
    if len(originals)!=1:raise ValueError('Original trial identity ambiguous')
    original=originals[0]
    audit=read(ROOT/'checks/cf-tmax-canary-remaining14-20261030-live-protocol.json')
    entries=[r for r in audit['trials'] if TASK in r['trial_directory']]
    if len(entries)!=1 or not any(v.get('source')=='compaction' for v in entries[0]['contract_violations']):
        raise ValueError('No demonstrated auxiliary contract failure for this task')
    counts=Counter();active=0
    for file in (ROOT/'jobs').glob('*/config.json'):
        config=read(file)
        if config.get('install_only') or not any(a.get('name')=='open-harness' for a in config.get('agents',[])):continue
        if config.get('n_attempts',1)!=1 or config.get('retry',{}).get('max_retries',0)!=0:
            raise ValueError('Unexpected teacher replicate/retry policy')
        counts.update(Path(t['path']).name for t in config['tasks'])
        result=file.parent/'result.json'
        if result.exists() and not read(result).get('finished_at'):
            stats=read(result)['stats'];active+=stats['n_running_trials']+stats['n_pending_trials']
    if counts[TASK]!=1 or sum(counts.values())+1>2000 or len(counts)>1000 or max(counts.values())>2:
        raise ValueError('Research per-task/global attempt limit would be exceeded')
    if active+1>8:raise ValueError('Combined teacher concurrency would exceed eight')
    cfg=copy.deepcopy(read(ROOT/'configs/canary-first2.json'))
    cfg.update(job_name=JOB,tasks=[original['config']['task']],n_attempts=1,n_concurrent_trials=8,retry={'max_retries':0})
    cfg['environment']['kwargs']['project_namespace']='cftmaxsummarycf20261030'
    kwargs=cfg['agents'][0]['kwargs']
    kwargs.update(wheel_path=str(wheel),wheel_sha256=contract['wheel_sha256'],config=read(teacher_file))
    parsed=JobConfig.model_validate(cfg);OpenHarnessAgent.preflight(parsed.agents[0].kwargs)
    if parsed.agents[0].override_timeout_sec!=10800 or parsed.agents[0].model_name!='deepseek/deepseek-flash':
        raise ValueError('Teacher model/deadline changed')
    file=ROOT/'configs/canary-summary-cf.json'
    with file.open('x') as stream:json.dump(cfg,stream,indent=2)
    record=dict(status='DISPATCH_REQUESTED_ACKNOWLEDGEMENT_PENDING',job_name=JOB,
        submitted_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),config_sha256=sha(file),
        teacher_config_sha256=contract['config_sha256'],wheel_sha256=contract['wheel_sha256'],
        requested_attempts=1,task_id=TASK,attempt=2,prior_trial_id=original['id'],
        reason='Observed compaction auxiliary request disabled Thinking and used 40960 output limit',
        total_teacher_dispatches_after_submission=sum(counts.values())+1,unique_teacher_tasks=len(counts),
        no_original_task_or_verifier_modification=True,global_concurrency=8,maximum_per_task_attempts=2)
    with destination.open('x') as stream:json.dump(record,stream,indent=2)
    command='umask 077; exec '+shlex.join(['env','PATH='+str(ROOT/'client-bin')+':'+os.environ['PATH'],
        'SSH_AUTH_SOCK=/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock',
        HARBOR,'run','--config',str(file)])+' > '+shlex.quote(str(ROOT/'logs/canary-summary-cf.log'))+' 2>&1'
    submitted=subprocess.run(['tmux','-L',SOCKET,'new-session','-d','-s','summary-cf',command],
        capture_output=True,text=True,timeout=20)
    record.update(status='SUBMITTED_NATIVE_JOB_NOT_YET_VERIFIED' if submitted.returncode==0 else 'SUBMISSION_REJECTED',
        submission_returncode=submitted.returncode)
    destination.write_text(json.dumps(record,indent=2));print(json.dumps(record))
    if submitted.returncode:raise RuntimeError('Submission rejected; inspect existing identity')


if __name__=='__main__':main()
