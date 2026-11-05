"""Idle handoff and one project-key activation; preserve all native workloads."""
import argparse
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C = Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
B = R / 'environment-preflight30'
E = R / 'formal-native-eval-r1'
ACTIVATOR = '/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/scripts/activate-old112-selected267-qualified-project-key149-r1.py'
REMOTE_PYTHON = '/home/chenkeyi/.local/share/harbor-rsi/qwen35-old-m2-four-arm-20261101/env/harbor-native-boundary-r1/bin/python'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')


def props(unit):
    output = subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'LoadState',
                                      '-p', 'MainPID', '-p', 'ActiveState', '-p', 'Result'],
                                     text=True, timeout=5)
    return dict(line.split('=', 1) for line in output.splitlines())


def ident(pid):
    return dict(pid=pid, start_ticks=(Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19])


def remote_key(activate):
    args = [REMOTE_PYTHON, ACTIVATOR] + (['--activate'] if activate else [])
    process = subprocess.run(['/usr/bin/ssh', '-F', str(R / 'control-ssh/formal-engine149-r1.conf'),
                              '127.0.0.1', shlex.join(args)],
                             check=True, capture_output=True, text=True, timeout=20)
    proof = json.loads(process.stdout)
    assert proof['passed'] and proof['other_keys_unchanged']
    assert proof['source_sha256'] == 'c4c735f81500db21e7023f4f3fdf01a1b1e0c2f96cca58dfd3e4b66d13924f62'
    assert proof['authorized_keys_before_sha256'] == '1c5983091b87c9efb9d4454ce7ac9dd3505e257c9a44dc323daf23f7a3938e92'
    assert proof['authorized_keys_after_sha256'] == '95369736dc875506453ac88b5cc90b449f1e07284406b1c93d99b8a87073297a'
    assert proof['other_keys_sha256'] == '4345ea16eaa019689642cd301b007cd21bdae307ab8c5e5de1b5833418c5847b'
    assert proof.get('activated') is True if activate else proof.get('check_only') is True
    return proof


