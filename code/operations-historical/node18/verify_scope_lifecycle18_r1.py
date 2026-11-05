"""Finite CPU-only acceptance of native systemd scope process ownership."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
D = R / 'checks/ssh-master-scope-fixture-r1'
ORIGIN = 'qwen35-ssh-scope-fixture-origin-20261103-r1.service'
SCOPE = 'qwen35-ssh-scope-fixture-child-20261103-r1.scope'


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=8)


def properties(unit):
    result = run(['systemctl', '--user', 'show', unit, '-p', 'LoadState', '-p', 'ActiveState', '-p', 'ControlGroup'])
    return dict(line.split('=', 1) for line in result.stdout.splitlines())


def identity(pid):
    root = Path('/proc') / str(pid)
    if not root.exists():
        return None
    fields = root.joinpath('stat').read_text().rsplit(')', 1)[1].split()
    return dict(pid=pid, start_ticks=fields[19], state=fields[0], cgroup=root.joinpath('cgroup').read_text().strip())


def main():
    os.environ['XDG_RUNTIME_DIR'] = '/run/user/' + str(os.getuid())
    assert properties(ORIGIN)['LoadState'] == 'not-found'
    assert properties(SCOPE)['LoadState'] == 'not-found'
    D.mkdir(exist_ok=False)
    proof = dict(started_at=time.time(), passed=False, actual_model_calls=0,
                 actual_verifier_calls=0, actual_trials_changed=0,
                 source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    created_origin = False
    try:
        code = ("import json,subprocess,time;from pathlib import Path;"
                "a=subprocess.Popen(['/bin/sleep','90']);b=subprocess.Popen(['/bin/sleep','90']);"
                "Path(" + repr(str(D / 'children.json')) + ").write_text(json.dumps({'moved':a.pid,'unmoved':b.pid}));"
                "time.sleep(55)")
        run(['systemd-run', '--user', '--unit=' + ORIGIN, '--property=KillMode=control-group',
             '--property=RuntimeMaxSec=60s', '/usr/bin/python3', '-c', code])
        created_origin = True
        for _ in range(50):
            if (D / 'children.json').exists():
                break
            time.sleep(0.1)
        ids = json.loads((D / 'children.json').read_text())
        before = {name: identity(pid) for name, pid in ids.items()}
        assert all(value is not None and ORIGIN in value['cgroup'] for value in before.values())
        proof.update(children_before=before, origin_properties=properties(ORIGIN))
        rpc = ['busctl', '--user', 'call', 'org.freedesktop.systemd1', '/org/freedesktop/systemd1',
               'org.freedesktop.systemd1.Manager', 'StartTransientUnit', 'ssa(sv)a(sa(sv))',
               SCOPE, 'fail', '3', 'Description', 's', 'RSI finite CPU scope ownership acceptance',
               'Slice', 's', 'app.slice', 'PIDs', 'au', '1', str(ids['moved']), '0']
        proof['scope_rpc_reply'] = run(rpc).stdout.strip()
        for _ in range(50):
            moved = identity(ids['moved'])
            if moved and SCOPE in moved['cgroup']:
                break
            time.sleep(0.1)
        assert moved and moved['start_ticks'] == before['moved']['start_ticks'] and SCOPE in moved['cgroup']
        proof['scope_properties'] = properties(SCOPE)
        run(['systemctl', '--user', 'stop', ORIGIN])
        after = {name: identity(pid) for name, pid in ids.items()}
        assert after['moved'] and after['moved']['start_ticks'] == before['moved']['start_ticks']
        assert after['moved']['state'] != 'Z' and SCOPE in after['moved']['cgroup']
        assert after['unmoved'] is None or after['unmoved']['state'] == 'Z'
        proof.update(children_after_origin_stopped=after, moved_child_survived_origin_stop=True,
                     unmoved_child_ended_with_origin=True)
        run(['systemctl', '--user', 'stop', SCOPE])
        final = identity(ids['moved'])
        assert final is None or final['state'] == 'Z'
        proof.update(owned_scope_cleanup_confirmed=True, passed=True)
    except Exception as error:
        proof['error'] = repr(error)
        raise
    finally:
        # Only the two uniquely named CPU-fixture units are eligible for cleanup.
        cleanup = []
        for unit in ([ORIGIN, SCOPE] if created_origin else []):
            state = properties(unit)
            if state['LoadState'] != 'not-found' and state['ActiveState'] not in ['inactive', 'failed']:
                run(['systemctl', '--user', 'stop', unit])
            cleanup.append(dict(unit=unit, properties=properties(unit)))
        proof.update(finished_at=time.time(), cleanup=cleanup)
        target = D / 'SYSTEMD_SCOPE_CPU_LIFECYCLE_ACCEPTANCE_R1.json'
        with target.open('x') as stream:
            stream.write(json.dumps(proof, indent=2) + '\n')
        print(json.dumps(dict(passed=proof['passed'], evidence_path=str(target),
                              sha256=hashlib.sha256(target.read_bytes()).hexdigest())), flush=True)


if __name__ == '__main__':
    main()
