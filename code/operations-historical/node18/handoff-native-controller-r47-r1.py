"""Single idle handoff: keep every native Job/service; hold superseded admission."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C = Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
B = R / 'environment-preflight30'
NEW = 'qwen35-772-native-advance-node18-20261103-r47-summary-and-m1e3-cold.service'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(pid):
    return dict(pid=pid, start_ticks=(Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19])


def props(unit):
    value = subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'LoadState',
                                     '-p', 'MainPID', '-p', 'ActiveState', '-p', 'Result'], text=True, timeout=5)
    return dict(line.split('=', 1) for line in value.splitlines())


def current_masters():
    values = subprocess.check_output(['ps', '-u', str(os.getuid()), '-o', 'pid=,args='], text=True)
    result = []
    for line in values.splitlines():
        fields = line.split(None, 1)
        if len(fields) != 2:
            continue
        for slot in range(4):
            title = 'ssh: ' + str(R / '.ssh-mux-r2' / (str(slot) + '.sock')) + ' [mux]'
            if fields[1].strip() == title:
                pid = int(fields[0])
                result.append(dict(**identity(pid), slot=slot,
                                   cgroup=(Path('/proc') / str(pid) / 'cgroup').read_text().strip()))
    return result


def main(plan_sha):
    os.environ['XDG_RUNTIME_DIR'] = '/run/user/' + str(os.getuid())
    plan_path = R / 'checks/R47_SUMMARY_AND_M1E3_PROMOTION_PLAN_R1.json'
    assert sha(plan_path) == plan_sha
    plan = read(plan_path)
    owner = read(C / 'NATIVE_ADVANCE_OWNER.json')
    assert owner == plan['previous_owner']
    assert identity(owner['pid'])['start_ticks'] == owner['start_ticks']
    assert owner['pid'] == 256955 and owner['start_ticks'] == '105112999'
    old = owner['controller_unit']
    assert props(old)['ActiveState'] == 'active' and props(NEW)['LoadState'] == 'not-found'
    assert not (R / 'formal-native-eval-r1/manifests/SELECTED267_ADMISSION_R1.json').exists()
    previous = B / 'EXECUTION_RELEASE_R22.json'
    assert sha(previous) == '4bebc36ad27dc0788674b7a787d8792972c34830b0544214070e8010e9600c7f'
    sources = dict(read(previous)['source_sha256'])
    sources.update(plan['new_source_sha256'])
    sources[str(plan_path)] = plan_sha
    for name, digest in sources.items():
        assert sha(R / name) == digest, name
    assert read(R / 'reliability-repair/COMBINED_SOURCE_CPU_ACCEPTANCE_R1.json')['passed']
    prior = read(R / 'checks/NATIVE_ADVANCE_R46_HANDOFF_COMPLETED.json')
    actors = {}
    units = set(prior['actors_before'])
    units.update(row['unit'] for row in read(R / 'reliability-repair/COLD_SERVICES_LAUNCHED_R1.json')['replicas'])
    units.add('qwen35-reliability-recorder-privacy-20261103-r3.service')
    units.add('qwen35-reliability-long-ab8-native-20261103-r2.service')
    for unit in units:
        state = props(unit)
        if state['ActiveState'] == 'active':
            actors[unit] = identity(int(state['MainPID']))
    assert len(actors) >= 8
    masters = current_masters()
    assert all(old not in row['cgroup'] for row in masters), 'Detach any Job-shared master owned by the controller before stopping it'
    release = B / 'EXECUTION_RELEASE_R23.json'
    assert not release.exists()
    dropin = Path.home() / '.config/systemd/user' / (NEW + '.d') / '50-rsi-native-persistence.conf'
    assert not dropin.exists()
    dropin.parent.mkdir(parents=True, exist_ok=True)
    dropin.write_text('[Unit]\nStartLimitIntervalSec=1200\nStartLimitBurst=3\n[Service]\nRestart=on-failure\nRestartSec=20s\n')
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True, timeout=20)
    for _ in range(60):
        assert identity(owner['pid'])['start_ticks'] == owner['start_ticks']
        process = Path('/proc') / str(owner['pid'])
        if process.joinpath('wchan').read_text().strip() in ['hrtimer_nanosleep', 'do_nanosleep'] and not process.joinpath('task', str(owner['pid']), 'children').read_text().strip():
            assert current_masters() == masters
            break
        time.sleep(1)
    else:
        raise RuntimeError('Previous owner did not reach the native idle boundary; nothing stopped')
    subprocess.run(['systemctl', '--user', 'stop', old], check=True, timeout=30)
    assert props(old)['ActiveState'] == 'inactive'
    with release.open('x') as stream:
        stream.write(json.dumps(dict(at=time.time(), source_sha256=sources,
                                     previous_release_sha256=sha(previous), user_reliability_repair_admission_hold=True), indent=2) + '\n')
    log = R / 'logs/native-advance-r47-reliability.log'
    subprocess.run(['systemd-run', '--user', '--unit=' + NEW, '--property=MemoryMax=16G',
                    '--property=StandardOutput=append:' + str(log), '--property=StandardError=append:' + str(log),
                    '--setenv=PYTHONPATH=' + str(R) + ':' + str(R / 'formal-native-eval-r1/scripts'),
                    str(R / 'env/harbor-native-eval-r1/bin/python'), str(R / 'run-native772-advance-r47-summary-and-m1e3-cold.py')],
                   check=True, capture_output=True, text=True, timeout=10)
    for _ in range(30):
        current = read(C / 'NATIVE_ADVANCE_OWNER.json')
        state = props(NEW)
        if state['MainPID'] != '0' and current['pid'] == int(state['MainPID']) and current['controller_unit'] == NEW:
            break
        time.sleep(1)
    else:
        raise RuntimeError('New owner has not acquired the original lock; inspect actual units without duplicating dispatch')
    with (C / 'unique-native-advance.lock').open('r') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            raise AssertionError('New owner is not holding the shared lock')
    preserved = {}
    for unit, before in actors.items():
        if (Path('/proc') / str(before['pid'])).exists():
            assert identity(before['pid']) == before
            preserved[unit] = 'SAME_PID_AND_START_TICKS'
        else:
            actual = props(unit)
            preserved[unit] = dict(status='PROCESS_ENDED_INDEPENDENTLY_REQUIRES_NATIVE_TERMINAL_AUDIT', actual_unit=actual)
    current_master_rows = current_masters()
    for before in masters:
        if (Path('/proc') / str(before['pid'])).exists():
            assert before in current_master_rows
    value = dict(passed=True, at=time.time(), old_owner=owner, new_owner=current, same_shared_lock_held=True,
                 old_controller_inactive=True, actors_before=actors, actor_checks=preserved,
                 shared_master_handles_before=masters, shared_master_handles_after=current_master_rows,
                 source_sha256=sha(Path(__file__)), new_release_sha256=sha(release), plan_sha256=plan_sha,
                 legacy_trial_result_reward_recorder_and_job_configs_unchanged=True,
                 old_winner267_and_old_research_admission_held=True)
    target = R / 'checks/NATIVE_ADVANCE_R47_HANDOFF_COMPLETED.json'
    with target.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')
    print(json.dumps(dict(passed=True, new_owner=current, actors_preserved=len(preserved),
                          receipt_sha256=sha(target), new_release_sha256=sha(release))))


if __name__ == '__main__':
    assert len(sys.argv) == 2
    main(sys.argv[1])
