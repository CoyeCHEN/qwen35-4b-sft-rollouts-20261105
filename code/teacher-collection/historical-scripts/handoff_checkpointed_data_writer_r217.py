"""Resume a read-only protocol scan from its verified per-Trial checkpoints.

Only the zero-model derived parser is interrupted. No Teacher, Verifier,
Qwen target auditor, raw artifact or official Result is changed.
"""
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
old_script=R/'scripts/audit_stream_data_worker149_r7.py'
parser_script=R/'scripts/audit_native_canary_protocol_r186.py'
new_script=R/'scripts/audit_stream_data_worker149_r9.py'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
target=R/'checks/data-writer-handoff-r217.json'
guard=(R/'checks/data-writer-handoff-r217.lock').open('a')
fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
if target.exists():raise FileExistsError('Observe existing handoff; never replay')
acceptance=R/'checks/terminal-recorder-isolation-acceptance-r218.json'
proof=json.loads(acceptance.read_text())
assert proof['passed'] and proof['unchanged_valid_parser_ast_verified'] and proof['valid_cached_rows_reused']==2
for name,expected in proof['sources'].items():assert sha(R/'scripts'/name)==expected
assert sha(old_script)=='1d841853d614633f151560dfdd1ef113c663aecc7bee5d40809464953239c829'
assert sha(parser_script)=='7a5d634045d53cf3e9d889e4b1033f61fbf1905d71d0220ff3e110899de89e01'
if (R/'checks/data-writer-handoff-r194.json').exists():raise ValueError('Another writer handoff completed; inspect actual authority')
for item in Path('/proc').iterdir():
    if not item.name.isdigit():continue
    try:
        argv=(item/'cmdline').read_bytes().split(b'\0')
        if str(R/'scripts/handoff_isolating_data_writer149_r194.py').encode() in argv:
            raise ValueError('The superseded handoff helper is still active')
    except OSError:pass
proc=Path('/proc')/str(PID)
ticks=(proc/'stat').read_text().rsplit(')',1)[1].split()[19]


def same():
    try:return str(old_script).encode() in (proc/'cmdline').read_bytes().split(b'\0') and (proc/'stat').read_text().rsplit(')',1)[1].split()[19]==ticks
    except OSError:return False


def children():
    result=[]
    for thread in (proc/'task').iterdir():
        for pid in (thread/'children').read_text().split():
            path=Path('/proc')/pid
            try:
                if (path/'stat').read_text().rsplit(')',1)[1].split()[0]!='Z':result.append(path)
            except OSError:pass
    return result


def interrupted(signum,frame):raise InterruptedError('Resume the old writer unless transfer has completed')


signal.signal(signal.SIGTERM,interrupted)
paused=False
try:
    deadline=time.monotonic()+120
    parser=None
    while True:
        if not same():raise ValueError('Old writer process changed')
        state=json.loads((R/'checks/stream-r4-data-audit-worker.json').read_text())
        owned=children()
        readonly_parser=(len(owned)==1 and str(parser_script).encode() in (owned[0]/'cmdline').read_bytes().split(b'\0'))
        idle=(not owned and (proc/'wchan').read_text().strip()=='hrtimer_nanosleep')
        if state['pid']==PID and state['pending_futures']==0 and (readonly_parser or idle):
            os.kill(PID,signal.SIGSTOP);paused=True
            state=json.loads((R/'checks/stream-r4-data-audit-worker.json').read_text());owned=children()
            if state['pending_futures']!=0:
                os.kill(PID,signal.SIGCONT);paused=False;continue
            if owned:
                if len(owned)!=1 or str(parser_script).encode() not in (owned[0]/'cmdline').read_bytes().split(b'\0'):
                    os.kill(PID,signal.SIGCONT);paused=False;continue
                parser=owned[0]
            break
        if time.monotonic()>deadline:raise TimeoutError('Keep current writer; only a zero-auditor protocol checkpoint is eligible')
        time.sleep(.2)
    cache=R/'derived/native-protocol-cache-r23'
    before={str(p):sha(p) for p in cache.glob('*/*.json')}
    intent=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),old_writer_pid=PID,
        old_parser_pid=int(parser.name) if parser else None,old_writer_source_sha256=sha(old_script),
        accepted_sources=proof['sources'],complete_immutable_checkpoint_count=len(before),
        checkpoint_set_sha256=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
        active_qwen_target_auditors=0,teacher_or_verifier_signals=0,model_calls=0,
        policy='Keep every completed cache proof; resume unfinished read-only verification with the same valid parser and per-file SHA checks')
    with (R/'checks/data-writer-handoff-intent-r217.json').open('x') as stream:json.dump(intent,stream,indent=2)
    if parser:
        os.kill(int(parser.name),signal.SIGINT)
        end=time.monotonic()+30
        while parser.exists():
            try:
                if (parser/'stat').read_text().rsplit(')',1)[1].split()[0]=='Z':break
            except OSError:break
            if time.monotonic()>end:raise TimeoutError('Read-only parser did not unwind; old writer will resume')
            time.sleep(.1)
    # The old parser stores only immutable complete per-Trial cache rows.
    # Its partial in-memory report is not an official Result or data index.
    assert all(Path(path).exists() and sha(Path(path))==digest for path,digest in before.items())
    for name,expected in proof['sources'].items():assert sha(R/'scripts'/name)==expected
    os.kill(PID,signal.SIGTERM);os.kill(PID,signal.SIGCONT);paused=False
    end=time.monotonic()+60
    while same():
        if time.monotonic()>end:raise TimeoutError('No new writer until the old process exits')
        time.sleep(.1)
    shared=(R/'derived/stream-r3-audit-worker.lock').open('a')
    while True:
        try:fcntl.flock(shared,fcntl.LOCK_EX|fcntl.LOCK_NB);break
        except BlockingIOError:
            if time.monotonic()>end:raise TimeoutError('Do not bypass an existing derived-index writer lock')
            time.sleep(.2)
    fcntl.flock(shared,fcntl.LOCK_UN);shared.close()
    py='/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
    command=shlex.join([py,str(new_script)])+' > '+shlex.quote(str(R/'logs/stream-r9-data-writer.log'))+' 2>&1'
    subprocess.run(['tmux','-L','cf-tmax-teacher-20261029','new-window','-d','-n','data-writer-r9',command],check=True)
    end=time.monotonic()+90
    while True:
        state=json.loads((R/'checks/stream-r4-data-audit-worker.json').read_text())
        if state.get('source_revision')=='r9':
            assert str(new_script).encode() in (Path('/proc')/str(state['pid'])/'cmdline').read_bytes().split(b'\0')
            break
        if time.monotonic()>end:raise TimeoutError('Inspect the started writer; never launch a duplicate')
        time.sleep(.5)
    result=dict(intent,passed=True,completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        new_writer_pid=state['pid'],new_writer_source_sha256=sha(new_script),all_existing_checkpoints_rehashed_unchanged=True,
        old_writer_exited=True,shared_writer_lock_released_before_start=True,original_results_recorders_rewards_attempts_modified=False,
        source_sha256=sha(Path(__file__)),acceptance_sha256=sha(acceptance))
    with target.open('x') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result),flush=True)
finally:
    if paused and same():os.kill(PID,signal.SIGCONT)
