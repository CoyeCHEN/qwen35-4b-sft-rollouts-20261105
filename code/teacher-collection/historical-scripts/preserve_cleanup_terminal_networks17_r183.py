"""Finite exact-scope recovery: preserve ended Trials, then remove owned resources.

Original Results, Rewards, Task files and attempts remain unchanged. No image
is removed. One stopped helper is used only to read orphaned named volumes.
"""
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import shutil
import subprocess

S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
D = S / 'terminal-network-preservation-r182'
PLAN = json.loads((D / 'PLAN.json').read_text())
CLI = ['docker', '--host', 'unix://' + str(S / 'engine17-r1/socket/docker.sock')]
os.umask(0o077)


def stop_requested(signum, frame):
    raise TimeoutError('Finite preservation received termination; leave original resources intact')


signal.signal(signal.SIGTERM, stop_requested)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def run(args, timeout=120):
    return subprocess.run(CLI + args, capture_output=True, check=True, timeout=timeout)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def freeze(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)


def resources(identity):
    result = {}
    for kind in ['container', 'network', 'volume']:
        args = [kind, 'ls', '-q', '--filter', 'label=io.harbor.remote-docker.identity=' + identity]
        if kind == 'container':
            args.insert(2, '-a')
        result[kind] = run(args).stdout.decode().split()
    return result


def no_teacher(container):
    if not container['State']['Running']:
        return []
    lines = run(['top', container['Id'], '-eo', 'pid,stat,args']).stdout.decode().splitlines()
    summary = []
    for line in lines[1:]:
        fields = line.split(None, 2)
        if len(fields) != 3:
            continue
        argv = shlex.split(fields[2])
        if argv[:1] == ['{open-harness}']:
            argv = argv[1:]
        if any(arg.endswith('/bin/open-harness') for arg in argv) and fields[1][0] != 'Z':
            raise ValueError('A real Teacher CLI still exists; preserve this scope')
        summary.append(dict(pid=int(fields[0]), state=fields[1], program=Path(argv[0]).name if argv else ''))
    return summary


def copy_volume(container_id, source, target):
    target.mkdir()
    run(['cp', container_id + ':' + source + '/.', str(target)], timeout=3600)
    files = [dict(path=str(path.relative_to(target)), bytes=path.stat().st_size, sha256=sha(path))
             for path in sorted(target.rglob('*')) if path.is_file() and not path.is_symlink()]
    links = [dict(path=str(path.relative_to(target)), target=str(path.readlink()))
             for path in sorted(target.rglob('*')) if path.is_symlink()]
    return dict(directory=str(target), files=files, symlinks=links)


assert run(['info', '--format', '{{.ID}}']).stdout.decode().strip() == PLAN['engine_id']
if (D / 'TERMINAL.json').exists():
    raise FileExistsError('Observe the completed finite recovery; never replay')
