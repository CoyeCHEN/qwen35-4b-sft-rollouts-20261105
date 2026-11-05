"""Idle handoff of the existing Ceph-locked owner; retain every native worker."""
import argparse
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C = Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
B = R / 'environment-preflight30'
E = R / 'formal-native-eval-r1'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')


def props(unit):
    text = subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'LoadState',
                                    '-p', 'MainPID', '-p', 'ActiveState', '-p', 'Result'],
                                   text=True, timeout=5)
    return dict(line.split('=', 1) for line in text.splitlines())


def ident(pid):
    return dict(pid=pid, start_ticks=(Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19])


def main(expected_plan_sha):
    os.environ['XDG_RUNTIME_DIR'] = '/run/user/' + str(os.getuid())
    plan_path = R / 'checks/R40_HOST_TRANSPORT_SCORING_PROMOTION_PLAN_R1.json'
    assert sha(plan_path) == expected_plan_sha
    plan = read(plan_path)
    owner = read(C / 'NATIVE_ADVANCE_OWNER.json')
    assert owner == plan['previous_owner']
    assert owner['pid'] == 4113845 and owner['start_ticks'] == '100553203'
    old = owner['controller_unit']
    new = 'qwen35-772-native-advance-node18-20261103-r40-env-repair.service'
    assert old == 'qwen35-772-native-advance-node18-20261103-r39-env-repair.service'
    assert props(old)['ActiveState'] == 'active' and props(new)['LoadState'] == 'not-found'
    assert not (R / 'checks/WINNER_FROM_COMMON30_SELECTION_R1.json').exists()
    previous = B / 'EXECUTION_RELEASE_R15.json'
    assert sha(previous) == 'a43ffcece92aab8f281a1509b18be9c791ae43f388494d8018c9863ba5dcf65e'
    source = dict(read(previous)['source_sha256'])
    source.update(plan['new_source_sha256'])
    source[str(plan_path)] = sha(plan_path)
    for name, digest in source.items():
        assert sha(R / name) == digest, name
    proof = read(R / 'checks/REAL_R40_FINITE_BINDING_ACCEPTANCE_R1.json')
    assert proof['passed'] and proof['model_or_verifier_dispatches'] == 0
    assert proof['derived_files_written_by_cached_reader'] == 0
    assert proof['reader_sha256'] == sha(E / 'scripts/read-diagnostic150-matrix18-r6.py')
    sys.path[:0] = [str(R), str(E / 'scripts')]
    winner = importlib.import_module('winner267-phase18-r15')
    cfg = read(R / 'configs/diagnostic150-five-model-r1.json')
    units = [value['replica']['unit'] for value in winner.current_roles(cfg).values()]
    units += ['qwen35-accepted30-' + model['tag'] + '-20261102-r4.service' for model in cfg['models']]
    units += ['qwen35-accepted30-disk-recovery-new-m2-e1-20261102-r2.service',
              'qwen35-accepted30-disk-recovery-new-m1-e3-20261102-r3.service',
              'qwen35-accepted30-disk-recovery-new-m1-e5-20261102-r3.service']
    before = {}
    for unit in units:
        state = props(unit)
        if state['ActiveState'] == 'active':
            before[unit] = dict(identity=ident(int(state['MainPID'])), properties=state)
    assert len(before) >= 8
    release = B / 'EXECUTION_RELEASE_R16.json'
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
        one_verified_cpu_writer = len(cpu_writers) <= 1 and all(row['verified'] for row in cpu_writers)
        process = Path('/proc') / str(owner['pid'])
        idle = process.joinpath('wchan').read_text().strip() in ['hrtimer_nanosleep', 'do_nanosleep']
        no_children = not process.joinpath('task', str(owner['pid']), 'children').read_text().strip()
        if idle and no_children and one_verified_cpu_writer:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Existing controller is not idle or the CPU writer identity is unverified')
    subprocess.run(['systemctl', '--user', 'stop', old], check=True, timeout=30)
    assert props(old)['ActiveState'] == 'inactive'
    save(release, dict(at=time.time(), source_sha256=source,
                       previous_release_sha256=sha(previous), promotion_plan_sha256=sha(plan_path),
                       only_derived_host_transport_qualification_changed=True,
                       original_trials_rewards_recorders_protocol_and_workers_unchanged=True,
                       single_shared_lock_and_original_native_queue=True))
    log = R / 'logs/native-advance-r40.log'
    subprocess.run(['systemd-run', '--user', '--unit=' + new, '--property=MemoryMax=16G',
                    '--property=StandardOutput=append:' + str(log), '--property=StandardError=append:' + str(log),
                    '--setenv=PYTHONPATH=' + str(R) + ':' + str(E / 'scripts'),
                    str(R / 'env/harbor-native-eval-r1/bin/python'),
                    str(R / 'run-native772-advance-r40-env-repair.py')],
                   check=True, capture_output=True, text=True, timeout=10)
    for _ in range(30):
        current = read(C / 'NATIVE_ADVANCE_OWNER.json')
        state = props(new)
        if state['MainPID'] != '0' and current['pid'] == int(state['MainPID']) and current['deployment_revision'] == 'r40-host-docker-transport-scoring-qualification':
            break
        time.sleep(1)
    else:
        raise RuntimeError('New owner did not acquire the existing shared lock')
    with (C / 'unique-native-advance.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            raise AssertionError('New owner does not hold the shared lock')
    preserved = {}
    for unit, row in before.items():
        if (Path('/proc') / str(row['identity']['pid'])).exists():
            assert ident(row['identity']['pid']) == row['identity']
            preserved[unit] = 'ORIGINAL_PID_AND_TICKS_PRESERVED'
        else:
            state = props(unit)
            assert state['ActiveState'] == 'inactive' and state['Result'] == 'success'
            preserved[unit] = 'NATIVE_PROCESS_COMPLETED_DURING_HANDOFF'
    result = dict(passed=True, at=time.time(), old_owner=owner, new_owner=current,
                  new_release_sha256=sha(release), promotion_plan_sha256=sha(plan_path),
                  same_shared_lock_held=True, old_controller_inactive=True,
                  healthy_native_workers_and_model_services=before, preservation_checks=preserved,
                  existing_verified_cpu_writers_retained=cpu_writers,
                  source_sha256=sha(Path(__file__)))
    save(R / 'checks/NATIVE_ADVANCE_R40_HANDOFF_COMPLETED.json', result)
    print(json.dumps(dict(passed=True, new_owner=current, preserved=len(preserved),
                          new_release_sha256=sha(release))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan-sha256', required=True)
    main(parser.parse_args().plan_sha256)
