"""Preserve one exited original container, restore only keepalive, run official Verifier once."""
import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import uuid
from pathlib import Path, PurePosixPath

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
E = R / 'formal-native-eval-r1'
C = Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
sys.path[:0] = [str(R), str(E / 'scripts')]
from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.task import Task
from harbor.models.trial.config import TrialConfig
from harbor.models.trial.paths import TrialPaths
from harbor.verifier.verifier import Verifier
from environment_evidence_audit_r3 import read, write


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity(path):
    return {'path': str(path), 'bytes': Path(path).stat().st_size, 'sha256': sha(path)}


def startup_sensitive(diff):
    found = []
    for line in diff.splitlines():
        path = line[2:]
        if (path in ['/bin', '/sbin', '/lib', '/lib64', '/etc/ld.so.preload', '/etc/ld.so.cache']
                or path.startswith(('/lib/', '/lib64/', '/usr/lib/', '/usr/lib64/'))
                or path.rsplit('/', 1)[-1] in ['sh', 'dash', 'bash', 'sleep']):
            found.append(line)
    return found


def canonical_diff(diff):
    lines = diff.splitlines()
    if not lines or any(line[:2] not in ['A ', 'C ', 'D '] or not line[2:].startswith('/') for line in lines):
        raise RuntimeError('Unexpected Docker diff syntax; do not normalize ambiguous records')
    # Preserve every complete status/path record and multiplicity; only record order is irrelevant.
    return '\n'.join(sorted(lines)) + '\n'


