"""Campaign deployment is selected before any image or native Trial operation."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tomllib
from uuid import uuid4

import run_collection_stream_r4 as c
from collection_readiness_r4 import prepared, blocking_review, verify_nop, basic_receipt
from native_image_archive149_r1 import ImageCapacityError

R = c.R
CONFIG = R / 'configs/campaign-deployment17-r7b.json'
DEPLOYMENT = json.loads(CONFIG.read_text())
CONFIG_SHA = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
NODE = DEPLOYMENT['runtime']
D = R / 'stream/collection-r4/deployment-r7b'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError('Immutable deployment evidence changed: ' + str(path))
        return
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)


def rpc(action, row=None, **fields):
    if sha(CONFIG) != CONFIG_SHA:
        raise ValueError('Frozen Campaign deployment configuration changed')
    request = dict(deployment=NODE, action=action, row=row, helper_sha256=DEPLOYMENT['image_helper_sha256'], **fields)
    args = [*DEPLOYMENT['ssh'], DEPLOYMENT['host'], shlex.join([DEPLOYMENT['python17'], DEPLOYMENT['image_helper']])]
    reply = subprocess.run(args, input=json.dumps(request), capture_output=True, text=True, timeout=2400)
    if reply.returncode:
        if 'IMAGE_CAPACITY:' in reply.stderr:
            raise ImageCapacityError('Private17 SSD capacity wait; original Task is not failed')
        raise RuntimeError(reply.stderr[-2400:] or reply.stdout[-2400:])
    return json.loads(reply.stdout)


def choose(row):
    # Immutable binding precedes image inspection, initial tests and Ready.
    assigned = dict(row, runtime_node='17', runtime_engine_id=NODE['engine_id'],
        deployment_config=str(CONFIG), deployment_config_sha256=CONFIG_SHA)
    binding = D / 'placements' / (row['task_id'] + '.json')
    freeze(binding, dict(task_id=row['task_id'], slot_id=row['slot_id'], node='17',
        engine_id=NODE['engine_id'], deployment_config=str(CONFIG), deployment_config_sha256=CONFIG_SHA,
        teacher_config_sha256=c.TEACHER_SHA, wheel_sha256=c.WHEEL_SHA))
    assigned.update(deployment_assignment=str(binding), deployment_assignment_sha256=sha(binding))
    return assigned


def image_info(image):
    return rpc('inspect', dict(image_id=image))


def ensure_resident(row):
    if row.get('runtime_engine_id') != NODE['engine_id'] or row.get('runtime_node') != '17':
        raise ValueError('Backend must be selected before image materialization')
    return rpc('ensure', row)


def release_cold_cache(row):
    return rpc('release', row)


def find_basic(row):
    basic = basic_receipt(row)
    if basic is not None:
        return basic
    # A newer native acceptance can supersede an old preparation failure.
    # Its raw receipt, Task bytes and image identity must still validate.
    path = R / 'checks/native-reserve-acceptance-r4' / (row['task_id'] + '.json')
    if path.exists():
        value = json.loads(path.read_text())
        if value['status'] == 'ENV_READY' and value.get('admitted_task'):
            if value.get('raw_outcome') and sha(Path(value['raw_outcome'])) != value['raw_outcome_sha256']:
                raise ValueError('New acceptance source identity changed')
            return path, dict(image_id=value['admitted_task']['image_id'])
    return None


def prepare_identity(row):
    selected = choose(row)
    basic = find_basic(row)
    if basic is None:
        raise ValueError('No accepted original source/image preparation receipt')
    admitted = prepared(selected, basic)
    # prepared() retains the explicit deployment fields while validating the
    # official Task, private test bytes, resources and deadlines.
    return admitted


def initial(row):
    original = Path(row['source_path'] if row['pool'] == 'calibforge' else row['task_path'])
    task = tomllib.loads((original / 'task.toml').read_text())
    from harbor.models.task.config import TaskConfig
    native = TaskConfig.model_validate(task)
    resources = {key: getattr(native.environment, key) for key in ['cpus', 'memory_mb', 'storage_mb', 'gpus']}
    if resources['gpus']:
        raise ValueError('Original Task requires unsupported GPU; no resource downgrade')
    if row['pool'] == 'tmax':
        from tmax_runtime_adapter import runtime_compose_override
        startup = runtime_compose_override(R / 'sources/tmax/original-tasks' / row['task_id'])['services']['main']['command']
        startup = [*startup[:-1], startup[-1].replace('$$', '$')]
        source = R / 'sources/tmax/original-tasks' / row['task_id'] / 'test_initial_state.py'
        remote = NODE['ssd_root'] + '/trusted-initial-r7/' + row['task_id'] + '/test_initial_state.py'
        subprocess.run([*DEPLOYMENT['ssh'], DEPLOYMENT['host'], 'mkdir -p ' + shlex.quote(str(Path(remote).parent))], check=True, timeout=30)
        subprocess.run(['rsync', '-a', '-e', shlex.join(DEPLOYMENT['ssh']), str(source), DEPLOYMENT['host'] + ':' + remote], check=True, timeout=120)
        test = dict(path=remote, sha256=sha(source))
        workdir = home = '/home/user'
    else:
        startup = ['/bin/bash', '-lc', 'trap : TERM INT; sleep infinity & wait']
        test = None
        workdir = native.environment.workdir or '/'
        home = native.environment.env.get('HOME', '/root')
    return rpc('initial', row, resources=resources, startup=startup, initial_test=test,
        workdir=workdir, home=home, initial_timeout=max(120, native.verifier.timeout_sec),probe_id=uuid4().hex)


def native_config(row, kind):
    if sha(Path(DEPLOYMENT['dependency_override'])) != DEPLOYMENT['dependency_override_sha256']:
        raise ValueError('Frozen public dependency bootstrap changed')
    result = c.native_config(row, kind)
    env = dict(DEPLOYMENT['environment'])
    env['extra_docker_compose'] = [*result.environment.extra_docker_compose, DEPLOYMENT['dependency_override']]
    result.environment = result.environment.model_validate(env)
    result.trials_dir = R / 'stream/collection-r4/trials'
    return result


def archive_trial(trial):
    """Keep a verified final native Trial copy on SSD;149 is the mirror."""
    target = NODE['final_logs_root'] + '/' + trial.name
    subprocess.run([*DEPLOYMENT['ssh'], DEPLOYMENT['host'], 'mkdir -p ' + shlex.quote(target)], check=True, timeout=30)
    subprocess.run(['rsync', '-a', '-e', shlex.join(DEPLOYMENT['ssh']), str(trial) + '/',
        DEPLOYMENT['host'] + ':' + target + '/'], check=True, timeout=1800)
    files = [{'path': str(p.relative_to(trial)), 'sha256': sha(p), 'bytes': p.stat().st_size}
        for p in sorted(trial.rglob('*')) if p.is_file() and not p.is_symlink()]
    code = "import json,hashlib,sys;from pathlib import Path;v=json.load(sys.stdin);r=Path(v['root']);errors=[x['path'] for x in v['files'] if not (r/x['path']).is_file() or hashlib.sha256((r/x['path']).read_bytes()).hexdigest()!=x['sha256']];assert not errors,errors;print(json.dumps({'verified_files':len(v['files']),'errors':errors}))"
    reply = subprocess.run([*DEPLOYMENT['ssh'], DEPLOYMENT['host'], shlex.join([DEPLOYMENT['python17'], '-c', code])],
        input=json.dumps(dict(root=target, files=files)), text=True, capture_output=True, check=True, timeout=600)
    return dict(source_native_mirror=str(trial), authoritative_ssd_root=target,
        node='17', engine_id=NODE['engine_id'], files=files, verification=json.loads(reply.stdout),
        result_sha256=sha(trial / 'result.json'), raw_trial_preserved=True)