helper_image = next(image for task in PLAN['tasks'] for image in task['original_container_images'])
helper_image_id = json.loads(run(['image', 'inspect', helper_image]).stdout)[0]['Id']
results = []
for task in sorted(PLAN['tasks'], key=lambda item:bool(item['original_container_ids'])):
    identity = task['identity']
    root = D / identity
    root.mkdir(mode=0o700, exist_ok=False)
    paused = []
    helper = None
    status = dict(task=task, engine_id=PLAN['engine_id'], started_at=now(), new_model_calls=0,
        original_result_or_reward_rewritten=False, original_attempt_budget_unchanged=True)
    try:
        before = resources(identity)
        containers = []
        for cid in before['container']:
            container, = json.loads(run(['inspect', cid]).stdout)
            if container['Id'] not in task['original_container_ids']:
                raise ValueError('Native scope container identity changed')
            if container['Config']['Labels']['io.harbor.remote-docker.identity'] != identity:
                raise ValueError('Container does not belong to the exact native scope')
            commands = no_teacher(container)
            containers.append(container)
            if container['State']['Running'] and not container['State']['Paused']:
                run(['pause', container['Id']])
                paused.append(container['Id'])
            status.setdefault('containers', []).append(dict(id=container['Id'], image=container['Image'],
                original_state=container['State'], process_metadata=commands, mounts=container['Mounts']))
        status['exact_owned_resources'] = before
        freeze(root / 'PRESERVATION_PLAN.json', status)
        for container in containers:
            target = root / ('filesystem-' + container['Id'][:12] + '.tar.gz')
            partial = target.with_suffix('.partial')
            with partial.open('xb') as raw, (root / 'export.stderr').open('ab') as log:
                process = subprocess.Popen(CLI + ['export', container['Id']], stdout=subprocess.PIPE, stderr=log)
                try:
                    with gzip.GzipFile(fileobj=raw, mode='wb', compresslevel=1, mtime=0) as archive:
                        shutil.copyfileobj(process.stdout, archive, 1024 * 1024)
                    if process.wait(timeout=120) != 0:
                        raise ValueError('Root filesystem preservation failed; no cleanup')
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=30)
                    process.stdout.close()
            partial.replace(target)
            status.setdefault('filesystems', []).append(dict(path=str(target), bytes=target.stat().st_size, sha256=sha(target)))
        mounts = {mount['Name']: (container['Id'], mount['Destination']) for container in containers
                  for mount in container['Mounts'] if mount['Type'] == 'volume'}
        if not containers and before['volume']:
            # Stopped helper: no Task code or process ever runs.
            args = ['create', '--network', 'none', '--read-only', '--label', 'rsi.preservation.scope=' + identity,
                    '--name', 'cftmax-preserve-r183-' + identity[:12], '--entrypoint', '/bin/true']
            for ordinal, name in enumerate(before['volume']):
                args += ['--mount', 'type=volume,source=' + name + ',target=/preserve/v' + str(ordinal) + ',readonly']
            helper = run(args + [helper_image_id]).stdout.decode().strip()
            mounts = {name:(helper, '/preserve/v' + str(i)) for i, name in enumerate(before['volume'])}
            status['orphaned_volumes_helper'] = dict(container=helper, image=helper_image_id, started=False)
            status['old_container_already_absent'] = True
        for ordinal, name in enumerate(before['volume']):
            volume, = json.loads(run(['volume', 'inspect', name]).stdout)
            if volume['Labels'].get('io.harbor.remote-docker.identity') != identity:
                raise ValueError('Named volume ownership changed')
            owner, destination = mounts[name]
            copied = copy_volume(owner, destination, root / ('volume-' + str(ordinal)))
            status.setdefault('volumes', []).append(dict(name=name, **copied))
        for container in containers:
            for ordinal, mount in enumerate(container['Mounts']):
                if mount['Type'] != 'bind':
                    continue
                path = Path(mount['Source'])
                item = dict(source=str(path), destination=mount['Destination'], source_retained=True, read_only=not mount['RW'])
                if path.is_file():
                    target = root / ('bind-' + str(ordinal))
                    shutil.copy2(path, target)
                    assert sha(target) == sha(path)
                    item.update(copy=str(target), sha256=sha(target))
                status.setdefault('binds', []).append(item)
        # Rehash every preserved file before removing any original resource.
        for item in status.get('filesystems', []):
            assert sha(Path(item['path'])) == item['sha256']
        for volume in status.get('volumes', []):
            for item in volume['files']:
                assert sha(Path(volume['directory']) / item['path']) == item['sha256']
        freeze(root / 'PRESERVATION_COMPLETE.json', status)
        if helper:
            run(['rm', '--force', helper]);helper = None
        for kind, identifiers in before.items():
            for identifier in identifiers:
                run([kind, 'rm', *(['--force'] if kind == 'container' else []), identifier])
        after = resources(identity)
        assert not any(after.values())
        status.update(status='PRESERVED_AND_OWNED_RESOURCES_CLEANED', finished_at=now(), remaining_owned_resources=after,
            staging_retained=True, image_removals=0, official_task_or_verifier_changes=0)
        freeze(root / 'CLEANUP_COMPLETE.json', status)
    except Exception as error:
        status.update(status='PRESERVATION_OR_CLEANUP_FAILED_OR_DEFERRED', error_type=type(error).__name__, error=str(error)[-800:])
        freeze(root / 'FAILURE.json', status)
    finally:
        if helper:
            run(['rm', '--force', helper])
        for cid in paused:
            reply = subprocess.run(CLI + ['inspect', cid], capture_output=True)
            if reply.returncode == 0 and json.loads(reply.stdout)[0]['State']['Paused']:
                run(['unpause', cid])
    results.append(dict(task_id=task['task_id'], identity=identity, status=status['status'], root=str(root)))
    temporary = D / 'progress.pending'
    temporary.write_text(json.dumps(dict(checked_at=now(), completed_scopes=len(results), planned_scopes=len(PLAN['tasks']), results=results), indent=2))
    temporary.replace(D / 'progress.json')
freeze(D / 'TERMINAL.json', dict(results=results, completed_at=now(), new_model_calls=0,
    source_sha256=sha(Path(__file__)), plan_sha256=sha(D / 'PLAN.json')))
print(json.dumps(results))
