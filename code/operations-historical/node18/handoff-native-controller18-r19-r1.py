"""Advance independent M0 integration and preserve the predeclared score metric."""
import ast
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C = Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
E = R / 'formal-native-eval-r1'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_text())
def save(path, value):
    assert not path.exists(), path
    path.write_text(json.dumps(value, indent=2) + '\n')
def props(unit):
    return dict(line.split('=', 1) for line in subprocess.check_output(
        ['systemctl', '--user', 'show', unit, '-p', 'LoadState', '-p', 'MainPID',
         '-p', 'ActiveState'], text=True).splitlines())
def identity(pid):
    return dict(pid=pid, start_ticks=(Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19])


def main():
    old = 'qwen35-772-native-advance-node18-20261102-r18.service'
    new = 'qwen35-772-native-advance-node18-20261102-r19.service'
    owner = read(C / 'NATIVE_ADVANCE_OWNER.json')
    assert owner['pid'] == 373506 and owner['start_ticks'] == '94786541'
    assert props(old)['ActiveState'] == 'active' and props(new)['LoadState'] == 'not-found'
    assert identity(owner['pid']) == dict(pid=owner['pid'], start_ticks=owner['start_ticks'])
    release = read(R / 'checks/ADMISSION_WORKSPACE_LAYOUT_RELEASE_R1.json')
    assert all(sha(R / name) == digest for name, digest in release['source_sha256'].items())
    assert read(R / 'runs/new-m2-tmax356-128k-e5/FINAL_HF_ADMISSION.json')['passed']
    assert not (E / 'jobs/qwen35-new772-tb21-n3').exists()
    assert not (C / 'native-phase-requests/formal-n3.json').exists()
    assert props('qwen35-formal-controller18-m0-native-joint-20261102-r1.service')['LoadState'] == 'not-found'
    for tag in ['m0', 'new-m1-e5']:
        assert read(R / 'formal-protocol' / tag / 'FORMAL_PROTOCOL_ADMISSION.json')['passed']
    failed = R / 'formal-protocol/new-m2-e5'
    assert not (failed / 'FORMAL_PROTOCOL_ADMISSION.json').exists()
    assert 'timed out after 599.' in (R / 'logs/native-advance-r18.log').read_text()
    counts, tools = Counter(), Counter()
    for line in (failed / 'stdout.jsonl').open():
        value = json.loads(line)
        counts[value['type']] += 1
        if value['type'] == 'tool_execution_start': tools[value['toolName']] += 1
    save(R / 'checks/NEW_M2_EXTENDED_PROTOCOL_TIMEOUT_R1.json', dict(at=time.time(),
        extended_protocol_admitted=False, original_smoke=str(failed), events=dict(counts),
        tool_names_and_counts=dict(tools), timeout_seconds=600, official_reward=None,
        original_hf_core_multiturn_finish_remains_passed=True,
        failed_output_sha256=sha(failed / 'stdout.jsonl'),
        failed_recorder_events_sha256=sha(failed / 'recorder/events.jsonl'),
        model_commands_used_shell_write_and_read_in_first_two_tools=True,
        no_automatic_retry_or_false_extended_pass=True, model_weights_or_sampling_changed=False))
    metric_test = json.loads(subprocess.check_output([str(R / 'env/train-r1/bin/python'),
        str(R / 'accept-official-score-metric-r8-r1.py'), '--rows',
        str(E / 'checks/DIAGNOSTIC30_MATRIX_ROWS_R1.jsonl')], text=True))
    assert metric_test['passed']
    old_ast = ast.parse((R / 'phase_progression18_r13.py').read_text())
    new_ast = ast.parse((R / 'phase_progression18_r14.py').read_text())
    funcs = lambda tree: {node.name: ast.dump(node) for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name != 'formal'}
    assert funcs(old_ast) == funcs(new_ast)
    source = (R / 'phase_progression18_r14.py').read_text()
    assert source.index("assert load(joint)['passed']", source.index('def formal(')) < source.index("request_path=C/'native-phase-requests/formal-n3.json'")
    assert "proof=R/'formal-protocol'/tag/'FORMAL_PROTOCOL_ADMISSION.json';assert load(proof)['passed']" in source
    assert sha(E / 'manifests/FORMAL_801_TRIAL_PLAN.json') == 'ca38c348707a111d7583114c4f222102194e46fb6343ebe16024d7079fab4b16'
    save(R / 'checks/OFFICIAL_SCORE_METRIC_R8_ACCEPTANCE_R1.json', dict(metric_test,
        strict_r7_retained=True, all_three_extended_and_actual_m0_joint_gates_retained=True,
        diagnostic_and_old_study_functions_ast_identical=True,
        actual_formal_trials_before_correction=0,
        metric_spec_sha256=sha(E / 'manifests/METRIC_SPECIFICATIONS_R1.json')))
    names = ['phase_progression18_r14.py', 'run-native772-advance-r19.py',
        'compare-formal801-readonly-r8.py', 'accept-official-score-metric-r8-r1.py',
        'formal-native-eval-r1/scripts/compare-formal801-readonly-r8.py']
    save(R / 'checks/FORMAL_PROGRESS_AND_METRIC_RELEASE_R1.json', dict(at=time.time(),
        source_sha256={name: sha(R / name) for name in names},
        native_m0_joint_moved_after_m0_protocol_before_other_model_protocols=True,
        all_original_formal_readiness_gates_retained=True,
        scoring_matches_unchanged_preregistered_metric=True,
        raw_results_rewards_and_original_r7_outputs_unchanged=True,
        no_new_formal_task_retry_or_training_changes=True))
    units = ['qwen35-new772-cold-' + tag + '-20261101.service'
        for tag in ['m0', 'new-m1-e5', 'new-m2-e5', 'new-m1-epoch3-fixed']]
    units += ['qwen35-new772-diag30-serving-' + tag + '-20261102-r1.service'
        for tag in ['new-m1-e5-diag', 'new-m2-e3-diag']]
    units += ['qwen35-new772-diag30-native-' + tag + '-20261102-r2.service'
        for tag in ['new-m1-e3-diag', 'new-m1-e5-diag', 'new-m2-e3-diag']]
    before = {unit: identity(int(props(unit)['MainPID'])) for unit in units}
    for _ in range(60):
        base = Path('/proc') / str(owner['pid'])
        if base.joinpath('wchan').read_text().strip() in ['hrtimer_nanosleep', 'do_nanosleep'] and not base.joinpath('task', str(owner['pid']), 'children').read_text().strip(): break
        time.sleep(1)
    else: raise RuntimeError('Original controller has not reached its idle boundary')
    subprocess.run(['systemctl', '--user', 'stop', old], check=True, timeout=60)
    assert props(old)['ActiveState'] == 'inactive'
    with (C / 'unique-native-advance.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert all(identity(value['pid']) == value for value in before.values())
    argv = ['systemd-run', '--user', '--unit=' + new, '--property=MemoryMax=192G',
        '--property=StandardOutput=append:' + str(R / 'logs/native-advance-r19.log'),
        '--property=StandardError=append:' + str(R / 'logs/native-advance-r19.log'),
        '--setenv=OMP_NUM_THREADS=2', '--setenv=HF_HUB_OFFLINE=1',
        '--setenv=TMPDIR=' + str(R / 'tmp'), '--setenv=TRITON_CACHE_DIR=' + str(R / 'cache/triton'),
        '--setenv=TORCH_EXTENSIONS_DIR=' + str(R / 'cache/torch-extensions'),
        str(R / 'env/train-r1/bin/python'), str(R / 'run-native772-advance-r19.py')]
    subprocess.run(argv, check=True, capture_output=True, text=True)
    for _ in range(30):
        current = props(new)
        new_owner = read(C / 'NATIVE_ADVANCE_OWNER.json')
        if int(current['MainPID']) and new_owner['pid'] == int(current['MainPID']): break
        time.sleep(1)
    else: raise RuntimeError('R19 did not acquire original Ceph lock')
    assert all(identity(value['pid']) == value for value in before.values())
    value = dict(passed=True, at=time.time(), old_owner=owner, new_owner=new_owner,
        preserved_native_workers_and_cold_models=before, old_controller_stopped_at_idle=True,
        original_ceph_lock=str(C / 'unique-native-advance.lock'),
        release_sha256=sha(R / 'checks/FORMAL_PROGRESS_AND_METRIC_RELEASE_R1.json'),
        no_diagnostic_or_formal_task_restarted=True, no_formal_readiness_gate_waived=True,
        source_sha256=sha(Path(__file__)))
    save(C / 'NATIVE_ADVANCE_R19_CONTROLLED_HANDOFF.json', value)
    print(json.dumps(value))


if __name__ == '__main__':
    main()