def main(expected_plan_sha):
    os.environ['XDG_RUNTIME_DIR'] = '/run/user/' + str(os.getuid())
    plan_path = R / 'checks/R41_QUALIFIED_READOUT_PROMOTION_PLAN_R1.json'
    assert sha(plan_path) == expected_plan_sha
    plan = read(plan_path)
    owner = read(C / 'NATIVE_ADVANCE_OWNER.json')
    assert owner == plan['previous_owner'] and owner['pid'] == 185129 and owner['start_ticks'] == '102447756'
    old = owner['controller_unit']
    new = 'qwen35-772-native-advance-node18-20261103-r41-env-repair.service'
    assert old == 'qwen35-772-native-advance-node18-20261103-r40-env-repair.service'
    assert props(old)['ActiveState'] == 'active' and props(new)['LoadState'] == 'not-found'
    assert not (E / 'manifests/SELECTED267_ADMISSION_R1.json').exists()
    assert not (R / 'checks/WINNER_FROM_COMMON30_SELECTION_R1.json').exists()
    previous = B / 'EXECUTION_RELEASE_R16.json'
    assert sha(previous) == '2bef12deeb75a6ea3f32a35ac9aab9b19ce16b09885692403cc9e8291b24679f'
    source = dict(read(previous)['source_sha256'])
    source.update(plan['new_source_sha256'])
    source[str(plan_path)] = sha(plan_path)
    for name, digest in source.items():
        assert sha(R / name) == digest, name
    accepted = read(R / 'checks/REAL_R41_QUALIFIED_CONTROL_BINDING_ACCEPTANCE_R1.json')
    assert accepted['passed'] and accepted['actual_model_verifier_container_calls'] == 0
    assert accepted['original_native_execution_AST_unchanged'] and accepted['old_rsi2_and_pipeline_NOP_receipts_unchanged']
    precheck = remote_key(False)
    sys.path[:0] = [str(R), str(E / 'scripts')]
    winner = importlib.import_module('winner267-phase18-r16')
    assert winner.native_boundary_runtime_gate()['passed']
    cfg = read(R / 'configs/diagnostic150-five-model-r1.json')
    units = [item['replica']['unit'] for item in winner.current_roles(cfg).values()]
    units += ['qwen35-accepted30-' + item['tag'] + '-20261102-r4.service' for item in cfg['models']]
    units += ['qwen35-accepted30-disk-recovery-new-m2-e1-20261102-r2.service',
              'qwen35-accepted30-disk-recovery-new-m1-e3-20261102-r3.service',
              'qwen35-accepted30-disk-recovery-new-m1-e5-20261102-r3.service']
    before = {}
    for unit in units:
        status = props(unit)
        if status['ActiveState'] == 'active':
            before[unit] = dict(identity=ident(int(status['MainPID'])), properties=status)
    assert len(before) >= 8
    master_proof = read(R / 'checks/shared-ssh-master-native-scope-r1/SSH_MASTER_NATIVE_SCOPE_OWNERSHIP_ACCEPTANCE_R1.json')
    for item in master_proof['after'].values():
        assert ident(item['pid'])['start_ticks'] == item['start_ticks']
        assert master_proof['scope'] in (Path('/proc') / str(item['pid']) / 'cgroup').read_text()
    release = B / 'EXECUTION_RELEASE_R17.json'
    dropin = Path.home() / '.config/systemd/user' / (new + '.d') / '50-rsi-native-persistence.conf'
    assert not release.exists() and not dropin.exists()
    dropin.parent.mkdir(parents=True, exist_ok=True)
    dropin.write_text('[Unit]\nStartLimitIntervalSec=1200\nStartLimitBurst=3\n'
                      '[Service]\nRestart=on-failure\nRestartSec=20s\n')
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True, timeout=20)
    reader = E / 'scripts/read-diagnostic150-matrix18-r6.py'
    for _ in range(60):
        assert ident(owner['pid'])['start_ticks'] == owner['start_ticks']
        cpu_writers = winner.reader_writers(reader)
        verified = len(cpu_writers) <= 1 and all(row['verified'] for row in cpu_writers)
        process = Path('/proc') / str(owner['pid'])
        idle = process.joinpath('wchan').read_text().strip() in ['hrtimer_nanosleep', 'do_nanosleep']
        no_children = not process.joinpath('task', str(owner['pid']), 'children').read_text().strip()
        if idle and no_children and verified:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Previous controller is not idle or CPU writer identity is unverified')
    subprocess.run(['systemctl', '--user', 'stop', old], check=True, timeout=30)
    assert props(old)['ActiveState'] == 'inactive'
    activation = remote_key(True)
    activation_path = R / 'checks/PROJECT_KEY_NATIVE_R15_ACTIVATION_ACCEPTANCE_R1.json'
    save(activation_path, activation)
    source[str(activation_path)] = sha(activation_path)
    save(release, dict(at=time.time(), source_sha256=source, previous_release_sha256=sha(previous),
                       promotion_plan_sha256=sha(plan_path), project_key_activation_sha256=sha(activation_path),
                       original_trials_rewards_recorders_protocol_and_workers_unchanged=True,
                       selected267_and_all_old_readout_consumers_require_host_qualification=True))
    log = R / 'logs/native-advance-r41.log'
    subprocess.run(['systemd-run', '--user', '--unit=' + new, '--property=MemoryMax=16G',
                    '--property=StandardOutput=append:' + str(log), '--property=StandardError=append:' + str(log),
                    '--setenv=PYTHONPATH=' + str(R) + ':' + str(E / 'scripts'),
                    str(R / 'env/harbor-native-eval-r1/bin/python'),
                    str(R / 'run-native772-advance-r41-env-repair.py')],
                   check=True, capture_output=True, text=True, timeout=10)
    for _ in range(30):
        current = read(C / 'NATIVE_ADVANCE_OWNER.json')
        status = props(new)
        if status['MainPID'] != '0' and current['pid'] == int(status['MainPID']) and current['deployment_revision'] == 'r41-selected267-qualified-readout-and-strong-completion':
            break
        time.sleep(1)
    else:
        raise RuntimeError('New controller did not acquire the same shared lock')
    with (C / 'unique-native-advance.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            raise AssertionError('New owner does not hold the shared lock')
    deployed = importlib.import_module('freeze-old-readout-selected267-deployment18-r4').freeze(current)
    assert deployed['actual_remote_deployment_proof']['passed']
    preserved = {}
    for unit, record in before.items():
        if (Path('/proc') / str(record['identity']['pid'])).exists():
            assert ident(record['identity']['pid']) == record['identity']
            preserved[unit] = 'ORIGINAL_PID_AND_TICKS_PRESERVED'
        else:
            status = props(unit)
            assert status['ActiveState'] == 'inactive' and status['Result'] == 'success'
            preserved[unit] = 'NATIVE_PROCESS_COMPLETED_DURING_HANDOFF'
    for item in master_proof['after'].values():
        assert ident(item['pid'])['start_ticks'] == item['start_ticks']
        assert master_proof['scope'] in (Path('/proc') / str(item['pid']) / 'cgroup').read_text()
    result = dict(passed=True, at=time.time(), old_owner=owner, new_owner=current,
                  previous_controller_inactive=True, same_shared_lock_held=True,
                  healthy_native_workers_and_model_services=before, preservation_checks=preserved,
                  original_four_shared_masters_preserved=True, existing_verified_cpu_writers_retained=cpu_writers,
                  project_key_precheck=precheck, activation_receipt_sha256=sha(activation_path),
                  old_readout_release_r4_sha256=sha(R / 'checks/OLD_READOUT_SELECTED267_RELEASE_R4.json'),
                  promotion_plan_sha256=sha(plan_path), new_release_sha256=sha(release), source_sha256=sha(Path(__file__)))
    target = R / 'checks/NATIVE_ADVANCE_R41_HANDOFF_COMPLETED.json'
    save(target, result)
    print(json.dumps(dict(passed=True, new_owner=current, preserved=len(preserved),
                          new_release_sha256=sha(release), old_readout_release_r4_sha256=result['old_readout_release_r4_sha256'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan-sha256', required=True)
    main(parser.parse_args().plan_sha256)
