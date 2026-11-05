"""Switch the existing index writer at its ordinary idle boundary only."""
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
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    lock=(R/'checks/qualification-reader-r9-activation-r114.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    target=R/'checks/qualification-reader-r9-activation-r114.json'
    if target.exists():raise FileExistsError('Observe the existing reader activation')
    proof_path=R/'checks/qualification-reader-r9-acceptance-r114.json';proof=json.loads(proof_path.read_text())
    files={'audit_collection_results_r8.py':proof['old_audit_sha256'],'audit_collection_results_r9.py':proof['new_audit_sha256'],
        'reviewed_verifier_zero_r113.py':proof['review_helper_sha256'],'audit_collection_results_r7.py':proof['unchanged_native_validator_source_sha256']}
    def check():
        if not proof['passed'] or any(sha(R/'scripts'/n)!=h for n,h in files.items()):raise ValueError('Accepted qualification sources changed')
        if sha(R/'checks/COMPLETED_VERIFIER_ZERO_REVIEWS_R113.json')!=proof['review_manifest_sha256']:raise ValueError('Reviewed native evidence manifest changed')
        if (R/'scripts/audit_collection_results.py').resolve()!=R/'scripts/audit_collection_results_r8.py':raise ValueError('Another qualifier activation occurred')
        if (R/'scripts/export_native_canary_calls.py').resolve()!=R/'scripts/export_native_canary_calls_r8.py':raise ValueError('Existing exporter changed')
    proc=Path('/proc')/str(PID);writer=R/'scripts/audit_stream_data_worker149_r5.py'
    def same():
        if not proc.exists() or str(writer).encode() not in (proc/'cmdline').read_bytes().split(b'\0') or (proc/'stat').read_text().rsplit(')',1)[1].split()[19]!=ticks:
            raise ValueError('The existing data writer identity changed')
    if not proc.exists() or str(writer).encode() not in (proc/'cmdline').read_bytes().split(b'\0'):raise ValueError('Existing data writer missing')
    ticks=(proc/'stat').read_text().rsplit(')',1)[1].split()[19]
    protected_names={str(R/'scripts'/n).encode() for n in ['audit_collection_results.py','audit_collection_results_r8.py','audit_collection_results_r9.py','export_native_canary_calls.py']}
    def protected():
        result=[]
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():continue
            try:
                if protected_names.intersection((p/'cmdline').read_bytes().split(b'\0')):result.append(int(p.name))
            except OSError:pass
        return result
    check();began=time.monotonic();paused=False
    try:
        while True:
            same()
            if time.monotonic()-began>7200:raise TimeoutError('Keep current writer and qualifier; no collection interrupted')
            if protected() or (proc/'wchan').read_text().strip()!='hrtimer_nanosleep':time.sleep(1);continue
            os.kill(PID,signal.SIGSTOP);paused=True
            state=next(x.split(':',1)[1].strip().split()[0] for x in (proc/'status').read_text().splitlines() if x.startswith('State:'))
            if state not in ['T','t'] or protected():
                os.kill(PID,signal.SIGCONT);paused=False;time.sleep(1);continue
            break
        same();check()
        temporary=R/'scripts'/('.qualification-reader-r9-'+uuid4().hex)
        os.symlink('audit_collection_results_r9.py',temporary);os.replace(temporary,R/'scripts/audit_collection_results.py')
        value=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),data_writer_pid=PID,data_writer_start_ticks=ticks,
            new_qualifier='audit_collection_results_r9.py',new_qualifier_sha256=files['audit_collection_results_r9.py'],
            accepted=str(proof_path),accepted_sha256=sha(proof_path),reviewed_trials=proof['changes'],
            existing_exporter_unchanged=True,raw_results_rewards_or_records_modified=False,
            task_pool_model_prompt_tools_budget_or_attempt_counter_changed=False,
            new_index_writers_started=0,data_writer_restarts=0,
            brief_signals_to_idle_data_writer_only=['SIGSTOP','SIGCONT in finally'],
            collection_controller_teacher_verifier_or_cpu_auditor_signals=0,model_calls=0,source_sha256=sha(Path(__file__)))
        with target.open('x') as f:json.dump(value,f,indent=2)
        print(json.dumps(value),flush=True)
    finally:
        if paused and proc.exists():os.kill(PID,signal.SIGCONT)


if __name__=='__main__':main()
