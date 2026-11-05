"""Task-local image/initial-state operations on the configured private Engine.

Runs on17. No149 image inspection, transport, build or Docker operation.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    request = json.load(sys.stdin)
    if sha(Path(__file__)) != request['helper_sha256']:
        raise ValueError('Frozen node image helper changed')
    deployment = request['deployment']
    if deployment.get('public_bootstrap') and sha(deployment['public_bootstrap']['path']) != deployment['public_bootstrap']['sha256']:
        raise ValueError('Pinned public bootstrap binary changed')
    for filename,key in [('resolve_cold_image17_r2.py','cold_resolver_sha256'),('inspect_cold_oci_r1.py','archive_inspector_sha256')]:
        if sha(Path(__file__).parent/filename)!=deployment[key]:
            raise ValueError('Frozen image resolver/inspector source changed')
    public=deployment['approved_public_verifier_dependency_bindings']
    if sha(public['path'])!=public['sha256']:
        raise ValueError('Approved public verifier dependency bindings changed')
    root = Path(deployment['ssd_root'])
    command = ['docker', '--host', 'unix://' + deployment['socket']]
    def docker(*args, timeout=120):
        return subprocess.run(command + list(args), text=True, capture_output=True, timeout=timeout)
    def checked(reply):
        if reply.returncode:
            raise RuntimeError((reply.stderr or reply.stdout)[-2000:])
        return reply.stdout
    engine = json.loads(checked(docker('info', '--format', '{{json .}}')))
    if engine['ID'] != deployment['engine_id'] or engine['DockerRootDir'] != '/var/lib/docker':
        raise ValueError('Configured private Engine identity changed')
    # /var/lib/docker is inside the owned dind parent, bound to the SSD.
    mount = subprocess.run(['docker', 'inspect', deployment['parent_container']],
        check=True, text=True, capture_output=True, timeout=30)
    parent, = json.loads(mount.stdout)
    mounts = {x['Destination']: x['Source'] for x in parent['Mounts']}
    if mounts.get('/var/lib/docker') != deployment['docker_root'] or mounts.get('/var/lib/containerd') != deployment['containerd_root']:
        raise ValueError('Private Engine storage escaped the declared SSD paths')
    row = request.get('row') or {}
    image = row.get('image_id')
    action = request['action']
    if action == 'engine':
        print(json.dumps(dict(engine_id=engine['ID'], free_bytes=shutil.disk_usage(root).free,
            storage_mounts=mounts, node='17')))
        return
    def inspect():
        reply = docker('image', 'inspect', image)
        if reply.returncode == 0:
            value, = json.loads(reply.stdout)
            if value['Id'] != image:
                raise ValueError('Exact Task image identity changed')
            return value
        if 'No such image' in reply.stderr:
            return None
        raise RuntimeError(reply.stderr[-1000:])
    current = inspect()
    if action == 'inspect':
        print(json.dumps(current))
        return
    from resolve_cold_image17_r2 import resolve
    if action == 'ensure':
        if current is not None:
            print(json.dumps(dict(status='EXACT_IMAGE_ALREADY_RESIDENT', image_id=image, engine_id=engine['ID'], node='17')))
            return
        proof = resolve(row['task_id'], image, row['pool'], deployment['approved_public_verifier_dependency_bindings'])
        archive = Path(proof['archive'])
        if not archive.is_relative_to(root) or '..' in archive.parts:
            raise ValueError('Exact archive is outside campaign SSD storage')
        need = deployment['reserve_bytes'] + proof['expanded_layer_tar_bytes'] + proof['archive_bytes']
        if shutil.disk_usage(root).free < need:
            raise RuntimeError('IMAGE_CAPACITY: insufficient SSD image-load headroom')
        if sha(archive) != proof['archive_sha256']:
            raise ValueError('Exact cold archive SHA changed')
        checked(docker('image', 'load', '--input', str(archive), timeout=1800))
        if inspect() is None:
            raise ValueError('Private Engine load did not preserve Task image identity')
        print(json.dumps(dict(status='EXACT_SSD_ARCHIVE_LOADED_ON_SAME_NODE', image_id=image,
            archive=str(archive), archive_sha256=proof['archive_sha256'], engine_id=engine['ID'], node='17', image_bytes_transferred_via149=0)))
        return
    if action == 'release':
        if current is None:
            print(json.dumps(dict(status='IMAGE_ALREADY_ABSENT', image_id=image, node='17')))
            return
        if checked(docker('ps', '-aq', '--filter', 'ancestor=' + image)).strip():
            print(json.dumps(dict(status='CACHE_RETAINED_CONTAINER_REFERENCE', image_id=image, node='17')))
            return
        proof = resolve(row['task_id'], image, row['pool'], deployment['approved_public_verifier_dependency_bindings'])
        if sha(proof['archive']) != proof['archive_sha256']:
            raise ValueError('Release refused: cold archive identity changed')
        # This Engine is campaign-owned. No force removal or global pruning.
        checked(docker('image', 'rm', image, timeout=180))
        print(json.dumps(dict(status='EXACT_IDLE_SSD_IMAGE_RELEASED', image_id=image,
            engine_id=engine['ID'], node='17', force_or_global_prune_actions=0)))
        return
    if action != 'initial' or current is None:
        raise ValueError('Unknown operation or missing materialized Task image')
    resources = request['resources']
    name = 'cftmax-r7-initial-' + row['task_id'].lower().replace('_', '-')[-65:] + '-' + request['probe_id'][:8]
    initial = request.get('initial_test')
    args = ['create', '--name', name, '--label', 'rsi.campaign=' + root.name,
        '--cpus', str(resources['cpus']), '--memory', str(resources['memory_mb'] * 1024**2),
        '--workdir', request['workdir'], '--env', 'HOME=' + request['home']]
    if initial:
        test = Path(initial['path'])
        if not test.is_relative_to(root) or sha(test) != initial['sha256']:
            raise ValueError('Trusted original initial-state test identity differs')
        args += ['--mount', 'type=bind,src=' + str(test) + ',dst=/trusted-preparation/test_initial_state.py,readonly']
    args += ['--entrypoint', '/bin/bash', image, *request['startup'][1:]]
    out = dict(node='17', engine_id=engine['ID'], image_id=image, task_id=row['task_id'], model_calls=0)
    try:
        checked(docker(*args))
        inspected, = json.loads(checked(docker('inspect', name)))
        host = inspected['HostConfig']
        if host['Privileged'] or host.get('DeviceRequests') or host['Memory'] != resources['memory_mb'] * 1024**2 or host['NanoCpus'] != round(resources['cpus'] * 1e9):
            raise ValueError('Original Task resource/privilege contract changed')
        checked(docker('start', name))
        probe="printf '%s\\n' \"$(cat /sys/fs/cgroup/cpu.max)\" \"$(cat /sys/fs/cgroup/memory.max)\"; test ! -e /dev/nvidia0"
        values=checked(docker('exec',name,'/bin/sh','-c',probe)).splitlines()
        cpu=values[0].split(); memory=int(values[1])
        actual=dict(cpu_max=values[0],memory_max=values[1],gpu=False,
            direct_deepseek_tls='Accepted by frozen joint canary; managed runtime and actual request checked separately')
        if cpu[0]=='max' or int(cpu[0])/int(cpu[1])!=resources['cpus'] or memory!=resources['memory_mb']*1024**2:
            raise ValueError('Actual cgroup resources differ from original Task')
        checked(docker('exec', '--workdir', request['workdir'], name, 'bash', '-lc', 'test -w .; test ! -e /tests'))
        if initial:
            reply = docker('exec', '--workdir', request['workdir'], '--env', 'HOME=' + request['home'], name,
                'bash', '-lc', 'python3 -m pytest -q /trusted-preparation/test_initial_state.py', timeout=request['initial_timeout'])
            logs = root / 'preflight-r7' / row['task_id'] / request['probe_id']; logs.mkdir(parents=True, exist_ok=False)
            for kind in ['stdout', 'stderr']:
                path = logs / ('initial-' + kind + '.txt'); path.write_text(getattr(reply, kind))
                out['initial_' + kind] = dict(path=str(path), sha256=sha(path))
            out['initial_state_returncode'] = reply.returncode
            checked(reply)
        out.update(status='ORIGINAL_TASK_INITIAL_RESOURCES_NETWORK_ACCEPTED', actual_resources=actual)
    finally:
        reply = docker('rm', '-f', name)
        out['cleanup_confirmed'] = reply.returncode == 0 or 'No such container' in reply.stderr
    print(json.dumps(out))


if __name__ == '__main__':
    main()
