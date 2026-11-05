"""Deploy corrected local smoke layout; keep all native diagnostic jobs alive."""
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C = Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
NAMES = ['cold-hf-native-cli-smoke-r6.py', 'audit-native-cli-smoke-r4.py',
    'admit-formal-native-cli18-r2.py', 'audit-native-cli-smoke-r5.py',
    'final-hf-admission18-r5.py', 'phase_progression18_r13.py',
    'new-validation-readouts18-r3.py', 'run-native772-advance-r18.py',
    'accept-protocol-workspace-and-nll-r1.py', 'read-only-monitor18-r24.py']


def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path, value):
    assert not path.exists(), path
    path.write_text(json.dumps(value, indent=2) + '\n')


def props(unit):
    return dict(line.split('=', 1) for line in subprocess.check_output(
        ['systemctl', '--user', 'show', unit, '-p', 'LoadState', '-p', 'MainPID',
         '-p', 'ActiveState', '-p', 'Result'], text=True).splitlines())


def identity(pid):
    return dict(pid=pid, start_ticks=(Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19])


def main():
    old = 'qwen35-772-native-advance-node18-20261102-r17.service'
    new = 'qwen35-772-native-advance-node18-20261102-r18.service'
    owner = read(C / 'NATIVE_ADVANCE_OWNER.json')
    assert owner['pid'] == 2813141 and owner['start_ticks'] == '94630126'
    assert identity(owner['pid']) == dict(pid=owner['pid'], start_ticks=owner['start_ticks'])
    assert props(old)['ActiveState'] == 'active' and props(new)['LoadState'] == 'not-found'
    frozen = read(R / 'checks/DIAGNOSTIC30_NATIVE_LOCK_ACCEPTANCE_R2.json')
    assert all(sha(R / name) == digest for name, digest in frozen['source_sha256'].items())
    assert sha(R / 'runs/new-m2-tmax356-128k-e5/HF_EXPORT_COMPLETE.json') == 'c4b4c5ae2649d1de5312deda149ebdec0f08089a7ebaf99738faba1dbac16487'
    assert read(R / 'new-sft/workspace/jobs/new772-new-cf416-tmax356-m2/job.json')['returncode'] == 0
    assert not (R / 'runs/new-m2-tmax356-128k-e5/FINAL_HF_ADMISSION.json').exists()
    assert not (R / 'nll-audits/new-m2-epoch5').exists()
    for tag in ['m0', 'new-m1-e5', 'new-m2-e5']:
        assert not (R / 'formal-protocol' / tag).exists()
    failure = read(R / 'checks/NEW_M2_FINAL_HF_NATIVE_CLI_FAILURE_R1.json')
    smoke = Path(failure['smoke'])
    assert sha(smoke / 'recorder/events.jsonl') == failure['files'][str(smoke / 'recorder/events.jsonl')]
    controls = ['stdout.jsonl', 'sessions/', 'SMOKE_SOURCE.json', 'server-command.json', 'config.json']
    rows = []
    for line in (smoke / 'stdout.jsonl').open():
        value = json.loads(line)
        if value['type'] != 'tool_execution_start': continue
        text = json.dumps(value['args'])
        hits = [name for name in controls if name in text]
        if hits:
            rows.append(dict(tool_call_id=value['toolCallId'], name=value['toolName'],
                control_files=hits, arguments=text))
    assert len(rows) == 7
    feedback = dict(observed=True, at=time.time(), original_smoke=str(smoke),
        source_smoke_cwd=str(smoke), control_files_were_created_in_agent_cwd=True,
        actual_tool_calls_reading_control_artifacts=rows,
        original_events_sha256=sha(smoke / 'recorder/events.jsonl'),
        exclusive_cause_of_timeout_not_proven=True,
        actual_new_model_or_task_calls=0, raw_evidence_unmodified=True)
    save(R / 'checks/LOCAL_PROTOCOL_WORKSPACE_FEEDBACK_EVIDENCE_R1.json', feedback)
    test = json.loads(subprocess.check_output([str(R / 'env/train-r1/bin/python'),
        str(R / 'accept-protocol-workspace-and-nll-r1.py')], text=True))
    assert test['passed'] and test['actual_model_or_task_calls'] == 0
    save(R / 'checks/PROTOCOL_WORKSPACE_AND_NLL_CPU_ACCEPTANCE_R1.json', test)
    release = dict(at=time.time(), source_sha256={name: sha(R / name) for name in NAMES},
        correction='Local CLI admission uses an empty workspace; live control, server, Session and Recorder files are outside that cwd.',
        same_prompt_request_options_wheel_and_audit_assertions=True,
        official_task_attempts_or_resources_changed=False,
        old_failed_smoke_sha256=sha(R / 'checks/NEW_M2_FINAL_HF_NATIVE_CLI_FAILURE_R1.json'),
        feedback_evidence_sha256=sha(R / 'checks/LOCAL_PROTOCOL_WORKSPACE_FEEDBACK_EVIDENCE_R1.json'),
        cpu_acceptance_sha256=sha(R / 'checks/PROTOCOL_WORKSPACE_AND_NLL_CPU_ACCEPTANCE_R1.json'),
        corrected_final_hf_smoke_maximum_attempts=1, automatic_retry_after_corrected_failure=False,
        nll_requires_sealed_hf_matching_cold_load_complete_epoch5_not_agent_success=True,
        formal801_still_requires_actual_normal_hf_and_extended_protocol=True)
    save(R / 'checks/ADMISSION_WORKSPACE_LAYOUT_RELEASE_R1.json', release)
    units = ['qwen35-new772-cold-new-m1-epoch3-fixed-20261101.service',
        'qwen35-new772-diag30-serving-new-m1-e5-diag-20261102-r1.service',
        'qwen35-new772-diag30-serving-new-m2-e3-diag-20261102-r1.service',
        'qwen35-new772-diag30-native-new-m1-e3-diag-20261102-r2.service',
        'qwen35-new772-diag30-native-new-m1-e5-diag-20261102-r2.service',
        'qwen35-new772-diag30-native-new-m2-e3-diag-20261102-r2.service']
    before = {unit: identity(int(props(unit)['MainPID'])) for unit in units}
    for _ in range(60):
        base = Path('/proc') / str(owner['pid'])
        if base.joinpath('wchan').read_text().strip() in ['hrtimer_nanosleep', 'do_nanosleep'] and not base.joinpath('task', str(owner['pid']), 'children').read_text().strip():
            break
        time.sleep(1)
    else: raise RuntimeError('Wait for original native controller idle boundary; never kill its child')
    subprocess.run(['systemctl', '--user', 'stop', old], check=True, timeout=60)
    assert props(old)['ActiveState'] == 'inactive'
    with (C / 'unique-native-advance.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert all(identity(value['pid']) == value for value in before.values())
    argv = ['systemd-run', '--user', '--unit=' + new, '--property=MemoryMax=192G',
        '--property=StandardOutput=append:' + str(R / 'logs/native-advance-r18.log'),
        '--property=StandardError=append:' + str(R / 'logs/native-advance-r18.log'),
        '--setenv=OMP_NUM_THREADS=2', '--setenv=HF_HUB_OFFLINE=1',
        '--setenv=TMPDIR=' + str(R / 'tmp'), '--setenv=TRITON_CACHE_DIR=' + str(R / 'cache/triton'),
        '--setenv=TORCH_EXTENSIONS_DIR=' + str(R / 'cache/torch-extensions'),
        str(R / 'env/train-r1/bin/python'), str(R / 'run-native772-advance-r18.py')]
    subprocess.run(argv, check=True, capture_output=True, text=True)
    for _ in range(30):
        current = props(new)
        new_owner = read(C / 'NATIVE_ADVANCE_OWNER.json')
        if int(current['MainPID']) and new_owner['pid'] == int(current['MainPID']): break
        time.sleep(1)
    else: raise RuntimeError('R18 did not acquire original Ceph lock')
    assert all(identity(value['pid']) == value for value in before.values())
    value = dict(passed=True, at=time.time(), old_owner=owner, new_owner=new_owner,
        old_controller_stopped_at_idle_without_children=True,
        original_ceph_lock=str(C / 'unique-native-advance.lock'),
        healthy_native_and_model_identities_preserved=before,
        release_sha256=sha(R / 'checks/ADMISSION_WORKSPACE_LAYOUT_RELEASE_R1.json'),
        original_failed_hf_result_and_blocker_preserved=True,
        diagnostic_trial_restart_count=0, training_restart_count=0,
        source_sha256=sha(Path(__file__)))
    save(C / 'NATIVE_ADVANCE_R18_CONTROLLED_HANDOFF.json', value)
    print(json.dumps(value))


if __name__ == '__main__':
    main()
