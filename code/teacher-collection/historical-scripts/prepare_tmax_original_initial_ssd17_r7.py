"""Run original initial tests as verified native SSD archives become available.

One Task at a time, alongside the one CF worker, with a separate disk guard.
Trusted initial tests are mounted only in preparation containers. No teacher.
"""
from pathlib import Path
from collections import Counter
import datetime
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import time
from prepare_cf_original_basic_ssd17_r6 import run, inspect_image, ENGINE, R

S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    lock = (R / 'checks/tmax-initial-ssd17-r7.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    plan = R / 'manifests/TMAX_REMAINING_INITIAL_SSD17_R7.json'
    rows = json.loads(plan.read_text())['tasks']
    output = R / 'checks/tmax-environments-ssd17-r7'; output.mkdir(exist_ok=True)
    statefile = R / 'checks/tmax-initial-ssd17-r7.json'
    pending = {row['task_id']: row for row in rows}; results = {}

    def state(status):
        value = dict(status=status, pid=os.getpid(), checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            planned_tasks=len(rows), observed_tasks=len(results), remaining_tasks=len(pending), counts=dict(Counter(results.values())),
            plan_sha256=sha(plan), model_calls=0, teacher_backend_changes=0, native_cli_and_verifier_pending=True,
            docker_root_free_bytes=shutil.disk_usage('/').free)
        temp = statefile.with_suffix('.tmp'); temp.write_text(json.dumps(value, indent=2)); temp.replace(statefile)

    engine = run(['docker', 'info', '--format', '{{.ID}}']); engine.check_returncode()
    if engine.stdout.strip() != ENGINE:
        raise ValueError('Unaccepted native Docker engine')
    while pending:
        for ident in list(pending):
            p = output / (ident + '.json')
            if p.exists():
                results[ident] = json.loads(p.read_text())['status']; del pending[ident]
        for row in list(pending.values()):
            ident = row['task_id']; builtfile = S / 'buildkit-rootless-r2/archives' / ident / 'client-proxy-r3/build.json'
            if not builtfile.exists():
                continue
            built = json.loads(builtfile.read_text()); source = built['source_context']
            item = dict(task_id=ident, pool='tmax', backend_engine=ENGINE,
                checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), source_revision=row['source_revision'],
                original_resources=row['original_resources'], model_calls=0, official_final_verifier_executed=False,
                native_cli_install_and_verifier='Pending; original initial tests do not imply ENV_READY')
            name = 'rsi-tmax-initial17-r7-' + hashlib.sha256(ident.encode()).hexdigest()[:16]
            loaded = False; image = None; start = time.monotonic()
            try:
                if source['task_id'] != ident or source['source_revision'] != row['source_revision'] or source['source_manifest_sha256'] != row['source_manifest_sha256']:
                    raise ValueError('Frozen native context source differs')
                if built['status'] != 'ORIGINAL_NATIVE_OCI_ARCHIVE_BUILT_INITIAL_AND_VERIFIER_TESTS_PENDING' or not built['all_manifest_config_layer_hashes_verified']:
                    raise ValueError('Original native build failed; source build log retained')
                archive = Path(built['archive']).resolve()
                if not archive.is_relative_to(S / 'buildkit-rootless-r2/archives' / ident):
                    raise ValueError('Archive escaped owned task cache')
                if shutil.disk_usage('/').free < 50 * 1024**3 + 2 * built['archive_bytes']:
                    state('WAITING_FOR_NATIVE17_DOCKER_ROOT_HEADROOM'); break
                if sha(archive) != built['archive_sha256']:
                    raise ValueError('Native archive SHA mismatch')
                initial = S / 'trusted-tmax-initial-ssd17-r7' / ident / 'test_initial_state.py'
                if sha(initial) != row['initial_test_sha256']:
                    raise ValueError('Original trusted initial test changed')
                image = built['native_manifest_digest']; initial_image = inspect_image(image)
                if initial_image is None:
                    with (output / (ident + '.load.log')).open('x') as stream:
                        reply = subprocess.run(['docker', 'image', 'load', '--input', str(archive)], stdout=stream, stderr=subprocess.STDOUT, timeout=900)
                    reply.check_returncode(); loaded = True
                info = inspect_image(image)
                if info is None or info['Id'] != image:
                    raise ValueError('Native runtime image identity differs')
                resource = row['original_resources']
                if resource.get('gpus'):
                    raise ValueError('No GPU acceptance for this worker')
                startup = row['native_startup_override']['services']['main']
                command = startup['command']; command = [*command[:-1], command[-1].replace('$$', '$')]
                created = run(['docker', 'create', '--name', name, '--runtime', 'runc', '--label', 'rsi.campaign=' + R.name,
                    '--cpus', str(resource['cpus']), '--memory', str(resource['memory_mb'] * 1024**2),
                    '--workdir', '/home/user', '--env', 'HOME=/home/user',
                    '--mount', 'type=bind,src=' + str(initial) + ',dst=/trusted-preparation/test_initial_state.py,readonly',
                    '--entrypoint', '/bin/bash', image, *command[1:]])
                created.check_returncode()
                configured = run(['docker', 'inspect', name]); configured.check_returncode()
                actual = json.loads(configured.stdout)[0]['HostConfig']
                if actual['Privileged'] or actual.get('DeviceRequests') or actual['Memory'] != resource['memory_mb'] * 1024**2 or actual['NanoCpus'] != round(resource['cpus'] * 10**9):
                    raise ValueError('Actual resource/device contract differs')
                started = run(['docker', 'start', name], timeout=180); started.check_returncode()
                if 'healthcheck' in startup:
                    ready = run(['docker', 'exec', name, 'bash', '-c',
                        'for ((i=0; i<120; i++)); do read -r task_process < /proc/1/comm; '
                        'if test "$task_process" = sleep; then exit 0; fi; sleep 1; done; exit 1'], timeout=150)
                    ready.check_returncode()
                probe = ('set -eu; pwd -P; id; test "$HOME" = /home/user; test "$(pwd -P)" = /home/user; '
                    'test -w .; test ! -e /tests; python3 -m pytest -q /trusted-preparation/test_initial_state.py')
                checked = run(['docker', 'exec', '--workdir', '/home/user', '--env', 'HOME=/home/user', name, 'bash', '-lc', probe], timeout=180)
                item.update(status='IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING' if checked.returncode == 0 else 'ORIGINAL_INITIAL_STATE_TEST_FAILED',
                    image_id=image, archive_sha256=built['archive_sha256'], build_receipt_sha256=sha(builtfile),
                    initial_test_sha256=row['initial_test_sha256'], initial_state_returncode=checked.returncode,
                    initial_state_stdout=checked.stdout[:24000], initial_state_stderr=checked.stderr[:4000],
                    native_startup_override=row['native_startup_override'], actual_nano_cpus=actual['NanoCpus'], actual_memory_bytes=actual['Memory'])
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                item.update(status='ENVIRONMENT_PREPARATION_FAILED', error_type=type(error).__name__, error=str(error)[:600])
            finally:
                try:
                    cleanup = run(['docker', 'rm', '-f', name], timeout=180)
                    item['cleanup_confirmed'] = cleanup.returncode == 0 or 'No such container' in cleanup.stderr
                except (OSError, subprocess.SubprocessError) as error:
                    item.update(cleanup_confirmed=False, cleanup_error=str(error)[:500])
                if loaded and item['cleanup_confirmed']:
                    refs = run(['docker', 'ps', '-a', '--filter', 'ancestor=' + image, '--format', '{{.ID}}']); refs.check_returncode()
                    if not refs.stdout.strip():
                        removed = run(['docker', 'image', 'rm', image], timeout=120)
                        item['newly_loaded_image_release_returncode'] = removed.returncode
            item['seconds'] = time.monotonic() - start
            receipt = output / (ident + '.json'); temporary = receipt.with_suffix('.publish-tmp')
            temporary.write_text(json.dumps(item, indent=2)); temporary.replace(receipt)
            results[ident] = item['status']; del pending[ident]
            print(json.dumps(dict(task_id=ident, status=item['status'], seconds=item['seconds'])), flush=True)
            state('PREPARING_ORIGINAL_TMAX_INITIAL_ON17')
            if not item['cleanup_confirmed']:
                raise RuntimeError('Unconfirmed preparation ownership; inspect before more image loads')
        state('PREPARING_ORIGINAL_TMAX_INITIAL_ON17' if pending else 'FINITE_ORIGINAL_INITIAL_CHECKS_TERMINAL')
        if pending:
            time.sleep(30)


if __name__ == '__main__':
    main()
