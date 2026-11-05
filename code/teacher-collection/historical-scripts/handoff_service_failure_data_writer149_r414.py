"""Transfer the existing derived-data writer at its main-loop idle boundary, draining active CPU audits and retaining queued work."""
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
PID = 3615642
proof_path = R / 'checks/SERVICE_FAILURE_DATA_WRITER_ACCEPTANCE_R413.json'
target = R / 'checks/data-writer-handoff-r414.json'
sha = lambda path:hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    guard = (R / 'checks/data-writer-handoff-r414.lock').open('a')
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if target.exists():
        raise FileExistsError('Observe existing data-writer handoff; no replay')
    proof = json.loads(proof_path.read_text())
    if not proof['passed']:
        raise ValueError('Canonical data-writer acceptance did not pass')
    for name, digest in proof['sources'].items():
        if sha(R / 'scripts' / name) != digest:
            raise ValueError('Accepted data-writer source changed')
    for item in proof.get('cases',[]):
        if sha(Path(item['proof'])) != item['sha256']:
            raise ValueError('Accepted real-Trial evidence changed')
    if sha(R/'scripts/audit_stream_data_worker149_r12.py')!='e7c8d2b3b7338da1ce5c5a6f2a13f949807e33a675451467d52f5424ee97dde0':raise ValueError('Frozen current data writer changed')
    proc = Path('/proc') / str(PID)
    old_script = str(R / 'scripts/audit_stream_data_worker149_r12.py').encode()
    ticks = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    def same():
        try:
            return old_script in (proc / 'cmdline').read_bytes().split(b'\0') and (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19] == ticks
        except FileNotFoundError:
            return False
    protected_names = {str(R / 'scripts' / name).encode() for name in [
        'merge_student_proofs.py', 'merge_student_proofs_nfc_r368.py', 'audit_collection_results.py', 'audit_collection_results_r9.py', 'audit_collection_results_r10.py', 'audit_collection_results_r11.py', 'audit_collection_results_r13.py',
        'export_native_canary_calls.py', 'export_native_canary_calls_r8.py', 'export_native_canary_calls_r187.py', 'audit_native_canary_protocol.py', 'audit_native_canary_protocol_r186.py', 'audit_native_canary_protocol_r216.py']}
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
                raise TimeoutError('Keep current data writer until its ordinary main-loop idle boundary')
            state = json.loads((R / 'checks/stream-r4-data-audit-worker.json').read_text())
            idle = state['pid'] == PID and (proc / 'wchan').read_text().strip() == 'hrtimer_nanosleep' and not protected()
            waiting = dict(pid=os.getpid(), checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                stage='WAITING_FOR_MAIN_LOOP_IDLE_AND_NO_INDEX_CHILD_WRITER', old_data_writer_pid=PID,
                actual_pending_cpu_audits=state['pending_futures'], old_stage=state['stage'], teacher_signals=0)
            path = R / 'checks/data-writer-handoff-wait-r414.json'
            temporary = path.with_suffix('.pending')
            temporary.write_text(json.dumps(waiting, indent=2));temporary.replace(path)
            if not idle:
                time.sleep(1);continue
            os.kill(PID, signal.SIGSTOP);paused = True
            mode = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[0]
            if mode not in ['T', 't'] or protected():
                os.kill(PID, signal.SIGCONT);paused = False;time.sleep(1);continue
            state = json.loads((R / 'checks/stream-r4-data-audit-worker.json').read_text())
            break
        completed_to_replay = list(state['completed_waiting_merge'])
        queued_to_replay = list(state['queued_trial_ids'])
        active_to_drain = list(state['active_trial_ids'])
        drain_began = time.monotonic()
        def active_children():
            parents={};states={}
            for path in Path('/proc').iterdir():
                if not path.name.isdigit():continue
                try:
                    fields=(path/'stat').read_text().rsplit(')',1)[1].split()
                    parents[int(path.name)]=int(fields[1]);states[int(path.name)]=fields[0]
                except OSError:continue
            owned=[]
            for pid,mode in states.items():
                if mode=='Z':continue
                ancestor=pid
                for _ in range(8):
                    ancestor=parents.get(ancestor,0)
                    if ancestor==PID:owned.append(pid);break
                    if ancestor<=1:break
            return owned
        ssh=['ssh','-S','/home/chenkeyi/.ssh/cf17-20261028.sock','-oBatchMode=yes','-oProxyCommand=false','chenkeyi@180.163.192.17']
        node_code="""from pathlib import Path
import json,os
scripts={b'/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029/scripts/'+name for name in [b'audit_stream_data_17.py',b'audit_stream_canonical17_r163.py',b'audit_stream_nfc_canonical17_r366.py']}
found=[]
for path in Path('/proc').iterdir():
 if not path.name.isdigit():continue
 try:
  if path.stat().st_uid==os.getuid() and scripts.intersection((path/'cmdline').read_bytes().split(bytes([0]))):found.append(int(path.name))
 except OSError:continue
print(json.dumps(found))"""
        while True:
            if not same() or (proc/'stat').read_text().rsplit(')',1)[1].split()[0] not in ['T','t']:
                raise ValueError('Old data-writer admission fence was lost')
            children=active_children()
            reply=subprocess.run(ssh+[shlex.join(['python3','-c',node_code])],capture_output=True,text=True,timeout=30)
            remote=json.loads(reply.stdout) if reply.returncode==0 else None
            waiting=dict(pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                stage='DRAINING_EXISTING_CPU_AUDITS_WITH_OLD_DATA_ADMISSION_PAUSED',old_data_writer_pid=PID,
                old_active_local_children=children,old_active_remote_cpu_auditors=remote,
                queued_unstarted_cpu_audits_retained=queued_to_replay,completed_audit_proofs_retained=completed_to_replay,teacher_signals=0)
            path=R/'checks/data-writer-handoff-wait-r414.json';temporary=path.with_suffix('.pending')
            temporary.write_text(json.dumps(waiting,indent=2));temporary.replace(path)
            if not children and remote==[]:break
            if time.monotonic()-drain_began>7200:raise TimeoutError('Resume old writer; never cancel healthy CPU audits')
            time.sleep(5)
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
        lock_deadline=time.monotonic()+60
        while True:
            try:fcntl.flock(shared,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()>lock_deadline:raise TimeoutError('Preserve held writer lock; no duplicate start')
                time.sleep(.2)
        fcntl.flock(shared,fcntl.LOCK_UN);shared.close()
        py = '/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
        script = R / 'scripts/audit_stream_data_worker149_r13.py'
        command = shlex.join([py, str(script)]) + ' > ' + shlex.quote(str(R / 'logs/stream-r13-data-writer.log')) + ' 2>&1'
        subprocess.run(['tmux', '-L', 'cf-tmax-teacher-20261029', 'new-window', '-d', '-n', 'data-writer-r13', command], check=True)
        deadline = time.monotonic() + 60
        while True:
            state = json.loads((R / 'checks/stream-r4-data-audit-worker.json').read_text())
            if state.get('source_revision') == 'r13':
                new = Path('/proc') / str(state['pid'])
                if str(script).encode() not in (new / 'cmdline').read_bytes().split(b'\0'):
                    raise ValueError('New writer state has another process identity')
                break
            if time.monotonic() > deadline:
                raise TimeoutError('Inspect new writer; never launch a duplicate')
            time.sleep(.5)
        value = dict(passed=True, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            old_data_writer_pid=PID, old_data_writer_start_ticks=ticks, old_writer_exited=True,
            old_active_cpu_audits_at_transfer=0, old_queued_unstarted_cpu_audits_retained=queued_to_replay, old_initial_active_audits_drained=active_to_drain, old_completed_futures_retained=completed_to_replay,
            completed_unmerged_proofs_policy="Retain existing proof files; new canonical writer re-reads and audits pending records without a Teacher rerun", old_state_sha256=old_state_sha,
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
    def terminate(signum,frame):raise InterruptedError('Resume old writer on interrupted handoff')
    signal.signal(signal.SIGTERM,terminate)
    main()
