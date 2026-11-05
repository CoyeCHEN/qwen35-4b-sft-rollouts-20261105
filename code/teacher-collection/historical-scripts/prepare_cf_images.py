"""Precache the frozen CF500 images and perform cheap isolated setup checks.

One preparation worker, no model/teacher trials, no benchmark edits or global
Docker cleanup. Per-task failures remain local. This is not verifier admission.
"""
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import tomllib
import warnings

from harbor.models.task.config import TaskConfig

ROOT = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
OUT = ROOT / 'checks/cf-environments'
DISK_RESERVE = 100 * 1024**3


def command(args, timeout=30):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def image_info(image):
    result = command(['docker', 'image', 'inspect', image])
    if result.returncode:
        if 'No such image' in result.stderr:
            return None
        raise RuntimeError('Docker image inventory failed')
    return json.loads(result.stdout)[0]


def main():
    OUT.mkdir(exist_ok=True)
    rows = list(map(json.loads, (ROOT / 'manifests/CALIBFORGE_500_TASKS.jsonl').open()))
    canary = json.loads((ROOT / 'manifests/SAMPLING_MANIFEST.json').read_text())['pools']['calibforge']['canary_task_ids']
    rows.sort(key=lambda r: (canary.index(r['task_id']) if r['task_id'] in canary else 8, r['task_id']))
    daemon = command(['docker', 'info', '--format', '{{json .}}'])
    daemon.check_returncode(); daemon = json.loads(daemon.stdout)
    counts = Counter()
    report = dict(planned_tasks=500, model_attempts=0, daemon_id=daemon['ID'])
    for row in rows:
        path = OUT / (row['task_id'] + '.json')
        if path.exists():
            counts[json.loads(path.read_text())['status']] += 1
            continue
        started = time.monotonic()
        record = dict(task_id=row['task_id'], checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            task_toml_sha256=row['task_toml_sha256'], image=row['docker_image'], daemon_id=daemon['ID'],
            status='PREPARING', model_attempts=0, official_verifier_executed=False)
        directory = Path(row['source_path'])
        before = (directory / 'task.toml').read_bytes()
        if hashlib.sha256(before).hexdigest() != row['task_toml_sha256']:
            raise ValueError('Task identity changed; freeze new preparation')
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            config = TaskConfig.model_validate(tomllib.loads(before.decode()))
        resources = config.environment
        record['original_environment'] = resources.model_dump(mode='json')
        record['original_agent_timeout_sec'] = config.agent.timeout_sec
        record['campaign_agent_timeout_sec'] = max(config.agent.timeout_sec or 0, 10800)
        record['original_verifier_timeout_sec'] = config.verifier.timeout_sec
        if (resources.gpus or 0) > 0:
            record['status'] = 'DECLARED_GPU_REQUIRES_EXPLICIT_RESOURCE_ACCEPTANCE'
        elif shutil.disk_usage(ROOT).free < DISK_RESERVE:
            # A shared-storage safety condition is global; no destructive cache cleanup.
            report = dict(status='PREPARATION_WAITING_FOR_DISK_HEADROOM', required_free_bytes=DISK_RESERVE,
                actual_free_bytes=shutil.disk_usage(ROOT).free, next_task_id=row['task_id'], counts=dict(counts))
            (ROOT / 'checks/cf-image-preparation.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report), flush=True)
            return
        else:
            container_name = 'cf500-preflight-' + hashlib.sha256(row['task_id'].encode()).hexdigest()[:16]
            try:
                info = image_info(row['docker_image'])
                record['initially_cached'] = info is not None
                if info is None:
                    log = OUT / (row['task_id'] + '.pull.log')
                    with log.open('x') as stream:
                        pulled = subprocess.run(['docker', 'pull', row['docker_image']], stdout=stream,
                            stderr=subprocess.STDOUT, timeout=900)
                    record['pull_returncode'] = pulled.returncode
                    if pulled.returncode:
                        raise RuntimeError('Registry pull failed; original log preserved')
                    info = image_info(row['docker_image'])
                record.update(image_id=info['Id'], repo_digests=info.get('RepoDigests', []),
                    image_size_bytes=info['Size'], configured_workdir=info['Config'].get('WorkingDir'),
                    image_user=info['Config'].get('User'), image_entrypoint=info['Config'].get('Entrypoint'))
                args = ['docker', 'run', '--rm', '--name', container_name,
                    '--label', 'rsi.campaign=' + ROOT.name, '--cpus', str(resources.cpus or 1),
                    '--memory', str((resources.memory_mb or 2048) * 1024**2),
                    '--entrypoint', '/bin/sh', info['Id'], '-c',
                    'set -eu; pwd -P; id; test -w .; command -v bash; command -v python3; '
                    'test ! -e /tests; test ! -e /solution; '
                    'probe=.cf500-preflight-$$; printf probe > "$probe"; rm -- "$probe"; '
                    'if test -e /sys/fs/cgroup/memory.max; then cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/cpu.max; fi; '
                    'getent hosts api.deepseek.com; '
                    'python3 -c "import urllib.request; r=urllib.request.urlopen(\'https://pypi.org/simple/pytest/\',timeout=20); print(\'PYPI_HTTP\',r.status)"']
                checked = command(args, timeout=90)
                record.update(probe_returncode=checked.returncode, probe_stdout=checked.stdout[:16000],
                    probe_stderr=checked.stderr[:4000], status='BASIC_ENVIRONMENT_CHECK_PASSED' if checked.returncode == 0
                    else 'BASIC_ENVIRONMENT_CHECK_FAILED')
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                record.update(status='ENVIRONMENT_PREPARATION_FAILED', error_type=type(error).__name__,
                    error=str(error)[:600])
            finally:
                # Only this exact preparation identity may be removed after a timed-out probe.
                cleanup = command(['docker', 'rm', '-f', container_name])
                record['container_cleanup_confirmed'] = cleanup.returncode == 0 or 'No such container' in cleanup.stderr
        if (directory / 'task.toml').read_bytes() != before:
            raise ValueError('Original task changed during read-only preparation')
        record['seconds'] = time.monotonic() - started
        record['disk_free_bytes'] = shutil.disk_usage(ROOT).free
        path.write_text(json.dumps(record, indent=2))
        counts[record['status']] += 1
        report = dict(status='PREPARING', planned_tasks=500, observed_tasks=sum(counts.values()),
            counts=dict(counts), full_verifier_admission=False, model_attempts=0, daemon_id=daemon['ID'])
        (ROOT / 'checks/cf-image-preparation.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(dict(task_id=row['task_id'], status=record['status'], seconds=record['seconds'])), flush=True)
    report.update(status='IMAGE_AND_BASIC_CHECKS_FINISHED_VERIFIER_CHECKS_PENDING',
        observed_tasks=sum(counts.values()), counts=dict(counts), full_verifier_admission=False)
    (ROOT / 'checks/cf-image-preparation.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
