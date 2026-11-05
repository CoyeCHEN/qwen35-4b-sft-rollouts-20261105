"""Finite root-only admission leaf; called under the existing controller lock."""
import hashlib
import json
import os
from pathlib import Path

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C = Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
B = R / 'reliability-repair/new-six-serving-acceptance-r2'
INDEX_SHA = '208c588e5ad6e8b70450afd0025b41574c06e3a1022d74ca212c2b6c0722e12f'
PAIRS = ('batch01-gpu0-gpu5', 'batch02-gpu1-gpu4', 'batch03-gpu6-gpu7')

def read(path): return json.loads(Path(path).read_bytes())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value, reason):
    if not value: raise RuntimeError(reason)

def once(path, value):
    if path.exists():
        require(read(path) == value, 'Existing ACTUAL conflicts; never overwrite: ' + str(path))
        return
    temporary = path.with_name(path.name + '.' + str(os.getpid()) + '.tmp')
    created = False
    try:
        with temporary.open('x') as stream:
            created = True
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n'); stream.flush(); os.fsync(stream.fileno())
        try: os.link(temporary, path)
        except FileExistsError: require(read(path) == value, 'Concurrent ACTUAL conflicts')
    finally:
        if created and temporary.exists(): temporary.unlink()

def admit(folder, stage, plan, deployment, owner, launch):
    template = read(folder / (stage + '_ADMISSION_TEMPLATE_R2.json'))
    source = B / ('probe_new_service_counter_zero18_r2.py' if stage == 'ZERO' else 'finite_serving_acceptance18_new_instances_r4.py')
    actual = folder / (stage + '_PLAN_ACTUAL_R2.json'); once(actual, plan)
    extra = dict(template, template_only=False, source_sha256=sha(source), plan_sha256=sha(actual),
        unique_controller_owner=owner, cold_manifest_path=str(deployment), cold_manifest_sha256=sha(deployment))
    admission = folder / (stage + '_ADMISSION_ACTUAL_R2.json')
    output = folder / ('zero-run-r1' if stage == 'ZERO' else 'finite-run-r1')
    if admission.exists():
        old = read(admission)
        require(all(old.get(key) == value for key, value in extra.items()), 'Persistent admission conflicts; no retry')
        return 'ADMITTED_NO_AUTORETRY'
    require(not output.exists(), 'Existing output without admission requires audit, not relaunch')
    require(extra['source_sha256'] == sha(source) and extra['unique_controller_owner'] == owner, 'Native launch auto-field expectation differs')
    launch_extra = {key: value for key, value in extra.items() if key not in {'source_sha256', 'unique_controller_owner'}}
    result = launch('qwen35-reliability-new-six-' + folder.name + '-' + stage.lower() + '-20261103-r2.service', str(source),
        ['--plan', str(actual), '--admission', str(admission), '--tool-schemas', str(B / 'FINAL5_ELEVEN_TOOL_SCHEMAS_R2.json'),
         '--owner-state', str(C / 'NATIVE_ADVANCE_OWNER.json'), '--output-dir', str(output)], admission, owner, launch_extra,
        native_python=R / 'env/serve-reliability-r1/bin/python')
    if admission.exists(): require(all(read(admission).get(key) == value for key, value in extra.items()), 'Native launch wrote a different persistent admission')
    return result

