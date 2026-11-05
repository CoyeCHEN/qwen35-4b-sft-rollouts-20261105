"""Read native Campaign, frozen SG identities and GPU metadata; never dispatch."""

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen


SETTINGS = {}
R: Path
C: Path
BINDING: Path
BINDING_SHA: str
ARCHIVE_ROOT: Path
ARCHIVE_PLAN_SHA: str


def configure(settings):
    global SETTINGS, R, C, BINDING, BINDING_SHA, ARCHIVE_ROOT, ARCHIVE_PLAN_SHA
    for key in ('run_root', 'control_root', 'serving_binding_path', 'raw_archive_root', 'campaign_metadata_path'):
        require(Path(settings[key]).is_absolute(), 'Observation paths must be explicitly absolute')
    SETTINGS = settings
    R, C = Path(settings['run_root']), Path(settings['control_root'])
    BINDING = Path(settings['serving_binding_path'])
    BINDING_SHA = settings['serving_binding_sha256']
    ARCHIVE_ROOT = Path(settings['raw_archive_root'])
    ARCHIVE_PLAN_SHA = settings['raw_archive_plan_sha256']


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read_json(path):
    data = path.read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
    require(result.returncode == 0, f'{args[0]} rc={result.returncode}: {result.stderr[-500:]}')
    return result.stdout


def http_json(port, endpoint):
    # Only mature read-only metadata APIs; no completion/count/embedding requests.
    require(endpoint in ('get_model_info', 'v1/models', 'v1/loads'), 'Unregistered GET')
    with urlopen(f'http://127.0.0.1:{port}/{endpoint}', timeout=2) as response:
        value = response.read(1024 * 1024 + 1)
    require(len(value) <= 1024 * 1024, 'Metadata response exceeds 1 MiB')
    return json.loads(value)


