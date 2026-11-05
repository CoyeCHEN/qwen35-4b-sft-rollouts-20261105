"""Resume the original Ceph owner after R16 exited; preserve failed HF smoke."""
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C = Path('/data/chenkeyi/qwen35-sft-772-20261101/control')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def props(unit):
    return dict(line.split('=', 1) for line in subprocess.check_output(
        ['systemctl', '--user', 'show', unit, '-p', 'ActiveState', '-p', 'MainPID',
         '-p', 'LoadState', '-p', 'ExecMainStatus'], text=True).splitlines())


def identity(pid):
    return dict(pid=pid, start_ticks=(Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19])


def main():
    old = 'qwen35-772-native-advance-node18-20261102-r16.service'
    new = 'qwen35-772-native-advance-node18-20261102-r17.service'
    owner = json.loads((C / 'NATIVE_ADVANCE_OWNER.json').read_text())
    assert owner['pid'] == 3608632 and owner['start_ticks'] == '94342967'
    assert props(old)['ActiveState'] == 'failed' and props(old)['MainPID'] == '0'
    assert not (Path('/proc') / str(owner['pid'])).exists()
    assert props(new)['LoadState'] == 'not-found'
    with (C / 'unique-native-advance.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    frozen = json.loads((R / 'checks/DIAGNOSTIC30_NATIVE_LOCK_ACCEPTANCE_R2.json').read_text())
    assert all(sha(R / name) == digest for name, digest in frozen['source_sha256'].items())
    acceptance = subprocess.check_output([str(R / 'env/train-r1/bin/python'),
        str(R / 'accept-final-hf-failure-isolation-r1.py')], text=True)
    assert json.loads(acceptance)['passed']
    units = [
        'qwen35-new772-cold-new-m1-epoch3-fixed-20261101.service',
        'qwen35-new772-diag30-serving-new-m1-e5-diag-20261102-r1.service',
        'qwen35-new772-diag30-serving-new-m2-e3-diag-20261102-r1.service',
        'qwen35-new772-diag30-native-new-m1-e3-diag-20261102-r2.service',
        'qwen35-new772-diag30-native-new-m1-e5-diag-20261102-r2.service',
        'qwen35-new772-diag30-native-new-m2-e3-diag-20261102-r2.service',
    ]
    before = {unit: identity(int(props(unit)['MainPID'])) for unit in units}
    model = R / 'runs/new-m2-tmax356-128k-e5'
    job = json.loads((R / 'new-sft/workspace/jobs/new772-new-cf416-tmax356-m2/job.json').read_text())
    assert job['status'] == 'completed' and job['returncode'] == 0
    assert not (model / 'FINAL_HF_ADMISSION.json').exists()
    smokes = list((R / 'smoke').glob('native-cli-new-m2-tmax356-128k-e5-*'))
    assert len(smokes) == 1
    smoke = smokes[0]
    counts, tools = Counter(), Counter()
    for line in (smoke / 'stdout.jsonl').open():
        value = json.loads(line)
        counts[value['type']] += 1
        if value['type'] == 'tool_execution_start':
            tools[value['toolName']] += 1
    assert counts['agent_end'] == 0 and counts['tool_execution_start'] == 82
    original_log = R / 'logs/native-advance-r16.log'
    assert 'timed out after 599.' in original_log.read_text()
    proof = dict(at=time.time(), kind='FAILED_FINAL_HF_NATIVE_CLI_TIMEOUT',
        training_status='completed', native_training_returncode=0,
        model=str(model), final_hf_admitted=False, smoke=str(smoke),
        stdout_events=dict(counts), actual_tools=dict(tools),
        native_cli_timeout_seconds=600, finish_calls=tools['finish'],
        completed_agent=False, diagnosis='Actual model tool calls continued without normal closure before the smoke deadline. Not a training failure or TLS/proxy failure.',
        files={str(path): sha(path) for path in [model / 'HF_EXPORT_COMPLETE.json',
            model / 'HF_LOAD_SMOKE.json', smoke / 'stdout.jsonl', smoke / 'stderr.log',
            smoke / 'recorder/events.jsonl', smoke / 'server.log', smoke / 'SMOKE_SOURCE.json',
            original_log]}, official_reward=None,
        raw_files_unmodified=True, automatic_smoke_retry=False)
    evidence = R / 'checks/NEW_M2_FINAL_HF_NATIVE_CLI_FAILURE_R1.json'
    assert not evidence.exists()
    evidence.write_text(json.dumps(proof, indent=2) + '\n')
    blocker = C / 'HF_ADMISSION_BLOCKER_new-cf416-tmax356-m2.json'
    assert not blocker.exists()
    blocker.write_text(json.dumps(dict(at=time.time(), model=str(model),
        stage='new-cf416-tmax356-m2', error='Actual native CLI smoke timed out after 600 seconds',
        hf_export_sha256=sha(model / 'HF_EXPORT_COMPLETE.json'),
        evidence=str(evidence), evidence_sha256=sha(evidence),
        automatic_smoke_retry=False, diagnostics_continue=True), indent=2) + '\n')
    argv = ['systemd-run', '--user', '--unit=' + new, '--property=MemoryMax=192G',
        '--property=StandardOutput=append:' + str(R / 'logs/native-advance-r17.log'),
        '--property=StandardError=append:' + str(R / 'logs/native-advance-r17.log'),
        '--setenv=OMP_NUM_THREADS=2', '--setenv=HF_HUB_OFFLINE=1',
        '--setenv=TMPDIR=' + str(R / 'tmp'),
        '--setenv=TRITON_CACHE_DIR=' + str(R / 'cache/triton'),
        '--setenv=TORCH_EXTENSIONS_DIR=' + str(R / 'cache/torch-extensions'),
        str(R / 'env/train-r1/bin/python'), str(R / 'run-native772-advance-r17.py')]
    subprocess.run(argv, check=True, capture_output=True, text=True)
    for _ in range(30):
        current = props(new)
        new_owner = json.loads((C / 'NATIVE_ADVANCE_OWNER.json').read_text())
        if int(current['MainPID']) and new_owner['pid'] == int(current['MainPID']):
            break
        time.sleep(1)
    else:
        raise RuntimeError('New owner did not acquire the original Ceph lock')
    assert all(identity(value['pid']) == value for value in before.values())
    acceptance_path = R / 'checks/HF_ADMISSION_FAILURE_ISOLATION_ACCEPTANCE_R1.json'
    acceptance_path.write_text(json.dumps(dict(json.loads(acceptance),
        source_sha256={name: sha(R / name) for name in [
            'run-native772-advance-r17.py', 'accept-final-hf-failure-isolation-r1.py']},
        source_frozen_r16_unchanged=True), indent=2) + '\n')
    value = dict(passed=True, at=time.time(), old_owner=owner, new_owner=new_owner,
        old_controller_naturally_exited=True, existing_gpu_and_native_workers_unchanged=before,
        original_ceph_lock=str(C / 'unique-native-advance.lock'),
        native_hf_failure_preserved=str(evidence), native_hf_failure_sha256=sha(evidence),
        isolation_acceptance_sha256=sha(acceptance_path),
        native_job_or_trial_restarted=False, new_model_calls_by_handoff=0,
        automatic_hf_smoke_retry=False, formal801_remains_blocked=True,
        source_sha256=sha(Path(__file__)))
    out = C / 'NATIVE_ADVANCE_R17_CONTROLLED_RESUMPTION.json'
    assert not out.exists()
    out.write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps(value))


if __name__ == '__main__':
    main()
