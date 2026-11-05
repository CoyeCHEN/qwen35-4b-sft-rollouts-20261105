"""Transfer the existing derived-data writer only at its zero-pending idle boundary."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
PID = 502085
proof_path = R / 'checks/canonical-data-writer-acceptance-r165.json'
target = R / 'checks/canonical-data-writer-handoff-r165.json'
sha = lambda path:hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    guard = (R / 'checks/canonical-data-writer-handoff-r165.lock').open('a')
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if target.exists():
        raise FileExistsError('Observe existing data-writer handoff; no replay')
    proof = json.loads(proof_path.read_text())
    if not proof['passed']:
        raise ValueError('Canonical data-writer acceptance did not pass')
    for name, digest in proof['sources'].items():
        if sha(R / 'scripts' / name) != digest:
            raise ValueError('Accepted data-writer source changed')
    for item in proof['cases']:
        if sha(Path(item['proof'])) != item['sha256']:
            raise ValueError('Accepted real-Trial evidence changed')
    proc = Path('/proc') / str(PID)
    old_script = str(R / 'scripts/audit_stream_data_worker149_r5.py').encode()
    ticks = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    def same():
        try:
            return old_script in (proc / 'cmdline').read_bytes().split(b'\0') and (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19] == ticks
        except FileNotFoundError:
            return False
    protected_names = {str(R / 'scripts' / name).encode() for name in [
        'merge_student_proofs.py', 'audit_collection_results.py', 'audit_collection_results_r9.py',
        'export_native_canary_calls.py', 'export_native_canary_calls_r8.py', 'audit_native_canary_protocol.py']}
    def protected():
        for process in Path('/proc').iterdir():
            if not process.name.isdigit():
                continue
            try:
                if protected_names.intersection((process / 'cmdline').read_bytes().split(b'\0')):
                    return True
            except OSError:
                continue
        return False
    began = time.monotonic()
    paused = False
    try:
        while True:
            if not same():
                raise ValueError('Existing data-writer identity changed')
            if time.monotonic() - began > 7200:
                raise TimeoutError('Keep current data writer; never interrupt active CPU audits')
            state = json.loads((R / 'checks/stream-r4-data-audit-worker.json').read_text())
            idle = state['pid'] == PID and state['pending_futures'] == 0 and (proc / 'wchan').read_text().strip() == 'hrtimer_nanosleep' and not protected()
            waiting = dict(pid=os.getpid(), checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                stage='WAITING_FOR_ZERO_PENDING_DATA_WRITER_IDLE', old_data_writer_pid=PID,
                actual_pending_cpu_audits=state['pending_futures'], old_stage=state['stage'], teacher_signals=0)
            path = R / 'checks/canonical-data-writer-handoff-wait-r165.json'
            temporary = path.with_suffix('.pending')
            temporary.write_text(json.dumps(waiting, indent=2));temporary.replace(path)
            if not idle:
                time.sleep(1);continue
            os.kill(PID, signal.SIGSTOP);paused = True
            mode = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[0]
            if mode not in ['T', 't'] or protected():
                os.kill(PID, signal.SIGCONT);paused = False;time.sleep(1);continue
            state = json.loads((R / 'checks/stream-r4-data-audit-worker.json').read_text())
            if state['pending_futures']:
                os.kill(PID, signal.SIGCONT);paused = False;time.sleep(1);continue
            break
        old_state_sha = sha(R / 'checks/stream-r4-data-audit-worker.json')
        for name, digest in proof['sources'].items():
            if sha(R / 'scripts' / name) != digest:
                raise ValueError('Accepted source changed while awaiting idle')
        # The old writer has no active auditors or child index writes here.
        os.kill(PID, signal.SIGTERM)
        os.kill(PID, signal.SIGCONT);paused = False
        deadline = time.monotonic() + 30
        while same():
            if time.monotonic() > deadline:
                raise TimeoutError('Old writer did not terminate; new writer forbidden')
            time.sleep(.1)
        shared = (R / 'derived/stream-r3-audit-worker.lock').open('a')
        fcntl.flock(shared, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(shared, fcntl.LOCK_UN);shared.close()
        py = '/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
        script = R / 'scripts/audit_stream_data_worker149_r6.py'
        command = shlex.join([py, str(script)]) + ' > ' + shlex.quote(str(R / 'logs/stream-r6-data-writer.log')) + ' 2>&1'
        subprocess.run(['tmux', '-L', 'cf-tmax-teacher-20261029', 'new-window', '-d', '-n', 'data-writer-r6', command], check=True)
        deadline = time.monotonic() + 60
        while True:
            state = json.loads((R / 'checks/stream-r4-data-audit-worker.json').read_text())
            if state.get('source_revision') == 'r6':
                new = Path('/proc') / str(state['pid'])
                if str(script).encode() not in (new / 'cmdline').read_bytes().split(b'\0'):
                    raise ValueError('New writer state has another process identity')
                break
            if time.monotonic() > deadline:
                raise TimeoutError('Inspect new writer; never launch a duplicate')
            time.sleep(.5)
        value = dict(passed=True, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            old_data_writer_pid=PID, old_data_writer_start_ticks=ticks, old_writer_exited=True,
            old_pending_cpu_audits_at_fence=0, old_state_sha256=old_state_sha,
            new_data_writer_pid=state['pid'], new_data_writer_source_sha256=sha(script),
            acceptance=str(proof_path), acceptance_sha256=sha(proof_path),
            shared_derived_writer_lock_verified_free_before_start=True,
            teacher_controller_agent_verifier_signals=0, model_calls=0,
            raw_results_rewards_or_trajectories_modified=False,
            source_sha256=sha(Path(__file__)))
        with target.open('x') as stream:
            json.dump(value, stream, indent=2)
        print(json.dumps(value), flush=True)
    finally:
        if paused and proc.exists():
            os.kill(PID, signal.SIGCONT)


if __name__ == '__main__':
    main()
