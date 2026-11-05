"""Switch derived readers at the existing writer's ordinary sleep boundary.

No collection controller, teacher, verifier or CPU-auditor child is signalled.
The single derived-index writer is briefly stopped only after it is idle, then
resumed in finally; no second index writer is started.
"""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import time
from uuid import uuid4

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
PID=502085


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def state(proc):return next(line.split(':',1)[1].strip().split()[0] for line in (proc/'status').read_text().splitlines() if line.startswith('State:'))


def main():
    lock=(R/'checks/derived-reader-activation-r8.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    destination=R/'checks/derived-reader-activation-r8.json'
    if destination.exists():raise FileExistsError('Observe the already activated readers')
    proc=Path('/proc')/str(PID);writer=R/'scripts/audit_stream_data_worker149_r5.py'
    if str(writer).encode() not in (proc/'cmdline').read_bytes().split(b'\0'):raise ValueError('Data-writer PID identity changed')
    start_ticks=(proc/'stat').read_text().rsplit(')',1)[1].split()[19]
    accepted=R/'checks/incremental-export-r8-real-canonical-equivalence.json'
    proof=json.loads(accepted.read_text())
    if not proof['passed'] or proof['producer_sha256']!=sha(R/'scripts/export_native_canary_calls_r8.py') or proof['cache_sha256']!=sha(R/'scripts/native_export_cache_r8.py'):
        raise ValueError('Real canonical-output equivalence acceptance changed')
    for name in ['attempt-counter-r8-current-parity.json','attempt-counter-r8-boundary-acceptance.json','qualification-reader-r8-validator-acceptance.json']:
        if not json.loads((R/'checks'/name).read_text())['passed']:raise ValueError('Reader contract has not passed: '+name)
    parity=json.loads((R/'checks/attempt-counter-r8-current-parity.json').read_text())
    audit_acceptance=json.loads((R/'checks/qualification-reader-r8-validator-acceptance.json').read_text())
    if parity['new_counter_sha256']!=sha(R/'scripts/collection_attempts_r8.py') or audit_acceptance['new_audit_sha256']!=sha(R/'scripts/audit_collection_results_r8.py') or audit_acceptance['unchanged_native_validator_source_sha256']!=sha(R/'scripts/audit_collection_results_r7.py'):
        raise ValueError('Accepted counter or qualification source identity changed')
    mappings={'export_native_canary_calls.py':'export_native_canary_calls_r8.py','audit_collection_results.py':'audit_collection_results_r8.py'}
    hashes={name:sha(R/'scripts'/name) for name in [*mappings.values(),'native_export_cache_r8.py','collection_attempts_r8.py','audit_collection_results_r7.py']}
    def protected():
        active=[]
        exact={str(R/'scripts'/name).encode() for name in mappings}
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():continue
            try:
                if exact.intersection((p/'cmdline').read_bytes().split(b'\0')):active.append(int(p.name))
            except OSError:pass
        return active
    began=time.monotonic();paused=False
    try:
        while True:
            if not proc.exists() or str(writer).encode() not in (proc/'cmdline').read_bytes().split(b'\0'):
                raise RuntimeError('Original data writer exited; inspect before any activation')
            if time.monotonic()-began>7200:raise TimeoutError('Keep existing readers; no existing work is cancelled')
            if protected() or (proc/'wchan').read_text().strip()!='hrtimer_nanosleep':time.sleep(1);continue
            os.kill(PID,signal.SIGSTOP);paused=True
            deadline=time.monotonic()+1
            while state(proc) not in ['T','t'] and time.monotonic()<deadline:time.sleep(.01)
            if state(proc) not in ['T','t']:
                os.kill(PID,signal.SIGCONT);paused=False;time.sleep(1);continue
            if protected():
                os.kill(PID,signal.SIGCONT);paused=False;time.sleep(1);continue
            break
        if any(sha(R/'scripts'/name)!=digest for name,digest in hashes.items()):raise ValueError('Accepted source changed while waiting')
        before={name:dict(sha256=sha(R/'scripts'/name),symlink=os.readlink(R/'scripts'/name) if (R/'scripts'/name).is_symlink() else None) for name in mappings}
        for old,new in mappings.items():
            temporary=R/'scripts'/('.reader-r8-'+uuid4().hex)
            os.symlink(new,temporary);os.replace(temporary,R/'scripts'/old)
        value=dict(status='SAME_DATA_WRITER_NEXT_ORDINARY_SUBPROCESSES_USE_ACCEPTED_R8_READERS',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            data_writer_pid=PID,data_writer_start_ticks=start_ticks,idle_boundary='Main writer hrtimer_nanosleep, then confirmed stopped with zero protected child readers',
            previous_sources=before,new_source_sha256=hashes,canonical_entries=mappings,
            equivalence_acceptance=str(accepted),equivalence_acceptance_sha256=sha(accepted),
            source_full_sse_export_body_unchanged=True,native_structural_validator='Exact R7 function imported unchanged; existing structural cache keys retained',
            writer_only_signals=['SIGSTOP at idle boundary','SIGCONT in finally'],
            collector_teacher_verifier_or_cpu_auditor_signals=0,new_index_writers_started=0,data_writer_restarts=0,model_calls=0,
            collection_admission_budget_changed=False,old_frozen_controller_and_preparers_untouched=True)
        with destination.open('x') as stream:json.dump(value,stream,indent=2)
        print(json.dumps(value),flush=True)
    finally:
        if paused and proc.exists():os.kill(PID,signal.SIGCONT)


if __name__=='__main__':main()