def identities(proof, path, zero, deployment, manifest, artifacts):
    require(proof.get('passed') is True and proof.get('frozen') is True and proof.get('expected') == 2
        and proof.get('generation_requests') == 0 and proof.get('count_requests') == 2, 'Zero proof is incomplete/failed/UNKNOWN')
    require(proof['source_sha256'] == sha(B / 'probe_new_service_counter_zero18_r2.py')
        and proof['plan_sha256'] == sha(path) and proof['final_harness_wheel_sha256'] == zero['harness_wheel_sha256']
        and proof['deployment_manifest_path'] == str(deployment) and proof['deployment_manifest_sha256'] == sha(deployment), 'Zero proof source/plan/Wheel/deployment differs')
    sg = next(row for row in artifacts['rows'] if row['kind'] == 'sglang')['modules']
    require(proof['sg_source_sha256'] == sg, 'Zero proof seven SG sources differ')
    require(sha(zero['static_runtime_identity_reference_path']) == zero['static_runtime_identity_reference_sha256'], 'Independent static identity proof changed')
    reference = next(row['measurement']['service_identity'] for row in read(zero['static_runtime_identity_reference_path'])['rows'] if row['tag'] == 'new-m2-e5')
    static = set(reference) - {'service_instance_id', 'pid', 'model_path', 'served_model_name'}
    rows = proof['rows']; require(len(rows) == 2 and {row['tag'] for row in rows} == set(zero['model_tags']), 'Zero proof population differs')
    ids, processes = {}, {}
    for row in rows:
        replica = next(item for item in manifest['replicas'] if item['tag'] == row['tag'])
        measured, process = row['measurement'], row['actual_process']; identity = measured['service_identity']
        require(row.get('passed') is True and measured.get('exact') is True and measured.get('model_generation_calls') == 0
            and measured.get('context_length') == 262144 and measured.get('requested_output_tokens') == 81920
            and measured['payload_sha256'] == row['request_payload_sha256'], 'Zero measurement is invalid')
        require(all(process.get(key) == value for key, value in zero['pre_count_process_identities'][row['tag']].items())
            and type(identity['pid']) is int and identity['pid'] == process['pid'], 'Zero PID/ticks/GPU differs from frozen deployment')
        require(identity['model_path'] == replica['model_path'] and identity['served_model_name'] == replica['model_id']
            and all(identity.get(key) == reference[key] for key in static), 'Zero tokenizer/template/processor/model identity differs')
        require(row['actual_weight_version'] == replica['weight_version'] == replica['model_manifest_sha256']
            and sha(replica['model_manifest']) == replica['weight_version']
            and row['model_info']['model_path'] == replica['model_path'] and row['model_info']['weight_version'] == replica['weight_version'], 'Zero HF identity differs')
        require(row['actual_deployment_fact_path'] == replica['deployment_fact_path'] and row['actual_GPU_processes']
            and all(item['gpu_uuid'] == replica['gpu_uuid'] for item in row['actual_GPU_processes']), 'Zero GPU/deployment ownership missing')
        ids[row['tag']], processes[row['tag']] = identity, process
    require(len({item['service_instance_id'] for item in ids.values()}) == 2, 'Two independent service identities required')
    return ids, processes

def advance(owner, state, launch):
    state.update(formal_ready=False, new212_admission=False)
    require(read(C / 'NATIVE_ADVANCE_OWNER.json') == owner and owner['pid'] == os.getpid()
        and Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19] == owner['start_ticks'], 'Only the current sole controller may admit')
    index = B / 'SOURCE_RELEASE_INDEX_R2.json'; require(sha(index) == INDEX_SHA, 'Fixed six-instance source package differs')
    for item in read(index)['runtime_files']: require(sha(B / item['path']) == item['sha256'], 'Fixed runtime/template/deployment differs: ' + item['path'])
    progress = state['new_six_final5_serving'] = {}
    for pair in PAIRS:
        current = progress[pair] = {}
        try:
            folder = B / pair; manifest = read(folder / 'DEPLOYMENT_MANIFEST_R2.json')
            manifest.update(frozen=True, admitted=True, prepared_only=False)
            deployment = folder / 'DEPLOYMENT_MANIFEST_ACTUAL_R2.json'; once(deployment, manifest)
            for fact in manifest['actual_deployment_facts']: require(sha(fact['path']) == fact['sha256'], 'Actual cold receipt changed')
            zero = read(folder / 'ZERO_PLAN_TEMPLATE_R2.json'); zero.update(frozen=True, admitted=True)
            current['zero'] = admit(folder, 'ZERO', zero, deployment, owner, launch)
            proof_path = folder / 'zero-run-r1/INDEPENDENT_ZERO_GENERATION_SERVICE_PROOF_R1.json'
            if not proof_path.exists(): current['finite'] = 'WAITING_INDEPENDENT_ZERO_PROOF_NO_RETRY'; continue
            artifact_path = Path(read(folder / 'ZERO_ADMISSION_TEMPLATE_R2.json')['artifacts_manifest_path'])
            require(sha(artifact_path) == zero['artifacts_manifest_sha256'], 'Final .5 artifact changed')
            ids, processes = identities(read(proof_path), folder / 'ZERO_PLAN_ACTUAL_R2.json', zero, deployment, manifest, read(artifact_path))
            finite = read(folder / 'FINITE_PLAN_TEMPLATE_R2.json')
            require(finite['max_generation_requests'] == 6 and finite['max_generation_inflight'] == 1 and finite['retries_per_case'] == 0, 'Fixed finite scope changed')
            finite.update(frozen=True, admitted=True, counter_probe_sha256=sha(proof_path), counter_identities=ids, process_identities=processes)
            current['finite'] = admit(folder, 'FINITE', finite, deployment, owner, launch)
        except Exception as error: current.update(status='BLOCKED_UNKNOWN_NO_AUTORETRY', blocker=repr(error))
