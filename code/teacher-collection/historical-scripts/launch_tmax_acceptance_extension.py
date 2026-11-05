"""One frozen, never-tried task completes the original-environment canary scope."""
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
TASK='task_004638_361c9edd'
JOB='tmax-original-environment-acceptance-extension-20261030'


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    file=ROOT/'configs/canary-tmax-acceptance-extension.json'
    receipt=ROOT/'checks/canary-tmax-acceptance-extension-submission.json'
    if file.exists() or receipt.exists() or (ROOT/'jobs'/JOB).exists():raise FileExistsError('Inspect existing submission; never replay')
    assert read(ROOT/'checks/scoped-ssh-client2-native-install8.json')['passed']
    probes=list((ROOT/'jobs/tmax-extra-canary-verifier-probe-20261030').glob('*/result.json'))
    assert len(probes)==1
    probe=read(probes[0]);log=(probes[0].parent/'verifier/test-stdout.txt').read_text(errors='replace')
    assert not probe.get('exception_info') and probe['verifier']['finished_at'] and probe['verifier_result']['rewards']['reward']==0
    assert re.search(r'\b\d+ (?:passed|failed)\b',log) and not any(s in log for s in ['ERROR collecting','ModuleNotFoundError','ImportError'])
    counts=Counter();active=0
    for p in (ROOT/'jobs').glob('*/config.json'):
        cfg=read(p)
        if cfg.get('install_only') or not any(a.get('name')=='open-harness' for a in cfg.get('agents',[])):continue
        counts.update(Path(t['path']).name for t in cfg['tasks'])
        result=read(p.parent/'result.json')
        if not result['finished_at']:active+=result['stats']['n_running_trials']+result['stats']['n_pending_trials']
    rows=list(map(json.loads,(ROOT/'manifests/TMAX_RUNTIME_CANDIDATES_V2.jsonl').open()))
    assert next(x['task_id'] for x in rows if not counts[x['task_id']])==TASK
    assert counts[TASK]==0 and sum(counts.values())+1<=2000 and len(counts)+1<=1000 and max(counts.values())<=2 and active+1<=8
    ready=read(ROOT/'checks/tmax-environments-runtime-r4'/(TASK+'.json'))
    assert ready['status']=='IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING'
    path=Path(ready['prepared_task_path']);task=tomllib.loads((path/'task.toml').read_text())
    assert task['environment']['workdir']=='/home/user' and task['environment']['env']['HOME']=='/home/user'
    cfg=copy.deepcopy(read(ROOT/'configs/canary-summary-cf.json'))
    cfg.update(job_name=JOB,tasks=[dict(path=str(path))])
    cfg['environment']['kwargs']['project_namespace']='tmaxacceptanceextension20261030'
    parsed=JobConfig.model_validate(cfg);OpenHarnessAgent.preflight(parsed.agents[0].kwargs)
    with file.open('x') as stream:json.dump(cfg,stream,indent=2)
    record=dict(status='DISPATCH_REQUESTED_ACKNOWLEDGEMENT_PENDING',job_name=JOB,submitted_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        config_sha256=sha(file),requested_attempts=1,task_id=TASK,attempt=1,additional_task_already_in_frozen_500=True,
        purpose='Additional acceptance evidence after a previous task exhausted its two attempts on infrastructure/contract failures; no task replacement',
        total_teacher_dispatches_after_submission=sum(counts.values())+1,unique_teacher_tasks=len(counts)+1,
        teacher_config_sha256=sha(ROOT/'configs/teacher-native-11tools-summary-r1.json'),wheel_sha256=parsed.agents[0].kwargs['wheel_sha256'],
        global_concurrency=8,maximum_per_task_attempts=2,ssh_wrapper_sha256=sha(ROOT/'client-bin-v2/ssh'))
    with receipt.open('x') as stream:json.dump(record,stream,indent=2)
    cmd='umask 077; exec '+shlex.join(['env','PATH='+str(ROOT/'client-bin-v2')+':'+os.environ['PATH'],
        'SSH_AUTH_SOCK=/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock',
        '/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/harbor','run','--config',str(file)])+' > '+shlex.quote(str(ROOT/'logs/canary-tmax-acceptance-extension.log'))+' 2>&1'
    x=subprocess.run(['tmux','-L','cf-tmax-teacher-20261029','new-session','-d','-s','tmax-acceptance-extension',cmd],capture_output=True,text=True,timeout=20)
    record.update(status='SUBMITTED_NATIVE_JOB_NOT_YET_VERIFIED' if x.returncode==0 else 'SUBMISSION_REJECTED',submission_returncode=x.returncode)
    receipt.write_text(json.dumps(record,indent=2));print(json.dumps(record));assert x.returncode==0


if __name__=='__main__':main()
