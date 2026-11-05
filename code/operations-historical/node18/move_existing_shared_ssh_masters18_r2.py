"""Move four existing campaign SSH masters to one native systemd scope.

No process is restarted or signalled. A failed/partial RPC is inspected and
recorded; the new scope is deliberately never stopped as a rollback.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shlex
import subprocess
import time

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C = Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
D = R / 'checks/shared-ssh-master-native-scope-r1'
SCOPE = 'qwen35-native-engine149-shared-masters18-20261103-r1.scope'
EXPECTED = {0: 3976389, 1: 3976392, 2: 3976388, 3: 3976383}
CONF = R / 'control-ssh/formal-engine149-mux-r2.conf'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, timeout=8):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def properties(unit):
    result = run(['systemctl', '--user', 'show', unit, '-p', 'LoadState', '-p', 'ActiveState',
                  '-p', 'MainPID', '-p', 'ControlGroup', '-p', 'KillMode', '-p', 'BindsTo', '-p', 'PartOf',
                  '-p', 'Requires', '-p', 'Controller'])
    assert result.returncode == 0, result.stderr
    return dict(line.split('=', 1) for line in result.stdout.splitlines())


def master(slot):
    sock = R / '.ssh-mux-r2' / (str(slot) + '.sock')
    check = run(['/usr/bin/ssh', '-F', str(CONF), '-S', str(sock), '-O', 'check',
                 '-p', '18449', 'chenkeyi@127.0.0.1'], timeout=3)
    match = re.fullmatch(r'Master running \(pid=([0-9]+)\)\n?', check.stderr)
    assert check.returncode == 0 and match, (slot, check.returncode, check.stderr)
    pid = int(match[1])
    assert pid == EXPECTED[slot], (slot, pid)
    root = Path('/proc') / str(pid)
    stat = root.joinpath('stat').read_text().rsplit(')', 1)[1].split()
    assert root.stat().st_uid == os.getuid() and stat[0] != 'Z'
    assert root.joinpath('comm').read_text().strip() == 'ssh'
    children = root.joinpath('task', str(pid), 'children').read_text().strip()
    assert not children, 'PIDs attachment is nonrecursive; do not leave children behind'
    cg = root.joinpath('cgroup').read_text().strip()
    info = sock.stat()
    return dict(slot=slot, pid=pid, start_ticks=stat[19], cgroup=cg,
                control_socket=str(sock), socket_inode=info.st_ino, socket_device=info.st_dev,
                no_children=True)


def host_io(slot):
    nonce = 'RSI_NATIVE_SCOPE_HOST_IO_SLOT_' + str(slot)
    code = 'import json,socket;print(json.dumps({"probe":' + repr(nonce) + ',"host":socket.gethostname()}))'
    result = run(['/usr/bin/ssh', '-vv', '-F', str(CONF), '-S',
                  str(R / '.ssh-mux-r2' / (str(slot) + '.sock')),
                  '-o', 'ControlMaster=no', '-p', '18449', 'chenkeyi@127.0.0.1',
                  shlex.join(['python3', '-c', code])])
    assert result.returncode == 0, (slot, result.stderr[-800:])
    value = json.loads(result.stdout)
    assert value == dict(probe=nonce, host='aibox-149'), value
    assert 'mux_client_request_session: master session id:' in result.stderr
    return dict(passed=True, host=value['host'], mux_session_confirmed=True,
                stdout_sha256=hashlib.sha256(result.stdout.encode()).hexdigest(),
                stderr_sha256=hashlib.sha256(result.stderr.encode()).hexdigest())


def main():
    os.environ['XDG_RUNTIME_DIR'] = '/run/user/' + str(os.getuid())
    assert properties(SCOPE)['LoadState'] == 'not-found'
    fixture = R / 'checks/ssh-master-scope-fixture-r1/SYSTEMD_SCOPE_CPU_LIFECYCLE_ACCEPTANCE_R1.json'
    assert sha(fixture) == '31a0fa5ae3a7f4a485c8ddaf892977e02220786640af546c2ecefec6ae9eef45'
    assert json.loads(fixture.read_text())['passed']
    owner = json.loads((C / 'NATIVE_ADVANCE_OWNER.json').read_text())
    assert owner['pid'] == 185129 and owner['start_ticks'] == '102447756'
    assert Path('/proc/185129/stat').read_text().rsplit(')', 1)[1].split()[19] == owner['start_ticks']
    D.mkdir(exist_ok=False)
    proof = dict(started_at=time.time(), passed=False, source_sha256=sha(Path(__file__)),
                 scope=SCOPE, unique_dispatch_owner=owner, model_calls=0, verifier_calls=0,
                 existing_processes_restarted=0, signals_sent=0, scope_stopped_as_rollback=False,
                 fixture_sha256=sha(fixture), ssh_config_sha256=sha(CONF))
    try:
        before = {slot: master(slot) for slot in EXPECTED}
        proof['before'] = before
        origin_units = {item['cgroup'].rsplit('/', 1)[-1] for item in before.values()}
        proof['origin_unit_properties'] = {unit: properties(unit) for unit in origin_units}
        assert all(item['KillMode'] == 'control-group' and item['ActiveState'] == 'active'
                   for item in proof['origin_unit_properties'].values())
        proof['host_io_before'] = {slot: host_io(slot) for slot in EXPECTED}
        for slot in EXPECTED:
            assert master(slot) == before[slot]
        plan = D / 'VALIDATED_PRE_MOVE_PLAN_R1.json'
        with plan.open('x') as stream:
            stream.write(json.dumps(proof, indent=2) + '\n')
        rpc = ['busctl', '--user', 'call', 'org.freedesktop.systemd1', '/org/freedesktop/systemd1',
               'org.freedesktop.systemd1.Manager', 'StartTransientUnit', 'ssa(sv)a(sa(sv))',
               SCOPE, 'fail', '3', 'Description', 's', 'RSI shared Engine149 SSH masters',
               'Slice', 's', 'app.slice', 'PIDs', 'au', '4']
        rpc += [str(before[slot]['pid']) for slot in EXPECTED] + ['0']
        result = run(rpc)
        proof['rpc'] = dict(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        # The RPC returns a queued job. Observe placement for at most five
        # seconds without replaying the RPC or opening any further SSH sessions.
        placement_started = time.monotonic()
        for _ in range(50):
            placement = {}
            for slot, pid in EXPECTED.items():
                root = Path('/proc') / str(pid)
                stat = root.joinpath('stat').read_text().rsplit(')', 1)[1].split()
                assert stat[19] == before[slot]['start_ticks']
                placement[slot] = root.joinpath('cgroup').read_text().strip()
            if all(SCOPE in value for value in placement.values()):
                break
            time.sleep(0.1)
        proof['placement_wait'] = dict(seconds=time.monotonic() - placement_started, cgroups=placement)
        # Even on a nonzero RPC, inspect every PID. Never stop the scope to undo
        # a partial attach: that would terminate already-moved live connections.
        after = {slot: master(slot) for slot in EXPECTED}
        proof['after'] = after
        for slot in EXPECTED:
            previous = dict(before[slot]); actual = dict(after[slot])
            assert SCOPE in actual.pop('cgroup')
            previous.pop('cgroup')
            assert actual == previous
        assert result.returncode == 0, result.stderr
        props = properties(SCOPE)
        assert props['ActiveState'] == 'active'
        assert not any(unit in props['BindsTo'] + ' ' + props['PartOf'] + ' ' + props['Requires']
                       for unit in origin_units)
        assert not props.get('Controller')
        proof['scope_properties'] = props
        proof['host_io_after'] = {slot: host_io(slot) for slot in EXPECTED}
        for slot in EXPECTED:
            assert master(slot) == after[slot]
        assert json.loads((C / 'NATIVE_ADVANCE_OWNER.json').read_text()) == owner
        assert sha(CONF) == proof['ssh_config_sha256']
        proof.update(passed=True, all_original_pid_ticks_and_sockets_preserved=True,
                     all_four_mux_host_sessions_confirmed=True,
                     no_existing_task_job_or_protocol_configuration_modified=True)
    except Exception as error:
        proof['error'] = repr(error)
        raise
    finally:
        # A failed call can still move some PIDs. Preserve its actual scope and
        # all surviving connections for explicit inspection; send no signals.
        observed = {}
        for slot, pid in EXPECTED.items():
            root = Path('/proc') / str(pid)
            row = dict(expected_pid=pid, unknown_fields={})
            # Raw identity/cgroup observations must not depend on responsive
            # mux IO, especially after an ambiguous or partially applied RPC.
            for field, name in [('stat', 'stat'), ('cgroup', 'cgroup'), ('comm', 'comm'),
                                ('children', 'task/' + str(pid) + '/children')]:
                try:
                    value = root.joinpath(name).read_text().strip()
                    if field == 'stat':
                        parts = value.rsplit(')', 1)[1].split()
                        row.update(actual_start_ticks=parts[19], actual_state=parts[0])
                    else:
                        row[field] = value
                except Exception as error:
                    row['unknown_fields'][field] = repr(error)
            try:
                row['actual_uid'] = root.stat().st_uid
            except Exception as error:
                row['unknown_fields']['uid'] = repr(error)
            try:
                sock = (R / '.ssh-mux-r2' / (str(slot) + '.sock')).stat()
                row.update(actual_socket_inode=sock.st_ino, actual_socket_device=sock.st_dev)
            except Exception as error:
                row['unknown_fields']['socket'] = repr(error)
            try:
                row['mux_identity_check'] = master(slot)
            except Exception as error:
                row['mux_identity_check'] = dict(error=repr(error))
            observed[slot] = row
        proof.update(finished_at=time.time(), actual_final_master_observations=observed)
        target = D / 'SSH_MASTER_NATIVE_SCOPE_OWNERSHIP_ACCEPTANCE_R1.json'
        with target.open('x') as stream:
            stream.write(json.dumps(proof, indent=2) + '\n')
        print(json.dumps(dict(passed=proof['passed'], evidence_path=str(target), sha256=sha(target))), flush=True)


if __name__ == '__main__':
    main()
