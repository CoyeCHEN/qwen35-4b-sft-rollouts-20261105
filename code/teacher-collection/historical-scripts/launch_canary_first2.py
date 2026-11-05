"""Launch one native Harbor canary job in a private remote tmux server.

The existing credential crosses encrypted SSH stdin and then environment only.
No key enters argv, a manifest, output or a persisted launcher configuration.
Lost acknowledgement requires observing this exact native job, never replay.
"""
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

ROOT = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
HARBOR = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/harbor')
SOCKET = 'cf-tmax-teacher-20261029'


def main():
    incoming = json.load(sys.stdin)
    secret = incoming['DEEPSEEK_API_KEY']
    if not isinstance(secret, str) or not secret:
        raise ValueError('Authorized teacher credential is absent')
    file = ROOT / 'configs/canary-first2.json'
    sha = hashlib.sha256(file.read_bytes()).hexdigest()
    if sha != incoming['config_sha256']:
        raise ValueError('Reviewed canary config identity changed')
    raw = json.loads(file.read_text()); config = JobConfig.model_validate(raw)
    if not(config.job_name == 'cf-tmax-canary-first2-20261030' and config.n_attempts == 1
            and config.retry.max_retries == 0 and config.n_concurrent_trials == 8
            and not config.install_only and len(config.tasks) == 2 and len(config.agents) == 1):
        raise ValueError('Canary scope or native retry/concurrency changed')
    agent = config.agents[0]
    OpenHarnessAgent.preflight(agent.kwargs)
    teacher = ROOT / 'configs/teacher-native-11tools.json'
    if agent.kwargs['config'] != json.loads(teacher.read_text()):
        raise ValueError('The two pools no longer share the exact teacher configuration')
    contract = json.loads((ROOT / 'manifests/TEACHER_CONTRACT_CANDIDATE.json').read_text())
    if hashlib.sha256(teacher.read_bytes()).hexdigest() != contract['config_sha256']:
        raise ValueError('Frozen teacher contract differs from actual configuration')
    if agent.model_name != 'deepseek/deepseek-flash' or agent.override_timeout_sec != 10800:
        raise ValueError('Teacher model or research timeout changed')
    selected = []
    for pool, manifest, task_id in [
        ('calibforge', 'CALIBFORGE_500_TASKS.jsonl', 'system-administration_20260430_081156_006'),
        ('tmax', 'TMAX_PREPARED_TASKS.jsonl', 'task_000142_395c1c7f'),
    ]:
        row = next(x for x in map(json.loads, (ROOT / 'manifests' / manifest).open()) if x['task_id'] == task_id)
        path = Path(raw['tasks'][len(selected)]['path'])
        instruction_sha = hashlib.sha256((path / 'instruction.md').read_bytes()).hexdigest()
        if instruction_sha != row['instruction_sha256']:
            raise ValueError('Canary instruction differs from original release')
        spec = tomllib.loads((path / 'task.toml').read_text())
        if (spec.get('agent', {}).get('timeout_sec') or 0) > 10800:
            raise ValueError('Research timeout would shorten this original task')
        image = spec['environment']['docker_image']
        inspected = subprocess.run(['docker','image','inspect',image],check=True,capture_output=True,text=True,timeout=15)
        image_id = json.loads(inspected.stdout)[0]['Id']
        selected.append(dict(pool=pool,task_id=task_id,source_manifest=manifest,task_path=str(path),
            image_id=image_id,instruction_sha256=instruction_sha,attempt=1,split=row['split'],family_id=row['family_id']))
    if (Path(config.jobs_dir) / config.job_name).exists():
        raise FileExistsError('Native job exists: observe the same job instead of replaying')
    live = subprocess.run(['tmux','-L',SOCKET,'has-session','-t','canary'],capture_output=True,timeout=10)
    if live.returncode == 0:
        raise RuntimeError('The sole canary controller is already live')
    for other in (ROOT / 'jobs').glob('*/config.json'):
        settings = json.loads(other.read_text())
        if not settings.get('install_only') and any(a.get('name') == 'open-harness' for a in settings.get('agents', [])):
            raise RuntimeError('Existing teacher ownership requires inspection before another job')
    launched_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record = dict(status='DISPATCH_REQUESTED_ACKNOWLEDGEMENT_PENDING',launched_at=launched_at,
        job_name=config.job_name,config_sha256=sha,tmux_socket=SOCKET,tmux_session='canary',
        canary_tasks=selected,canary_cohort_total=16,canary_cohort_attempts_requested=2,
        total_teacher_attempts_cap=2000,teacher_tasks_cap=1000,native_retry=0,native_concurrency=8,
        wheel_sha256=agent.kwargs['wheel_sha256'],teacher_config_sha256=contract['config_sha256'],
        credential_transport='Encrypted SSH stdin -> environment -> private tmux server; no argv value')
    destination = ROOT / 'checks/canary-first2-submission.json'
    with destination.open('x') as stream:json.dump(record,stream,indent=2)
    keep = ['HOME','PATH','LANG','LC_ALL','TERM','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS']
    environment = {k:os.environ[k] for k in keep if k in os.environ}
    environment.update(DEEPSEEK_API_KEY=secret,PYTHONUNBUFFERED='1',
        SSH_AUTH_SOCK='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock')
    command = 'umask 077; exec ' + shlex.join([str(HARBOR),'run','--config',str(file)])
    command += ' > ' + shlex.quote(str(ROOT/'logs/canary-first2.log')) + ' 2>&1'
    result = subprocess.run(['tmux','-L',SOCKET,'new-session','-d','-s','canary',command],
        env=environment,capture_output=True,text=True,timeout=20)
    record.update(status='SUBMITTED_NOT_YET_VERIFIED' if result.returncode == 0 else 'SUBMISSION_REJECTED',
        submission_returncode=result.returncode)
    destination.write_text(json.dumps(record,indent=2))
    print(json.dumps(record))
    if result.returncode:raise RuntimeError('Canary submission rejected; preserve and inspect this identity')


if __name__ == '__main__':
    main()