def native_campaign():
    owner, owner_sha = read_json(C / 'NATIVE_ADVANCE_OWNER.json')
    report_path = C / 'NATIVE_ADVANCE_STATUS.json'
    report, report_sha = read_json(report_path)
    require(read_json(C / 'NATIVE_ADVANCE_OWNER.json')[1] == owner_sha, 'Owner changed during observation')
    metadata, metadata_sha = read_json(Path(SETTINGS['campaign_metadata_path']))
    require(metadata_sha == SETTINGS['campaign_metadata_sha256'], 'Frozen Campaign observation metadata differs')
    require(metadata['kind'] == 'NATIVE_MULTICAMPAIGN_OBSERVATION_METADATA_R1' and metadata['maximum_active_native_model_trials'] == 8, 'Unexpected Campaign metadata/lane bound')
    require(owner['native_campaigns'] == metadata['campaigns'] and owner['native_harbor'] == metadata['native_harbor'], 'Owner/Campaign runtime registration differs')
    require(owner['expected_harbor_commit'] == metadata['expected_harbor_commit'] and owner['fixed_denominators'] == metadata['fixed_denominators'] == {'synthetic32': 32, 'common30': 180}, 'Owner/source or fixed scope differs')
    require(report['kind'] == 'native_multi_campaign_observation' and report['schema_version'] == 1, 'Unknown multi-Campaign observation schema')
    require(report['source_owner_sha256'] == owner_sha and report['owner_stable_during_observation'] is True, 'Owner/report identity differs')
    require(report['observer_source_sha256'] == SETTINGS['campaign_observer_source_sha256'], 'Native observer source differs')
    require(report['observation_metadata_sha256'] == metadata_sha, 'Published observation metadata differs')
    runtime = report['native_runtime_code_identity']
    require(runtime['harbor_commit'] == metadata['expected_harbor_commit'] and runtime['installed_package_sha256'] == metadata['expected_installed_package_sha256'], 'Installed native Harbor source differs')
    specs_sha = hashlib.sha256(json.dumps(owner['native_campaigns'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    require(report['native_campaigns_sha256'] == specs_sha and report['registered_campaigns'] == 11 and report['fixed_total_model_trials'] == 212, 'Registered multi-Campaign scope differs')
    age = time.time() - report_path.stat().st_mtime
    require(-30 <= age < 1800, 'Native report is stale or clock identity is unknown')
    return dict(status='PARTIAL_QUERY_FAILURE' if report['query_errors'] else 'NATIVE_MULTI_CAMPAIGN_OBSERVATION_VERIFIED',
                owner_sha256=owner_sha, report_sha256=report_sha, report_age_seconds=age,
                current_stage='NATIVE_HARBOR_MULTI_CAMPAIGN', native_unit=owner['controller_unit'],
                execution_host=owner['host'], native_harbor=owner['native_harbor'],
                groups=report['groups'], report=report, query_errors=report['query_errors'],
                native_agent_phase_is_not_Serving_generation_concurrency=True,
                no_model_to_GPU_or_port_inference=True, owner_process_not_requeried_across_hosts=True)


def scheduler_load(value):
    aggregate = value['aggregate']
    keys = ('total_running_reqs', 'total_waiting_reqs', 'total_reqs')
    require(all(type(aggregate.get(key)) is int and aggregate[key] >= 0 for key in keys), 'Invalid native scheduler counters')
    require(isinstance(value['loads'], list) and bool(value['loads']), 'Native scheduler rank metadata missing')
    queues = []
    for rank in value['loads']:
        queue = rank['queues']
        require(all(type(queue.get(key)) is int and queue[key] >= 0 for key in ('waiting', 'grammar', 'paused', 'retracted')), 'Invalid rank queues')
        queues.append(queue)
    return dict(version=value['version'], aggregate={key: aggregate[key] for key in keys}, rank_queues=queues,
                request_counts_are_not_task_concurrency=True)


def serving_identity(expected, unit):
    identity = expected['process_identity']
    proc = Path('/proc') / str(identity['pid'])
    ticks = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    argv_sha = hashlib.sha256((proc / 'cmdline').read_bytes()).hexdigest()
    require(ticks == identity['start_ticks'] and argv_sha == identity['argv_sha256'], 'Frozen SG PID/ticks/argv differs')
    require(unit['ActiveState'] == 'active' and int(unit['MainPID']) == identity['pid'], 'SG unit/MainPID differs')
    cgroup = (proc / 'cgroup').read_text()
    require(expected['unit'] in cgroup, 'SG PID is not in expected native unit')
    environment = dict(value.split(b'=', 1) for value in (proc / 'environ').read_bytes().split(b'\0') if b'=' in value)
    visible_gpu = environment.get(b'CUDA_VISIBLE_DEVICES', b'').decode()
    require(visible_gpu == expected['gpu_uuid'], 'SG process GPU UUID differs')
    manifest = Path(expected['source_identity']['model_manifest_path'])
    require(hashlib.sha256(manifest.read_bytes()).hexdigest() == expected['weight_version'], 'HF manifest SHA differs')
    model = http_json(expected['port'], 'get_model_info')
    require(model['model_path'] == expected['model_path'] and model['weight_version'] == expected['weight_version'], 'Live model path/weight differs')
    models = http_json(expected['port'], 'v1/models')
    require([row['id'] for row in models['data']] == [expected['model_id']], 'Live model alias differs')
    return dict(status='CURRENT_SG_IDENTITY_VERIFIED', pid=identity['pid'], start_ticks=ticks,
                argv_sha256=argv_sha, cgroup=cgroup, model_info=model,
                visible_gpu_uuid=visible_gpu,
                native_scheduler_load=scheduler_load(http_json(expected['port'], 'v1/loads')))


def serving_instances():
    binding, binding_sha = read_json(BINDING)
    require(binding_sha == BINDING_SHA and binding['frozen'] is True, 'Frozen eight-service binding differs')
    replicas = binding['bindings']
    require(sorted(row['gpu_index'] for row in replicas) == list(range(8)), 'Eight GPU bindings missing')
    require(len({row['gpu_uuid'] for row in replicas}) == len({row['port'] for row in replicas}) == 8, 'GPU UUID/port binding duplicated')
    artifact, source_sha = read_json(Path(binding['sglang_source_manifest_path']))
    require(source_sha == binding['sglang_source_manifest_sha256'], 'SG source manifest differs')
    sg = next(row for row in artifact['rows'] if row['kind'] == 'sglang')
    require(sg['sha256'] == binding['sglang_wheel_sha256'], 'SG wheel differs')
    for relative, expected in sg['modules'].items():
        actual = Path(binding['sglang_installed_root']) / relative.removeprefix('sglang/')
        require(hashlib.sha256(actual.read_bytes()).hexdigest() == expected, 'Installed SG source differs: ' + relative)
    output = command(['systemctl', '--user', 'show', *[row['unit'] for row in replicas], '-p', 'Id', '-p', 'MainPID', '-p', 'ActiveState'])
    units = {}
    for block in output.strip().split('\n\n'):
        values = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
        if values.get('Id'):
            units[values['Id']] = values
    rows = []
    for expected in replicas:
        row = {key: expected[key] for key in ('gpu_index', 'gpu_uuid', 'model_id', 'model_path', 'weight_version', 'port', 'unit')}
        try:
            row.update(serving_identity(expected, units[expected['unit']]))
        except Exception as error:
            row.update(status='UNKNOWN', error=repr(error))
        rows.append(row)
    return dict(binding_path=str(BINDING), binding_sha256=binding_sha, source_modules_verified=len(sg['modules']),
                services=rows, verified_services=sum(row['status'] == 'CURRENT_SG_IDENTITY_VERIFIED' for row in rows),
                idle_gpu_does_not_release_service=True, metadata_GETs_are_not_model_generation=True)


def gpu_metadata():
    columns = ('index', 'uuid', 'memory.total', 'memory.used', 'utilization.gpu')
    output = command(['nvidia-smi', '--query-gpu=' + ','.join(columns), '--format=csv,noheader,nounits'])
    rows = [dict(zip(columns, [value.strip() for value in row])) for row in csv.reader(output.splitlines())]
    require(len(rows) == 8, 'GPU query did not return eight cards')
    processes = command(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid,process_name,used_memory', '--format=csv,noheader,nounits'])
    return dict(status='OBSERVED', gpus=rows, compute_processes_csv=processes,
                memory_unit='MiB', utilization_unit='percent', no_CUDA_context_created=True,
                zero_utilization_is_not_an_empty_or_authorized_slot=True)


def archive_progress():
    path = ARCHIVE_ROOT / 'PROGRESS_R2.json'
    progress, sha = read_json(path)
    require(progress['plan_sha256'] == ARCHIVE_PLAN_SHA, 'Raw preservation plan differs')
    done, total = progress['complete_raw_bytes'], progress['expected_raw_bytes']
    require(type(done) is int and type(total) is int and 0 <= done <= total == 731008204800, 'Invalid raw archive byte counts')
    final = ARCHIVE_ROOT / 'RAW_CHUNK_ARCHIVE_ACCEPTANCE_R2.json'
    value = dict(status='READABLE', path=str(path), sha256=sha, progress=progress,
                 progress_is_not_global_SHA_acceptance=True, original_holder_release_not_authorized=True)
    if final.exists():
        acceptance, acceptance_sha = read_json(final)
        require(acceptance['kind'] == 'FA00_RAW_CHUNK_ARCHIVE_ACCEPTANCE_R2'
                and acceptance['plan_sha256'] == ARCHIVE_PLAN_SHA
                and acceptance['passed'] is True and acceptance['source_raw_bytes'] == total
                and acceptance['every_source_chunk_matches_independent_target_decode'] is True
                and acceptance['full_raw_sha256'] == acceptance['full_raw_sha256_from_ordered_second_decode'],
                'Archive final acceptance failed')
        value.update(final_acceptance_path=str(final), final_acceptance_sha256=acceptance_sha,
                     full_raw_sha256=acceptance['full_raw_sha256'])
    return value


def observe():
    started = time.monotonic()
    state = dict(kind='READ_ONLY_NODE18_MULTI_CAMPAIGN_GPU_OBSERVATION_R38', checked_at=time.time(),
                 read_only=True, model_generation_calls=0, automatic_dispatch=False,
                 old_training_and_H54_scans_removed=True, errors=[])
    for name, operation in (('native_campaign', native_campaign), ('gpu', gpu_metadata),
                            ('serving', serving_instances), ('raw_archive', archive_progress)):
        try:
            state[name] = operation()
            if name == 'serving' and state[name]['verified_services'] != 8:
                state['errors'].append('serving: one or more current service identities UNKNOWN')
        except Exception as error:
            state[name] = dict(status='UNKNOWN', error=repr(error))
            state['errors'].append(name + ': ' + repr(error))
    if state.get('native_campaign', {}).get('query_errors'):
        state['errors'].append('native_campaign: one or more native status queries UNKNOWN; other Campaign observations retained')
    if state.get('native_campaign', {}).get('report', {}).get('lane_phase_overlap'):
        state['errors'].append('native_campaign: more than one native Agent phase observed in a registered one-Trial lane')
    state['observation_seconds'] = time.monotonic() - started
    if state.get('gpu', {}).get('status') == 'OBSERVED' and state.get('serving', {}).get('verified_services') == 8:
        actual = {int(row['index']): row['uuid'] for row in state['gpu']['gpus']}
        expected = {row['gpu_index']: row['gpu_uuid'] for row in state['serving']['services']}
        if actual != expected:
            state['errors'].append('gpu: physical index/UUID differs from frozen service bindings')
    state['healthy_observation'] = not state['errors']
    return state


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--config-sha256', required=True)
    args = parser.parse_args()
    settings, settings_sha = read_json(args.config)
    require(settings_sha == args.config_sha256, 'Frozen observation configuration differs')
    configure(settings)
    observation = observe()
    print(json.dumps(observation))
    raise SystemExit(0 if observation['healthy_observation'] else 1)
