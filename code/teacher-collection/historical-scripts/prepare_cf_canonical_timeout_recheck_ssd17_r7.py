"""Original CF recheck after a documented149 Docker tag timeout; no teacher replay.

Cold official archives stay on SSD. Only images newly loaded by this worker may
be released, without force, after reference checks. No teacher/Verifier claims.
"""
from collections import Counter
from pathlib import Path
import argparse
import datetime
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import time
from verify_public_oci import verify, file_sha

R = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/registry')
ENGINE = '9e09f846-3672-4739-b45b-2eb4330320d1'
for key in ['DEEPSEEK_API_KEY', 'GH_TOKEN', 'OPENAI_API_KEY', 'DOCKER_HOST', 'DOCKER_CONTEXT']:
    os.environ.pop(key, None)


def run(args, timeout=30):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def inspect_image(image):
    reply = run(['docker', 'image', 'inspect', image])
    if reply.returncode == 0:
        return json.loads(reply.stdout)[0]
    if 'No such image' in reply.stderr:
        return None
    raise RuntimeError('Native Docker inventory unavailable')


def cache_for(row):
    for name in ['tasks-local-skopeo-r1', 'tasks']:
        path = S / name / row['task_id'] / 'cache.json'
        if path.exists():
            value = json.loads(path.read_text())
            if value['pinned'] != row['source_image']['pinned']:
                raise ValueError('Archive belongs to another frozen image')
            return value
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-id')
    args = parser.parse_args()
    plan = R / 'manifests/CF_CANONICAL_TIMEOUT_RECHECK_SSD17_R7.json'
    rows = json.loads(plan.read_text())['tasks']
    if args.task_id:
        rows = [r for r in rows if r['task_id'] == args.task_id]
        if len(rows) != 1:
            raise ValueError('Expected one original frozen task')
    rows.sort(key=lambda x: (x['source_image'].get('compressed_layer_bytes', 0), x['task_id']))
    lock = (R / 'checks/cf-basic-ssd17-recheck-r7.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    engine = run(['docker', 'info', '--format', '{{.ID}}']); engine.check_returncode()
    if engine.stdout.strip() != ENGINE:
        raise ValueError('Unaccepted native Docker engine')
    output = R / 'checks/cf-environments-ssd17-recheck-r7'; output.mkdir(exist_ok=True)
    state = R / 'checks' / ('cf-basic-ssd17-recheck-r7-' + (args.task_id or 'full') + '.json')
    pending = {row['task_id']: row for row in rows}
    results = {}
    while pending:
        for ident in list(pending):
            receipt = output / (ident + '.json')
            if receipt.exists():
                results[ident] = json.loads(receipt.read_text())['status']; del pending[ident]
        available = [row for row in pending.values() if cache_for(row)]
        for row in available:
            ident = row['task_id']; image = row['source_image']['top_manifest_digest']
            free = shutil.disk_usage('/').free
            reserve = 40 * 1024**3 + 2 * row['source_image'].get('compressed_layer_bytes', 0)
            if free < reserve:
                break
            item = dict(task_id=ident, pool='calibforge', source_revision=row['source_revision'],
                source_task_toml_sha256=row['source_task_toml_sha256'], source_instruction_sha256=row['source_instruction_sha256'],
                backend_engine=ENGINE, original_resources=row['original_resources'],
                checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), model_calls=0,
                official_final_verifier_executed=False, native_cli_install_and_verifier='Pending; basic check is not ENV_READY')
            name = 'rsi-cf-basic17-recheck-r7-' + hashlib.sha256(ident.encode()).hexdigest()[:16]
            start = time.monotonic(); initial = inspect_image(image); loaded = False
            try:
                cached = cache_for(row); archive = Path(cached['archive']).resolve()
                if not archive.is_relative_to(S) or file_sha(archive) != cached['archive_sha256']:
                    raise ValueError('Owned original archive identity differs')
                verified = verify(row['source_image'], archive)
                item['archive_sha256'] = verified['archive_sha256']
                if initial is None:
                    log = output / (ident + '.load.log')
                    with log.open('x') as stream:
                        reply = subprocess.run(['docker', 'image', 'load', '--input', str(archive)], stdout=stream, stderr=subprocess.STDOUT, timeout=900)
                    reply.check_returncode(); loaded = True
                info = inspect_image(image)
                if info is None or info['Id'] != image:
                    raise ValueError('Actual original image digest differs')
                resource = row['original_resources']
                if resource.get('gpus'):
                    raise ValueError('No GPU resource acceptance; task cannot run in this worker')
                create = run(['docker', 'create', '--name', name, '--runtime', 'runc', '--label', 'rsi.campaign=' + R.name,
                    '--cpus', str(resource['cpus']), '--memory', str(resource['memory_mb'] * 1024**2),
                    '--entrypoint', '/bin/bash', image, '-lc',
                    'set -eu; pwd -P; id; test -w .; command -v bash; test ! -e /tests; test ! -e /solution; '
                    'probe=.cf500-preflight-$$; printf probe > "$probe"; rm -- "$probe"; '
                    'if test -e /sys/fs/cgroup/memory.max; then cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/cpu.max; fi; '
                    'getent hosts api.deepseek.com; command -v python3 || true'])
                create.check_returncode()
                config = run(['docker', 'inspect', name]); config.check_returncode()
                actual = json.loads(config.stdout)[0]['HostConfig']
                if actual['Privileged'] or actual.get('DeviceRequests') or actual['Memory'] != resource['memory_mb'] * 1024**2 or actual['NanoCpus'] != round(resource['cpus'] * 10**9):
                    raise ValueError('Actual CPU/RAM/GPU/privilege contract differs')
                probe = run(['docker', 'start', '--attach', name], timeout=120)
                terminal = run(['docker', 'inspect', name]); terminal.check_returncode()
                code = json.loads(terminal.stdout)[0]['State']['ExitCode']
                item.update(status='IMAGE_IDENTITY_AND_BASIC_SETUP_PASSED' if probe.returncode == code == 0 else 'BASIC_SETUP_FAILED',
                    image_id=image, newly_loaded_image=loaded, probe_returncode=code, stdout=probe.stdout[:12000], stderr=probe.stderr[:3000],
                    actual_nano_cpus=actual['NanoCpus'], actual_memory_bytes=actual['Memory'], cold_archive_retained=str(archive))
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                item.update(status='ENVIRONMENT_PREPARATION_FAILED', error_type=type(error).__name__, error=str(error)[:600])
            finally:
                cleanup = run(['docker', 'rm', '-f', name], timeout=180)
                item['cleanup_confirmed'] = cleanup.returncode == 0 or 'No such container' in cleanup.stderr
                if loaded and item['cleanup_confirmed']:
                    refs = run(['docker', 'ps', '-a', '--filter', 'ancestor=' + image, '--format', '{{.ID}}'])
                    refs.check_returncode()
                    if not refs.stdout.strip():
                        removed = run(['docker', 'image', 'rm', image], timeout=120)
                        item['newly_loaded_image_release_returncode'] = removed.returncode
                        item['newly_loaded_image_release_stderr'] = removed.stderr[-1000:]
                    else:
                        item['newly_loaded_image_release'] = 'Retained: another container references it'
            item.update(seconds=time.monotonic() - start, docker_root_free_bytes=shutil.disk_usage('/').free)
            with (output / (ident + '.json')).open('x') as stream:
                stream.write(json.dumps(item, indent=2))
            results[ident] = item['status']; del pending[ident]
            print(json.dumps(dict(task_id=ident, status=item['status'], seconds=item['seconds'])), flush=True)
            if not item['cleanup_confirmed']:
                raise RuntimeError('Unconfirmed worker container ownership; inspect before further loads')
        value = dict(status='PREPARING_ORIGINAL_CF_BASIC_ON17' if pending else 'FINITE_ORIGINAL_BASIC_CHECKS_TERMINAL',
            pid=os.getpid(), checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), planned_tasks=len(rows),
            observed_tasks=len(results), remaining_tasks=len(pending), counts=dict(Counter(results.values())),
            plan_sha256=hashlib.sha256(plan.read_bytes()).hexdigest(), model_calls=0, teacher_backend_changes=0,
            native_cli_and_verifier_pending=True, docker_root_free_bytes=shutil.disk_usage('/').free)
        temp = state.with_suffix('.tmp'); temp.write_text(json.dumps(value, indent=2)); temp.replace(state)
        if pending:
            time.sleep(30)


if __name__ == '__main__':
    main()
