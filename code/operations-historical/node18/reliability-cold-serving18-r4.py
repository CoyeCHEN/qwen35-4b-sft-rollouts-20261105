"""Finite cold releases for the existing unique controller; no task dispatch."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid as uuid_module

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C = Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
D = R / 'reliability-repair'
PY = R / 'env/serve-reliability-r1/bin/python'
ARTIFACTS = D / 'artifacts-r1/INTEGRATED_ARTIFACT_MANIFEST_R1.json'
ARTIFACT_SHA = '30856858795f37e00f8c355173cafd95fa4fee6775e227dc807064ab75d59753'
WORKER = 'qwen35-accepted30-new-m2-e5-diag-20261102-r4.service'
JOB = R / 'formal-native-eval-r1/jobs' / WORKER.removesuffix('.service')
TARGETS = [
    dict(tag='m0', gpu_index=2, port=18302, old_port=18302,
         old_unit='qwen35-new772-cold-new-m2-e5-20261101.service',
         model_path=str(R / 'assets/source17-r1/student-tokenizer'),
         model_manifest=str(R / 'checks/M0_FIXED_REVISION_WEIGHT_SHA.json'),
         model_manifest_sha256='e9624087f590acf307a1676ae1206c545d817209a67f78d1f62f9ac1ea34c4ff',
         weight_files=['model.safetensors-00001-of-00002.safetensors', 'model.safetensors-00002-of-00002.safetensors']),
    dict(tag='new-m2-e5', gpu_index=3, port=18308, old_port=18308,
         old_unit='qwen35-new772-diag150-e5-gpu3-20261102-r1.service',
         model_path=str(R / 'runs/new-m2-tmax356-128k-e5'),
         model_manifest=str(R / 'runs/new-m2-tmax356-128k-e5/HF_EXPORT_COMPLETE.json'),
         model_manifest_sha256='c4b4c5ae2649d1de5312deda149ebdec0f08089a7ebaf99738faba1dbac16487',
         weight_files=['model.safetensors']),
]


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(p, value):
    p = Path(p)
    temporary = p.with_suffix(p.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(p)


def props(unit):
    return dict(line.split('=', 1) for line in subprocess.check_output(
        ['systemctl', '--user', 'show', unit, '-p', 'MainPID', '-p', 'LoadState',
         '-p', 'ActiveState', '-p', 'ControlGroup'], text=True, timeout=5).splitlines())


def get(port, path):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://127.0.0.1:{port}{path}', timeout=8) as response:
        return json.load(response)


def owner_check(admission):
    owner = read(C / 'NATIVE_ADVANCE_OWNER.json')
    if owner != admission['unique_controller_owner']:
        raise RuntimeError('Unique controller owner changed; do not release a service')
    stat = Path('/proc') / str(owner['pid']) / 'stat'
    if stat.read_text().rsplit(')', 1)[1].split()[19] != owner['start_ticks']:
        raise RuntimeError('Unique controller process identity differs')


def release_proof():
    worker = props(WORKER)
    if worker['MainPID'] != '0' or worker['ActiveState'] not in ['inactive', 'failed']:
        raise RuntimeError('Legacy M2 E5 worker still owns its pending queue')
    if sha(JOB / 'result.json') != '69eefde948167f6b72046400b19a2f1f03c300247ce64f11445869b4a6f48870':
        raise RuntimeError('Closed native M2 E5 aggregate identity changed')
    aggregate = read(JOB / 'result.json')
    if not aggregate.get('finished_at') or any(aggregate['stats'][k] for k in
        ['n_running_trials', 'n_pending_trials', 'n_cancelled_trials']):
        raise RuntimeError('Legacy M2 E5 native Job has not closed')
    results = list(JOB.glob('*/result.json'))
    native = [read(p) for p in results]
    if aggregate['n_total_trials'] != 24 or len(results) != 24 or not all(x.get('finished_at') for x in native):
        raise RuntimeError('Legacy Job native terminal identities incomplete')
    identifiers = [str(uuid_module.UUID(x['id'])) for x in native]
    if len(set(identifiers)) != 24 or any(x['config']['job_id'] != aggregate['id'] for x in native):
        raise RuntimeError('Native Trial UUID or Job membership differs')
    matrix = read(R / 'formal-native-eval-r1/checks/DIAGNOSTIC150_MATRIX_R6.json')
    if matrix['models']['new-m2-e5-diag']['terminal'] != 30:
        raise RuntimeError('Legacy logical M2 E5 population is not 30/30 terminal')
    leases = importlib.import_module('read-priority32-gpu-leases149-r10').observe_from_node18()
    if leases['unknown_model_identity_leases']:
        raise RuntimeError('A live CLI has unresolved model identity')
    forbidden = {18302, 18308}
    if any(x['port'] in forbidden for x in leases['active_cli_leases']):
        raise RuntimeError('Legacy model service still has a real CLI lease')
    unknown = []
    for row in leases['containers']:
        if row['status'] != 'UNKNOWN':
            continue
        matches = list((R / 'formal-native-eval-r1/jobs').glob(
            '*/*/remote-docker-' + row['identity'] + '.jsonl'))
        if len(matches) != 1:
            raise RuntimeError('Unresolved container cannot be attributed to a native Trial')
        journal = matches[0]
        # Native provider metadata, never filename resemblance alone. Read only
        # the bounded setup prefix; tool output later in the journal is irrelevant.
        events = []
        with journal.open() as stream:
            for _ in range(64):
                line = stream.readline(65536)
                if not line:
                    break
                if not line.endswith('\n'):
                    raise RuntimeError('Cannot validate a bounded provider setup record')
                events.append(json.loads(line))
                if any(e.get('action') == 'connected' for e in events) and any(
                    e.get('container') == row['container_id'] for e in events):
                    break
        if not events or any(e.get('identity') != row['identity'] or e.get('project') != row['project']
                             or e.get('session_id') != journal.parent.name + '__env' for e in events):
            raise RuntimeError('Provider session identity does not match the observed container')
        if not any(e.get('action') == 'connected' and e.get('endpoint') == 'ssh://chenkeyi@127.0.0.1:18449'
                   and e.get('daemon_id') == 'c6e16cdf-e878-4cc5-84c8-78a56c54b5c5' for e in events):
            raise RuntimeError('Provider Engine identity not proven')
        if not any(e.get('container') == row['container_id'] for e in events):
            raise RuntimeError('Provider journal does not identify the actual observed container')
        config = matches[0].parent / 'config.json'
        model = read(config)['agent']['kwargs']['config']['model']
        parsed = urllib.parse.urlsplit(model['baseUrl'])
        port = parsed.port
        if parsed.scheme != 'http' or parsed.hostname not in ['172.17.0.1', '127.0.0.1', 'localhost'] or parsed.username or parsed.password or port is None:
            raise RuntimeError('Unknown container has an unregistered model service URL')
        bindings = [x for x in leases['campaign_bindings']['bindings']
                    if x['model_id'] == model['id'] and x['port'] == port]
        if len(bindings) != 1:
            raise RuntimeError('Unknown container model alias and port have no unique frozen binding')
        if port in forbidden:
            raise RuntimeError('Setup/unknown container still routes to a service being released')
        unknown.append(dict(container_id=row['container_id'], config_path=str(config),
                            config_sha256=sha(config), model_id=model['id'], port=port,
                            native_provider_setup_events=events,
                            original_observation_error=row.get('error')))
    return dict(at=time.time(), native_job_result_sha256=sha(JOB / 'result.json'),
                native_terminal_trials=len(results), logical_terminal=30,
                leases=leases, unknown_containers_attributed_to_other_services=unknown)


def old_identity(target, uuid):
    old = props(target['old_unit'])
    if old['ActiveState'] != 'active' or old['MainPID'] == '0':
        raise RuntimeError('Expected project-owned old service identity not active')
    group = old['ControlGroup']
    if not group.startswith('/user.slice/') or not group.endswith('/' + target['old_unit']):
        raise RuntimeError('Old unit has no valid project service control group')
    pid = int(old['MainPID'])
    process = Path('/proc') / str(pid)
    ticks = (process / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    if ('CUDA_VISIBLE_DEVICES=' + uuid).encode() not in (process / 'environ').read_bytes().split(b'\0'):
        raise RuntimeError('Old service does not own the intended authorized GPU')
    argv = (process / 'cmdline').read_bytes().split(b'\0')
    if b'sglang.launch_server' not in argv:
        raise RuntimeError('Unexpected process in old project serving unit')
    live = get(target['old_port'], '/model_info')
    if live['model_path'] != str(R / 'runs/new-m2-tmax356-128k-e5') or live['weight_version'] != TARGETS[1]['model_manifest_sha256']:
        raise RuntimeError('Old service actual weights differ')
    load = get(target['old_port'], '/v1/loads')
    keys = ['total_running_reqs', 'total_waiting_reqs', 'total_reqs']
    if not load.get('loads') or any(type(load.get('aggregate', {}).get(k)) is not int or load['aggregate'][k] != 0 for k in keys):
        raise RuntimeError('Old serving scheduler still owns a running or waiting request')
    for rank in load['loads']:
        if any(type(rank.get('queues', {}).get(k)) is not int or rank['queues'][k] != 0
               for k in ['waiting', 'grammar', 'paused', 'retracted']):
            raise RuntimeError('Old serving scheduler has an unresolved auxiliary queue')
    applications = subprocess.check_output(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid',
                                            '--format=csv,noheader,nounits'], text=True)
    for line in applications.splitlines():
        gpu, app = [v.strip() for v in line.split(',')]
        if gpu != uuid:
            continue
        groups = [line.split(':', 2)[2] for line in (Path('/proc') / app / 'cgroup').read_text().splitlines()]
        if not groups or not all(g == group or g.startswith(group + '/') for g in groups):
            raise RuntimeError('Another process owns this GPU; preserve it')
    return dict(pid=pid, start_ticks=ticks, control_group=group, gpu_uuid=uuid,
                native_scheduler_load={k: load['aggregate'][k] for k in keys})


def main(admission_path):
    admission = read(admission_path)
    owner_check(admission)
    if admission['source_sha256'] != sha(__file__) or sha(ARTIFACTS) != ARTIFACT_SHA:
        raise RuntimeError('Cold serving source or artifacts differ from frozen admission')
    artifacts = read(ARTIFACTS)
    for row in artifacts['rows']:
        if sha(ARTIFACTS.parent / row['wheel']) != row['sha256']:
            raise RuntimeError('Frozen Wheel identity differs')
    installed = read(D / 'INSTALLED_NEW_SERVING_CPU_IMPORT_R1.json')
    if not installed['passed'] or installed['metadata_version'] != '0.5.10+rsi.reliability.20261103.1':
        raise RuntimeError('Installed independent Serving environment not accepted')
    proof = release_proof()
    write(D / 'COLD_SERVICE_RELEASE_PROOF_R2.json', proof)
    allowed = read(R / 'new-sft/workspace/configs/runtime.json')['authorized_gpu_uuids']
    completed = []
    for target in TARGETS:
        owner_check(admission)
        target = dict(target)
        unit = 'qwen35-reliability-cold-' + target['tag'] + '-20261103-r1.service'
        if props(unit)['LoadState'] != 'not-found':
            raise RuntimeError('Cold unit already exists; audit it, never silently restart')
        uuid = allowed[target['gpu_index']]
        old = old_identity(target, uuid)
        manifest = Path(target['model_manifest'])
        if sha(manifest) != target['model_manifest_sha256']:
            raise RuntimeError('Approved HF release Manifest identity differs')
        release = read(manifest)
        if target['tag'] == 'm0' and release['model_revision'] != '851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a':
            raise RuntimeError('M0 revision differs')
        names = [m.get('file', m.get('path', m.get('name'))) for m in release['files']]
        if not names or any(not isinstance(n, str) for n in names) or len(names) != len(set(names)) or set(target['weight_files']) != {n for n in names if n.endswith('.safetensors')}:
            raise RuntimeError('HF release is missing the complete registered weight set')
        for member, name in zip(release['files'], names):
            if not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts:
                raise RuntimeError('HF release contains an invalid relative filename')
            path = Path(target['model_path']) / name
            if path.stat().st_size != member['bytes'] or sha(path) != member['sha256']:
                raise RuntimeError('HF model file differs: ' + name)
        # Prove absence of requests immediately before native service shutdown.
        release_proof()
        owner_check(admission)
        if old_identity(target, uuid) != old:
            raise RuntimeError('Old serving process identity changed before release')
        subprocess.run(['systemctl', '--user', 'stop', target['old_unit']], check=True, timeout=45)
        if (Path('/proc') / str(old['pid'])).exists():
            stat = (Path('/proc') / str(old['pid']) / 'stat').read_text().rsplit(')', 1)[1].split()
            if stat[19] == old['start_ticks']:
                raise RuntimeError('Old serving process has not exited')
        if subprocess.check_output(['ss', '-ltn', 'sport = :' + str(target['port'])], text=True).splitlines()[1:]:
            raise RuntimeError('Cold port was not released; do not stop another process')
        memory = subprocess.check_output(['nvidia-smi', '-i', uuid, '--query-gpu=memory.used',
                                         '--format=csv,noheader,nounits'], text=True)
        if int(memory.strip()) >= 100:
            raise RuntimeError('GPU not released; do not interfere with remaining processes')
        raw = D / ('private-raw-serving-' + target['tag'] + '-r1')
        raw.mkdir(mode=0o700)
        command = [str(PY), '-m', 'sglang.launch_server', '--model-path', target['model_path'],
                   '--host', '127.0.0.1', '--port', str(target['port']), '--dtype', 'bfloat16',
                   '--context-length', '262144', '--tp', '1', '--reasoning-parser', 'qwen3',
                   '--tool-call-parser', 'qwen3_coder', '--mem-fraction-static', '0.80',
                   '--max-running-requests', '8', '--attention-backend', 'triton', '--mamba-backend', 'triton',
                   '--served-model-name', 'qwen35-reliability-' + target['tag'], '--weight-version', sha(manifest),
                   '--log-requests', '--log-requests-level', '3', '--log-requests-format', 'json',
                   '--log-requests-target', str(raw)]
        environment = dict(CUDA_VISIBLE_DEVICES=uuid, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
            TMPDIR=str(R / 'tmp'), XDG_CACHE_HOME=str(R / 'cache/serve-new11'),
            HF_HOME=str(R / 'cache/hf'), OMP_NUM_THREADS='4',
            TRITON_CACHE_DIR=str(R / 'cache/serve-triton'),
            TORCH_EXTENSIONS_DIR=str(R / 'cache/serve-torch-extensions'),
            CUDA_CACHE_PATH=str(R / 'cache/cuda-driver'),
            PATH=str(PY.parent) + ':' + str(R / 'env/serve-new11-r1/bin') + ':/usr/local/cuda/bin:/usr/bin:/bin')
        log = D / ('cold-' + target['tag'] + '-r1.log')
        native = ['systemd-run', '--user', '--unit=' + unit, '--property=MemoryMax=96G',
                  '--property=StandardOutput=append:' + str(log), '--property=StandardError=append:' + str(log)]
        native += ['--setenv=' + k + '=' + v for k, v in environment.items()]
        subprocess.run(native + command, check=True, capture_output=True, text=True, timeout=10)
        completed.append(dict(**target, unit=unit, gpu_uuid=uuid, weight_version=sha(manifest),
                              model_id='qwen35-reliability-' + target['tag'], command=native + command,
                              old_process_identity=old, raw_capture=str(raw)))
        write(D / 'COLD_SERVICES_LAUNCHED_R1.json', dict(at=time.time(), replicas=completed,
            source_sha256=sha(__file__), unique_controller_owner=admission['unique_controller_owner'],
            model_generation_calls_by_bootstrap=0, hot_weight_switching=False))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
