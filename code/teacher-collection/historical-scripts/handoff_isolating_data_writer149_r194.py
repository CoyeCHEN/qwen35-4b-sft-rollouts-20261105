"""Transfer the single derived-index writer only at a proved idle boundary."""
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

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
PID=3092237
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
proof_path=R/'checks/terminal-recorder-isolation-acceptance-r193.json'
target=R/'checks/data-writer-handoff-r194.json'
guard=(R/'checks/data-writer-handoff-r194.lock').open('a')
fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
if target.exists():raise FileExistsError('Inspect existing handoff; never replay')
proof=json.loads(proof_path.read_text());assert proof['passed']
for name,expected in proof['sources'].items():assert sha(R/'scripts'/name)==expected
proc=Path('/proc')/str(PID)
old=str(R/'scripts/audit_stream_data_worker149_r7.py').encode()
ticks=(proc/'stat').read_text().rsplit(')',1)[1].split()[19]


def same():
    try:return old in (proc/'cmdline').read_bytes().split(b'\0') and (proc/'stat').read_text().rsplit(')',1)[1].split()[19]==ticks
    except OSError:return False


def children():
    ids=[]
    for thread in (proc/'task').iterdir():
        ids.extend(int(x) for x in (thread/'children').read_text().split())
    return ids


paused=False
began=time.monotonic()
try:
    while True:
        if not same():raise ValueError('Old writer process identity changed')
        state=json.loads((R/'checks/stream-r4-data-audit-worker.json').read_text())
        pending=state.get('pending_futures')
        idle=state['pid']==PID and pending==0 and not children() and (proc/'wchan').read_text().strip()=='hrtimer_nanosleep'
        waiting=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),old_pid=PID,
            pending_cpu_audits=pending,old_stage=state['stage'],native_teacher_or_verifier_signals=0)
        wait_path=R/'checks/data-writer-handoff-wait-r194.json';tmp=wait_path.with_suffix('.pending')
        tmp.write_text(json.dumps(waiting,indent=2));tmp.replace(wait_path)
        if idle:
            os.kill(PID,signal.SIGSTOP);paused=True
            state=json.loads((R/'checks/stream-r4-data-audit-worker.json').read_text())
            if state['pending_futures']==0 and not children() and (proc/'stat').read_text().rsplit(')',1)[1].split()[0] in ['T','t']:break
            os.kill(PID,signal.SIGCONT);paused=False
        if time.monotonic()-began>14400:raise TimeoutError('Keep healthy writer until native idle boundary')
        time.sleep(2)
    for name,expected in proof['sources'].items():assert sha(R/'scripts'/name)==expected
    old_state_sha=sha(R/'checks/stream-r4-data-audit-worker.json')
    os.kill(PID,signal.SIGTERM);os.kill(PID,signal.SIGCONT);paused=False
    deadline=time.monotonic()+60
    while same():
        if time.monotonic()>deadline:raise TimeoutError('No new writer until old process exits')
        time.sleep(.2)
    shared=(R/'derived/stream-r3-audit-worker.lock').open('a')
    while True:
        try:fcntl.flock(shared,fcntl.LOCK_EX|fcntl.LOCK_NB);break
        except BlockingIOError:
            if time.monotonic()>deadline:raise TimeoutError('Writer lock still held; never bypass it')
            time.sleep(.2)
    fcntl.flock(shared,fcntl.LOCK_UN);shared.close()
    script=R/'scripts/audit_stream_data_worker149_r8.py'
    py='/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
    command=shlex.join([py,str(script)])+' > '+shlex.quote(str(R/'logs/stream-r8-data-writer.log'))+' 2>&1'
    subprocess.run(['tmux','-L','cf-tmax-teacher-20261029','new-window','-d','-n','data-writer-r8',command],check=True)
    deadline=time.monotonic()+90
    while True:
        state=json.loads((R/'checks/stream-r4-data-audit-worker.json').read_text())
        if state.get('source_revision')=='r8':
            assert str(script).encode() in (Path('/proc')/str(state['pid'])/'cmdline').read_bytes().split(b'\0')
            break
        if time.monotonic()>deadline:raise TimeoutError('Inspect already-started writer; never duplicate')
        time.sleep(.5)
    value=dict(passed=True,old_pid=PID,old_writer_exited=True,old_start_ticks=ticks,new_pid=state['pid'],
        source_sha256=sha(Path(__file__)),new_writer_source_sha256=sha(script),acceptance_sha256=sha(proof_path),
        old_state_sha256=old_state_sha,pending_audits_at_handoff=0,actual_shared_lock_released=True,
        teacher_controller_agent_verifier_signals=0,raw_results_recorders_rewards_attempts_modified=False,
        model_calls=0,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    with target.open('x') as stream:json.dump(value,stream,indent=2)
    print(json.dumps(value),flush=True)
finally:
    if paused and same():os.kill(PID,signal.SIGCONT)