async def main(admission_path):
    os.umask(0o077)
    admission = read(admission_path)
    if admission['unique_controller_owner'] != read(C / 'NATIVE_ADVANCE_OWNER.json') or admission['source_sha256'] != sha(__file__):
        raise RuntimeError('Only the current sole controller may admit the frozen verifier worker')
    plan_path = Path(admission['plan_path'])
    if sha(plan_path) != admission['plan_sha256']:
        raise RuntimeError('Verifier-only plan changed')
    plan = read(plan_path)
    if plan['original_trial_uuid'] != 'd4334220-f91b-410e-9ac2-ef5c002d3014' or plan['identity'] != '3470ff78efd74346af653c72f2385865':
        raise RuntimeError('This worker accepts only the explicitly authorized original Trial')
    if socket.gethostname() != plan['execution_node']:
        raise RuntimeError('Preservation archives must use the declared node18 SSD')
    previous = plan['previous_recovery_failure']
    if sha(previous['proof_path']) != previous['proof_sha256']:
        raise RuntimeError('R1 no-start/no-Verifier failure proof changed')
    failed = read(previous['proof_path'])
    if any(failed[k] != 0 for k in ['new_agent_runs', 'new_model_attempts', 'official_verifier_invocations', 'original_container_start_invocations']):
        raise RuntimeError('Previous recovery has ambiguous execution')
    for item in failed['files'] + [failed['source'], failed['log']]:
        if sha(item['path']) != item['sha256']:
            raise RuntimeError('Preserved R1 history changed: ' + item['path'])
    previous_out = Path(failed['r1_output_directory'])
    if any((previous_out / name).exists() for name in ['preservation', 'START_EXISTING_KEEPALIVE_INTENT_R1.json', 'NO_AGENT_RESUMED_R1.json', 'OFFICIAL_VERIFIER_DISPATCHED_R1.json']):
        raise RuntimeError('R1 archive/start/Verifier state no longer matches the frozen failure proof')
    out = Path(admission['output_directory'])
    if out != R / 'original-cython-verifier-only-r2' or out.resolve() != out:
        raise RuntimeError('Use the independent declared node18 SSD evidence directory')
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (out / 'RECOVERY_STARTED_R2.json').exists():
        raise RuntimeError('One admitted verifier recovery only; no implicit re-execution')
    os.environ['PATH'] = plan['private_client_bin'] + ':' + os.environ['PATH']
    os.environ['TMPDIR'] = str(R / 'tmp')
    record_id = str(uuid.uuid4())
    status = {'at': time.time(), 'recovery_record_id': record_id,
              'original_trial_uuid': plan['original_trial_uuid'], 'original_identity': plan['identity'],
              'new_agent_runs': 0, 'new_model_attempts': 0, 'original_result_unchanged': True,
              'independent_verifier_reward_auxiliary_only': True, 'terminal': False}
    write(out / 'RECOVERY_STARTED_R2.json', status)

    def progress(stage, **facts):
        status.update(at=time.time(), stage=stage, **facts)
        write(out / 'RECOVERY_STATUS_R2.json', status)

    # Immutable source files and native implementation identity are checked before any start.
    for item in plan['source_files'] + plan['native_sources']:
        if sha(item['path']) != item['sha256']:
            raise RuntimeError('Frozen source changed: ' + item['path'])
    cfg = TrialConfig.model_validate_json(Path(plan['source_config_path']).read_text())
    raw = read(Path(plan['source_result_path']))
    if raw['id'] != plan['original_trial_uuid'] or raw.get('verifier_result') is not None:
        raise RuntimeError('Original identity changed or original Verifier is already scored')
    task = Task(cfg.task.path)
    for f in plan['task_files']:
        path = cfg.task.path / f['path']
        if sha(path) != f['sha256'] or path.stat().st_mode & 0o7777 != f['mode']:
            raise RuntimeError('Official Task/tests changed: ' + str(path))
    if task.config.environment.model_dump(mode='json') != plan['task_environment'] or task.config.verifier.model_dump(mode='json') != plan['task_verifier']:
        raise RuntimeError('Original Task resource or Verifier configuration changed')
    if task.config.environment.cpus != 1 or task.config.environment.memory_mb != 2048:
        raise RuntimeError('Unexpected original resources')
    paths = TrialPaths(out / 'collected')
    paths.mkdir()
    task_snapshot = out / 'official-task-source'
    shutil.copytree(cfg.task.path, task_snapshot, symlinks=True)
    for item in plan['task_files']:
        if sha(task_snapshot / item['path']) != item['sha256']:
            raise RuntimeError('Trusted official Task snapshot hash mismatch')
    for item in plan['source_files']:
        target = out / 'source-metadata' / Path(item['path']).name
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(item['path'], target)
    compose = Path(plan['source_compose_path'])
    doc = read(compose)
    first = plan['source_provider_first']
    # Hydrate a fresh provider handle from real persisted identity; never construct a Trial UUID.
    env = EnvironmentFactory.create_environment_from_config(
        cfg.environment, environment_dir=task.paths.environment_dir, environment_name=task.short_name,
        session_id='verifier-only-record-' + record_id, trial_paths=paths, task_env_config=task.config.environment)
    env.identity = plan['identity']
    env.project = first['project']
    env.workspace = PurePosixPath(first['workspace'])
    env.root = env.workspace.parent
    env._remote_compose = compose
    env._prepared = True
    env._workspace_created = True
    env._agent_runtime_dir = PurePosixPath('/harbor/agent-runtime')
    env._agent_runtime_volume_key = 'agent-runtime'
    env._verifier_test_volume_key = 'verifier-tests'
    env._read_only_services = {k for k, v in doc['services'].items() if v.get('read_only')}
    env.evidence = out / ('recovery-provider-' + plan['identity'] + '.jsonl')
    await env._connect()
    await env._shell(env._marker_guard() + 'true')
    info = json.loads((await env._run(env._docker('info', '--format', '{{json .}}'))).stdout)
    if info['ID'] != plan['engine_id']:
        raise RuntimeError('Wrong original Docker Engine')
    cid = plan['container_id']

    async def inspected():
        return json.loads((await env._run(env._docker('inspect', cid))).stdout)[0]

    async def original_resources_present():
        found = await env._resources()
        expected_volumes = {m['Name'] for m in plan['mount_identity'] if m['Type'] == 'volume'}
        containers = found['container']  # Native Docker ps -q can return a validated short ID.
        if len(containers) != 1 or not cid.startswith(containers[0]) or set(found['volume']) != expected_volumes or len(found['network']) != 1:
            raise RuntimeError('Original container, network or named volumes are not completely preserved')
        return found

    def validate_container(actual, exited):
        if actual['Id'] != cid or actual['Image'] != plan['image_id']:
            raise RuntimeError('Original container or image changed')
        if actual['Config']['Labels'].get('io.harbor.remote-docker.identity') != plan['identity']:
            raise RuntimeError('Original owner UUID changed')
        if actual['Config']['Entrypoint'] is not None or actual['Config']['Cmd'] != ['sh', '-c', 'sleep infinity'] or actual['Config'].get('Healthcheck') is not None:
            raise RuntimeError('Only the inspected original keepalive may start')
        if actual['HostConfig']['NanoCpus'] != 1000000000 or actual['HostConfig']['Memory'] != 2147483648:
            raise RuntimeError('Original CPU/RAM changed')
        mounts = [{k: m.get(k) for k in ['Type', 'Name', 'Source', 'Destination', 'RW']} for m in actual['Mounts']]
        if mounts != plan['mount_identity']:
            raise RuntimeError('Original volumes or bind assets changed')
        if exited and (actual['State']['Status'] != 'exited' or actual['State']['Pid'] != 0 or actual['State']['OOMKilled']):
            raise RuntimeError('Original environment is not the retained exited sandbox')

    original = await inspected()
    validate_container(original, True)
    write(out / 'ORIGINAL_RESOURCE_IDENTITIES_R2.json', await original_resources_present())
    diff = (await env._run(env._docker('diff', cid))).stdout
    diff_evidence = {'raw_sha256': hashlib.sha256(diff.encode()).hexdigest(),
                     'canonical_sha256': hashlib.sha256(canonical_diff(diff).encode()).hexdigest(),
                     'line_count': len(diff.splitlines()), 'startup_sensitive_changes': startup_sensitive(diff),
                     'only_record_order_normalized': True}
    write(out / 'DIFF_CANONICAL_COMPARISON_R2.json', diff_evidence)
    if (diff_evidence['canonical_sha256'] != plan['original_diff_canonical_sha256']
            or diff_evidence['line_count'] != plan['original_diff_line_count']
            or diff_evidence['startup_sensitive_changes']):
        raise RuntimeError('Original startup filesystem status/path records changed')
    write(out / 'ORIGINAL_CONTAINER_BEFORE_START_R2.json', original)
    progress('PRESERVING_ORIGINAL_EXITED_FILESYSTEM_AND_MOUNTS')
    if os.statvfs(out).f_bavail * os.statvfs(out).f_frsize < 64 * 1024**3:
        raise RuntimeError('Node18 SSD has insufficient preservation headroom')

    async def archive(name, docker_args):
        archive_dir = out / 'preservation'
        archive_dir.mkdir(exist_ok=True)
        partial = archive_dir / (name + '.partial')
        destination = archive_dir / name
        command = env._marker_guard() + shlex.join(['docker', '--host', 'unix://' + env.remote_socket_path, *docker_args])
        with partial.open('xb') as stream:
            process = await asyncio.create_subprocess_exec(*env._ssh, command, stdout=stream, stderr=asyncio.subprocess.PIPE)
            try:
                _, stderr = await asyncio.wait_for(process.communicate(), timeout=env.transfer_timeout)
            except TimeoutError:
                if process.returncode is None:
                    process.kill()
                await process.wait()
                raise RuntimeError('Preservation SSH stream timed out; no container start permitted') from None
            stream.flush()
            os.fsync(stream.fileno())
        if process.returncode:
            raise RuntimeError('Preservation failed: ' + stderr.decode(errors='replace')[-2000:])
        size = partial.stat().st_size
        with partial.open('rb') as stream:
            if size < 1024 or size % 512:
                raise RuntimeError('Invalid/truncated native tar preservation')
            stream.seek(-1024, os.SEEK_END)
            if stream.read() != b'\0' * 1024:
                raise RuntimeError('Missing tar end markers')
        members = 0
        with tarfile.open(partial, 'r:') as tar:
            for member in tar:
                if member.isfile() and member.offset_data + member.size > size - 1024:
                    raise RuntimeError('Truncated preserved file body')
                members += 1
        partial.rename(destination)
        return dict(identity(destination), members=members, untrusted_tar_extracted=False, remote_archive_file_created=False)

    archives = [await archive('original-rootfs.tar', ['export', cid])]
    for index, mount in enumerate(plan['mount_identity']):
        archives.append(await archive('original-mount-' + str(index) + '.tar', ['cp', cid + ':' + mount['Destination'], '-']))
    preserved = {'at': time.time(), 'original_container_id': cid, 'original_identity': plan['identity'],
                 'source_result_sha256': sha(plan['source_result_path']), 'archives': archives,
                 'all_archives_complete_before_any_start': True, 'new_agent_runs': 0}
    write(out / 'PRESERVATION_COMPLETE_R2.json', preserved)
    validate_container(await inspected(), True)
    await original_resources_present()
    if sha(plan['source_result_path']) != raw_sha(plan):
        raise RuntimeError('Original Result changed during preservation')
    write(out / 'START_EXISTING_KEEPALIVE_INTENT_R2.json', {'at': time.time(), 'container_id': cid,
          'cmd': ['sh', '-c', 'sleep infinity'], 'preservation_sha256': sha(out / 'PRESERVATION_COMPLETE_R2.json')})
    await env._run(env._docker('start', cid))
    running = await inspected()
    validate_container(running, False)
    if not running['State']['Running']:
        raise RuntimeError('Original keepalive failed to start')
    top = (await env._run(env._docker('top', cid, '-eo', 'pid,ppid,args'))).stdout
    processes = [line.split(None, 2)[2] for line in top.splitlines()[1:] if line.strip()]
    if not processes or any(p not in ['sh -c sleep infinity', 'sleep infinity'] for p in processes):
        raise RuntimeError('Unexpected process after keepalive restoration; do not invoke Verifier')
    write(out / 'NO_AGENT_RESUMED_R2.json', {'at': time.time(), 'container_id': cid, 'docker_top': top,
          'image_id': running['Image'], 'new_agent_runs': 0, 'new_model_attempts': 0})
    progress('ORIGINAL_KEEPALIVE_RESTORED_COLLECTING_ORIGINAL_RECORDER')
    await env.download_dir(PurePosixPath('/logs/agent'), paths.agent_dir)
    original_logs = [identity(p) for p in paths.agent_dir.rglob('*') if p.is_file()]
    write(out / 'ORIGINAL_AGENT_LOG_FILES_R2.json', {'at': time.time(), 'files': original_logs})
    marker = out / 'OFFICIAL_VERIFIER_DISPATCHED_R2.json'
    if marker.exists():
        raise RuntimeError('Verifier dispatch already recorded; do not repeat')
    write(marker, {'at': time.time(), 'original_trial_uuid': plan['original_trial_uuid'],
          'official_tests': [f for f in plan['task_files'] if f['path'].startswith('tests/')],
          'timeout_sec': plan['effective_verifier_timeout_sec'], 'source_result_sha256': raw_sha(plan)})
    verifier = Verifier(task=task, trial_paths=paths, environment=env, override_env=cfg.verifier.env)
    progress('OFFICIAL_VERIFIER_RUNNING_AUXILIARY_ONLY')
    try:
        with env.with_default_user(task.config.verifier.user):
            result = await asyncio.wait_for(verifier.verify(), timeout=plan['effective_verifier_timeout_sec'])
        status['independent_official_verifier'] = result.model_dump(mode='json')
    except Exception as exc:
        status['verifier_error'] = repr(exc)
    files = [identity(p) for p in paths.trial_dir.rglob('*') if p.is_file()]
    write(out / 'COLLECTED_FILES_R2.json', {'at': time.time(), 'files': files})
    if sha(plan['source_result_path']) != raw_sha(plan):
        raise RuntimeError('Original Result was modified; reject recovery qualification')
    # Keep the original FS/volumes; stop only the restored keepalive via native lifecycle.
    await env.stop(delete=False)
    final = await inspected()
    progress('TERMINAL_AUXILIARY_VERIFIER_RECORD_ORIGINAL_FIRST_PASS_UNCHANGED', terminal=True,
             container_retained=True, original_volumes_and_workspace_retained=True,
             final_container_state=final['State'], first_pass_reader_or_selection_criterion_changed=False)


def raw_sha(plan):
    return next(item['sha256'] for item in plan['source_files'] if item['path'] == plan['source_result_path'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('admission', type=Path)
    args = parser.parse_args()
    lock_path = C / 'cython-original-verifier-only-recovery.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(main(args.admission))
