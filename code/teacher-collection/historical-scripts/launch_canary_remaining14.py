"""Secure, one-time native Harbor dispatch of the other fourteen canary tasks."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tomllib

from harbor.agents.installed.open_harness import OpenHarnessAgent
from harbor.models.job.config import JobConfig

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
HARBOR='/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/harbor'
SOCKET='cf-tmax-teacher-20261029'


def main():
    incoming=json.load(sys.stdin);secret=incoming['DEEPSEEK_API_KEY']
    if not isinstance(secret,str) or not secret:raise ValueError('Authorized credential absent')
    file=ROOT/'configs/canary-remaining14.json';sha=hashlib.sha256(file.read_bytes()).hexdigest()
    if sha!=incoming['config_sha256']:raise ValueError('Reviewed canary config changed')
    raw=json.loads(file.read_text());config=JobConfig.model_validate(raw)
    if not(config.job_name=='cf-tmax-canary-remaining14-20261030' and config.n_attempts==1
        and config.retry.max_retries==0 and config.n_concurrent_trials==8 and len(config.tasks)==14
        and len(config.agents)==1 and not config.install_only):raise ValueError('Authorized canary scope changed')
    if (Path(config.jobs_dir)/config.job_name).exists():raise FileExistsError('Observe existing native job; no replay')
    if (ROOT/'checks/canary-remaining14-submission.json').exists():raise FileExistsError('Submission identity already exists; inspect acknowledgement')
    agent=config.agents[0];OpenHarnessAgent.preflight(agent.kwargs)
    teacher=ROOT/'configs/teacher-native-11tools.json'
    if agent.kwargs['config']!=json.loads(teacher.read_text()) or agent.model_name!='deepseek/deepseek-flash' or agent.override_timeout_sec!=10800:
        raise ValueError('Frozen teacher contract changed')
    contract=json.loads((ROOT/'manifests/TEACHER_CONTRACT_CANDIDATE.json').read_text())
    if hashlib.sha256(teacher.read_bytes()).hexdigest()!=contract['config_sha256']:raise ValueError('Teacher config identity changed')
    for job,count in [('cf-remaining7-verifier-probe-r2-20261030',7),
        ('tmax-startup-native-verifier-probe-20261030',1),('tmax-remaining6-verifier-probe-20261030',6)]:
        results=[json.loads(p.read_text()) for p in (ROOT/'jobs'/job).glob('*/result.json')]
        if len(results)!=count or any(x.get('exception_info') or not x.get('verifier_result') for x in results):
            raise ValueError('Native verifier preparation has not completed: '+job)
    prior_name='cf-tmax-canary-first2-20261030';prior=ROOT/'jobs'/prior_name
    results=[json.loads(p.read_text()) for p in prior.glob('*/result.json')]
    if len(results)!=2:raise ValueError('First two teacher trials are not terminal')
    for other in (ROOT/'jobs').glob('*/config.json'):
        settings=json.loads(other.read_text())
        if not settings.get('install_only') and any(a.get('name')=='open-harness' for a in settings.get('agents',[])) and other.parent.name!=prior_name:
            raise ValueError('Unexpected teacher job ownership requires inspection')
    live=subprocess.run(['tmux','-L',SOCKET,'list-sessions'],capture_output=True,text=True,timeout=10)
    if live.returncode==0:raise RuntimeError('Private teacher tmux still has an active session')
    cf_ids=json.loads((ROOT/'manifests/SAMPLING_MANIFEST.json').read_text())['pools']['calibforge']['canary_task_ids']
    tf_ids=json.loads((ROOT/'checks/tmax-runtime-candidates-v2.json').read_text())['canary_task_ids']
    cf={r['task_id']:r for r in map(json.loads,(ROOT/'manifests/CALIBFORGE_500_TASKS.jsonl').open())}
    tf={r['task_id']:r for r in map(json.loads,(ROOT/'manifests/TMAX_RUNTIME_CANDIDATES_V2.jsonl').open())}
    expected=[]
    for a,b in zip(cf_ids[1:],tf_ids[1:]):expected.extend([('calibforge',cf[a]),('tmax',tf[b])])
    selected=[]
    for settings,(pool,row) in zip(raw['tasks'],expected):
        path=Path(settings['path'])
        if path.name!=row['task_id'] or hashlib.sha256((path/'instruction.md').read_bytes()).hexdigest()!=row['instruction_sha256']:
            raise ValueError('Original canary identity/instruction changed')
        task=tomllib.loads((path/'task.toml').read_text())
        if task.get('agent',{}).get('timeout_sec',0)>10800:raise ValueError('Override would shorten original deadline')
        image=json.loads(subprocess.run(['docker','image','inspect',task['environment']['docker_image']],
            check=True,capture_output=True,text=True,timeout=20).stdout)[0]
        selected.append(dict(pool=pool,task_id=row['task_id'],split=row['split'],family_id=row['family_id'],
            task_path=str(path),instruction_sha256=row['instruction_sha256'],image_id=image['Id'],attempt=1))
    record=dict(status='DISPATCH_REQUESTED_ACKNOWLEDGEMENT_PENDING',
        launched_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),job_name=config.job_name,
        config_sha256=sha,teacher_config_sha256=contract['config_sha256'],wheel_sha256=agent.kwargs['wheel_sha256'],
        canary_tasks=selected,prior_terminal_teacher_attempts=2,requested_attempts=14,
        canary_total_unique_tasks=16,canary_tasks_count_toward_500_each=True,global_native_concurrency=8,
        total_unique_teacher_task_cap=1000,total_complete_attempt_cap=2000,native_retry=0,
        credential_transport='Encrypted SSH stdin -> process environment -> private tmux; no argv value')
    destination=ROOT/'checks/canary-remaining14-submission.json'
    with destination.open('x') as stream:json.dump(record,stream,indent=2)
    keep=['HOME','PATH','LANG','LC_ALL','TERM','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS']
    environment={k:os.environ[k] for k in keep if k in os.environ}
    environment.update(DEEPSEEK_API_KEY=secret,PYTHONUNBUFFERED='1',
        SSH_AUTH_SOCK='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock')
    command='umask 077; exec '+shlex.join([HARBOR,'run','--config',str(file)])+' > '+shlex.quote(str(ROOT/'logs/canary-remaining14.log'))+' 2>&1'
    result=subprocess.run(['tmux','-L',SOCKET,'new-session','-d','-s','canary',command],
        env=environment,capture_output=True,text=True,timeout=20)
    record.update(status='SUBMITTED_NATIVE_JOB_NOT_YET_VERIFIED' if result.returncode==0 else 'SUBMISSION_REJECTED',
        submission_returncode=result.returncode)
    destination.write_text(json.dumps(record,indent=2));print(json.dumps(record))
    if result.returncode:raise RuntimeError('Submission rejected; preserve and inspect exact identity')


if __name__=='__main__':main()
