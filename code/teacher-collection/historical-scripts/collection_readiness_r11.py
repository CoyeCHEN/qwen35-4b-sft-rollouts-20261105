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
import collection_readiness_r9 as previous_readiness
from collection_readiness_r4 import prepared, blocking_review, verify_nop as original_verify_nop, basic_receipt
from native_image_archive149_r1 import ImageCapacityError

R = c.R
CONFIG = R / 'configs/campaign-deployment17-r11.json'
DEPLOYMENT = json.loads(CONFIG.read_text())
CONFIG_SHA = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
NODE = DEPLOYMENT['runtime']
D = Path(DEPLOYMENT['readiness_root'])


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
    variant=public_variant(row['task_id'])
    if variant is not None:
        candidate=variant['admitted_task'];path=Path(candidate['prepared_task_path'])
        if admitted['image_id']!=variant['original_published_image_id']:
            raise ValueError('Public dependency correction original source image differs')
        expected=tomllib.loads((Path(admitted['prepared_task_path'])/'task.toml').read_text())
        expected['environment']['docker_image']=variant['image_id']
        if sha(path/'task.toml')!=candidate['prepared_task_toml_sha256'] or tomllib.loads((path/'task.toml').read_text())!=expected:
            raise ValueError('Derived external Task copy changed additional fields')
        if sha(path/'instruction.md')!=row['instruction_sha256']:
            raise ValueError('Original public instruction changed')
        for artifact in admitted['verifier_files']:
            if sha(path/artifact['path'])!=artifact['sha256']:
                raise ValueError('Official verifier member changed')
        admitted.update(prepared_task_path=str(path),prepared_task_toml_sha256=sha(path/'task.toml'),image_id=variant['image_id'],
            original_published_image_id=variant['original_published_image_id'],public_verifier_dependency_approval=variant['approval_path'],
            public_verifier_dependency_approval_sha256=variant['approval_sha256'])
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
    case=DEPLOYMENT.get('task_public_dependencies',{}).get(row['task_id'],{})
    additions=[]
    for item in case.get('extra_docker_compose',[]):
        path=Path(item['path'])
        if sha(path)!=item['sha256']:raise ValueError('Public dependency runtime binding changed')
        additions.append(path)
    env['extra_docker_compose'] = [*result.environment.extra_docker_compose, DEPLOYMENT['dependency_override'],*additions]
    for key,value in case.get('verifier_env',{}).items():
        if key in result.verifier.env and result.verifier.env[key]!=value:
            raise ValueError('Public dependency override would replace an existing verifier setting')
        result.verifier.env[key]=value
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


def public_variant(ident):
    declaration=DEPLOYMENT['public_verifier_dependency_approvals149']
    path=Path(declaration['path'])
    if sha(path)!=declaration['sha256']:raise ValueError('Approved public dependency manifest changed')
    value=json.loads(path.read_text())
    item=next((x for x in value['tasks'] if x['task_id']==ident),None)
    if item is None:return None
    approval=Path(item['path'])
    if sha(approval)!=item['sha256']:raise ValueError('Image-specific native approval changed')
    result=json.loads(approval.read_text())
    for kind,native in result['native_results'].items():
        if sha(Path(native['trial'])/'result.json')!=native['result_sha256']:
            raise ValueError('Approved original native Result changed')
    return dict(result,approval_path=str(approval),approval_sha256=sha(approval))


def verify_nop(result,trial,row):
    variant=public_variant(row['task_id']) if row['pool']=='calibforge' else None
    if variant is None or not variant.get('public_goal_boundary_review'):
        return original_verify_nop(result,trial,row)
    if row['image_id']!=variant['image_id']:raise ValueError('Goal-module review belongs to another image')
    review_path=Path(variant['public_goal_boundary_review'])
    if sha(review_path)!=variant['public_goal_boundary_review_sha256']:
        raise ValueError('Image-specific public Goal review changed')
    review=json.loads(review_path.read_text())
    if result.exception_info or result.infrastructure_errors:raise ValueError('Native candidate lifecycle/infrastructure failure')
    raw=json.loads((trial/'result.json').read_text())
    reward=(raw.get('verifier_result') or {}).get('rewards',{}).get('reward')
    if not (raw.get('verifier') or {}).get('finished_at') or reward not in (0,1):
        raise ValueError('Original official verifier did not finish')
    import re
    text='\n'.join(p.read_text(errors='replace') for p in (trial/'verifier').glob('test-*.txt'))
    missing=set(re.findall(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]",text))
    if not missing.issubset(set(review['missing_modules'])):
        raise ValueError('An unreviewed verifier dependency is missing')
    if any(value in text for value in ['ERROR collecting','ImportError while importing','command not found','No module named pytest']):
        raise ValueError('Original verifier executable/collection failed')
    return reward


_normalized_legacy_ready={}


def readiness_roots():
    return [*[Path(path) for path in DEPLOYMENT['legacy_readiness']['roots']],D,Path(DEPLOYMENT['controller_root'])]


def normalize_ready(value,path):
    if value.get('deployment_config_sha256')==CONFIG_SHA:return value
    if value.get('deployment_config_sha256')!=previous_readiness.CONFIG_SHA:
        value=previous_readiness.normalize_ready(value,path)
    declaration=DEPLOYMENT['legacy_readiness']
    old_config=Path(declaration['config'])
    if value.get('deployment_config_sha256')!=declaration['sha256'] or sha(old_config)!=declaration['sha256']:
        raise ValueError('Ready belongs to an undeclared deployment transition')
    previous=json.loads(old_config.read_text())
    if previous['environment']!=DEPLOYMENT['environment'] or any(NODE.get(key)!=item for key,item in previous['runtime'].items()):
        raise ValueError('Legacy native acceptance changed Engine/storage/runtime semantics')
    if sha(Path(value['placement']))!=value['placement_sha256']:
        raise ValueError('Original accepted placement changed')
    key=(str(path),sha(path))
    if key not in _normalized_legacy_ready:
        admitted=value['admitted_task']
        task=Path(admitted['prepared_task_path'])
        if sha(task/'task.toml')!=admitted['prepared_task_toml_sha256'] or sha(task/'instruction.md')!=admitted['instruction_sha256']:
            raise ValueError('Original prepared Task changed')
        for artifact in admitted['verifier_files']:
            if sha(task/artifact['path'])!=artifact['sha256']:raise ValueError('Official Task verifier changed')
        assigned=choose(admitted)
        _normalized_legacy_ready[key]=dict(value,admitted_task=assigned,engine_id=NODE['engine_id'],
            deployment_config_sha256=CONFIG_SHA,placement=assigned['deployment_assignment'],
            placement_sha256=assigned['deployment_assignment_sha256'],
            original_native_ready_deployment_sha256=declaration['sha256'],
            original_native_ready_receipt=str(path),original_native_ready_receipt_sha256=key[1],
            deployment_transition='Same Engine, socket, storage, runtime options, Task and native acceptance; only exact image resolution and explicit approved public verifier dependency bindings change')
    return _normalized_legacy_ready[key]
