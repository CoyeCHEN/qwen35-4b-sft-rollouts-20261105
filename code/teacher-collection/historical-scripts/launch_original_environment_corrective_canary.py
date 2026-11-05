"""One bounded native Job for the preregistered original-environment canary."""
from collections import Counter
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tomllib

from harbor.agents.installed.open_harness import OpenHarnessAgent
from harbor.models.job.config import JobConfig

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
NAME='cf-tmax-original-environment-canary-20261030'


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    file=ROOT/'configs/canary-original-environment-corrective9.json'
    receipt_file=ROOT/'checks/canary-original-environment-corrective9-submission.json'
    if file.exists() or receipt_file.exists() or (ROOT/'jobs'/NAME).exists():
        raise FileExistsError('Inspect the existing exact submission; never replay')
    plan=read(ROOT/'manifests/ORIGINAL_ENVIRONMENT_CORRECTIVE_CANARY_PLAN.json')
    assert read(ROOT/'checks/tmax-original-directory-native-agent-r4-v2.json')['passed']
    probes=list((ROOT/'jobs/original-environment-corrective-verifier-probe-20261030').glob('*/result.json'))
    if len(probes)!=2:raise ValueError('Both original native verifier probes must be terminal')
    for p in probes:
        result=read(p);log=(p.parent/'verifier/test-stdout.txt').read_text(errors='replace')
        if result.get('exception_info') or not result['verifier']['finished_at'] or result['verifier_result']['rewards']['reward']!=0:
            raise ValueError('Native verifier probe failed to score')
        if any(marker in log for marker in ['ERROR collecting','ModuleNotFoundError','ImportError','Failed to download']):
            raise ValueError('Verifier preparation failed before a trustworthy score')
        if not re.search(r'\b\d+ (?:failed|passed)\b',log):raise ValueError('No actual test execution evidence')
    manifests={pool:{r['task_id']:r for r in map(json.loads,(ROOT/'manifests'/name).open())}
        for pool,name in [('calibforge','CALIBFORGE_500_TASKS.jsonl'),('tmax','TMAX_RUNTIME_CANDIDATES_V2.jsonl')]}
    counts=Counter()
    for p in (ROOT/'jobs').glob('*/config.json'):
        cfg=read(p)
        if cfg.get('install_only') or not any(a.get('name')=='open-harness' for a in cfg.get('agents',[])):continue
        counts.update(Path(t['path']).name for t in cfg['tasks'])
        if not read(p.parent/'result.json')['finished_at']:raise ValueError('Another teacher Job is active; preserve global concurrency eight')
    chosen=[('calibforge',plan['cf_first_untried'],0)]
    chosen += [('tmax',ident,1) for ident in plan['tmax_second_attempts']]
    chosen += [('tmax',ident,0) for ident in plan['tmax_first_attempts']]
    if len(chosen)!=9 or len({x[1] for x in chosen})!=9:raise ValueError('Corrective cohort changed')
    tasks=[];identities=[]
    for pool,ident,prior in chosen:
        if counts[ident]!=prior:raise ValueError('Per-task attempt identity changed')
        row=manifests[pool][ident]
        if pool=='tmax':
            check=read(ROOT/'checks/tmax-environments-runtime-r4'/(ident+'.json'))
            if check['status']!='IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING':raise ValueError('Original initial state not ready')
            path=Path(check['prepared_task_path'])
        else:
            check=read(ROOT/'checks/cf-environments-v2'/(ident+'.json'))
            if check['status']!='IMAGE_IDENTITY_AND_BASIC_SETUP_PASSED':raise ValueError('CF image/setup not ready')
            path=Path(row['source_path'])
        config=tomllib.loads((path/'task.toml').read_text())
        if pool=='tmax' and (config['environment'].get('workdir')!='/home/user' or config['environment'].get('env',{}).get('HOME')!='/home/user'):
            raise ValueError('TMax original directory/HOME contract differs')
        if sha(path/'instruction.md')!=row['instruction_sha256']:raise ValueError('Original instruction changed')
        if config.get('agent',{}).get('timeout_sec',0)>10800:raise ValueError('Research override would shorten original deadline')
        tasks.append(dict(path=str(path)))
        identities.append(dict(pool=pool,task_id=ident,attempt=prior+1,split=row['split'],family_id=row['family_id'],
            task_path=str(path),task_toml_sha256=sha(path/'task.toml'),instruction_sha256=row['instruction_sha256'],image_id=check['image_id']))
    if sum(counts.values())+9>2000 or len(set(counts)|{x[1] for x in chosen})>1000 or max(counts.values())>2:
        raise ValueError('Authorized total/per-task caps would be exceeded')
    cfg=copy.deepcopy(read(ROOT/'configs/canary-summary-cf.json'))
    cfg.update(job_name=NAME,tasks=tasks,n_concurrent_trials=8,n_attempts=1,retry={'max_retries':0})
    cfg['environment']['kwargs']['project_namespace']='originalenvcanary20261030'
    parsed=JobConfig.model_validate(cfg);OpenHarnessAgent.preflight(parsed.agents[0].kwargs)
    with file.open('x') as stream:json.dump(cfg,stream,indent=2)
    record=dict(status='DISPATCH_REQUESTED_ACKNOWLEDGEMENT_PENDING',job_name=NAME,submitted_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        config_sha256=sha(file),requested_attempts=9,canary_tasks=identities,
        teacher_config_sha256=sha(ROOT/'configs/teacher-native-11tools-summary-r1.json'),wheel_sha256=parsed.agents[0].kwargs['wheel_sha256'],
        total_teacher_dispatches_after_submission=sum(counts.values())+9,unique_teacher_tasks=len(set(counts)|{x[1] for x in chosen}),
        global_concurrency=8,maximum_per_task_attempts=2,original_trials_preserved=True,no_task_replacement_after_teacher_attempt=True)
    with receipt_file.open('x') as stream:json.dump(record,stream,indent=2)
    command='umask 077; exec '+shlex.join(['env','PATH='+str(ROOT/'client-bin')+':'+os.environ['PATH'],
        'SSH_AUTH_SOCK=/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock',
        '/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/harbor','run','--config',str(file)])+' > '+shlex.quote(str(ROOT/'logs/canary-original-environment-corrective9.log'))+' 2>&1'
    result=subprocess.run(['tmux','-L','cf-tmax-teacher-20261029','new-session','-d','-s','original-environment-canary',command],capture_output=True,text=True,timeout=20)
    record.update(status='SUBMITTED_NATIVE_JOB_NOT_YET_VERIFIED' if result.returncode==0 else 'SUBMISSION_REJECTED',submission_returncode=result.returncode)
    receipt_file.write_text(json.dumps(record,indent=2));print(json.dumps(record))
    if result.returncode:raise RuntimeError('Submission rejected; inspect exact identity')


if __name__=='__main__':main()
