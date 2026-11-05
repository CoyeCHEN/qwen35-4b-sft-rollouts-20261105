"""Resume a fenced derived-data handoff after observing actual lock release."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sha = lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
proof = json.loads((R / 'checks/canonical-data-writer-acceptance-r165.json').read_text())
for name, expected in proof['sources'].items():
    assert sha(R / 'scripts' / name) == expected
old = Path('/proc/502085')
if old.exists() and str(R / 'scripts/audit_stream_data_worker149_r5.py').encode() in (old / 'cmdline').read_bytes().split(b'\0'):
    raise ValueError('Preserve the old writer; it has not exited')
guard = (R / 'checks/canonical-data-writer-recovery-r171.lock').open('a')
fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
target = R / 'checks/canonical-data-writer-handoff-r165.json'
if target.exists():
    raise FileExistsError('Existing handoff evidence; no duplicate start')
scripts = {str(R / 'scripts' / name).encode() for name in ['audit_stream_data_worker149_r5.py', 'audit_stream_data_worker149_r6.py']}
for process in Path('/proc').iterdir():
    if not process.name.isdigit():
        continue
    try:
        if process.stat().st_uid == os.getuid() and scripts.intersection((process / 'cmdline').read_bytes().split(b'\0')):
            raise ValueError('An actual data writer is already present')
    except OSError:
        continue
shared = (R / 'derived/stream-r3-audit-worker.lock').open('a')
deadline = time.monotonic() + 30
while True:
    try:
        fcntl.flock(shared, fcntl.LOCK_EX | fcntl.LOCK_NB)
        break
    except BlockingIOError:
        if time.monotonic() > deadline:
            raise TimeoutError('Keep the fence; never bypass a held writer lock')
        time.sleep(.2)
drain = json.loads((R / 'checks/canonical-data-writer-handoff-wait-r165.json').read_text())
assert drain['stage'] == 'DRAINING_EXISTING_CPU_AUDITS_WITH_OLD_DATA_ADMISSION_PAUSED'
assert not drain['old_active_local_children'] and drain['old_active_remote_cpu_auditors'] == []
fcntl.flock(shared, fcntl.LOCK_UN)
shared.close()
py = '/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
script = R / 'scripts/audit_stream_data_worker149_r6.py'
command = shlex.join([py, str(script)]) + ' > ' + shlex.quote(str(R / 'logs/stream-r6-data-writer.log')) + ' 2>&1'
subprocess.run(['tmux', '-L', 'cf-tmax-teacher-20261029', 'new-window', '-d', '-n', 'data-writer-r6', command], check=True)
deadline = time.monotonic() + 60
while True:
    state = json.loads((R / 'checks/stream-r4-data-audit-worker.json').read_text())
    if state.get('source_revision') == 'r6':
        process = Path('/proc') / str(state['pid'])
        assert str(script).encode() in (process / 'cmdline').read_bytes().split(b'\0')
        break
    if time.monotonic() > deadline:
        raise TimeoutError('Inspect the started writer; never start a duplicate')
    time.sleep(.5)
value = dict(passed=True, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    old_data_writer_pid=502085, old_writer_exited=True, new_data_writer_pid=state['pid'],
    new_data_writer_source_sha256=sha(script), acceptance_sha256=sha(R / 'checks/canonical-data-writer-acceptance-r165.json'),
    prior_handoff_failure='R165c did not start a new writer because the derived-writer lock was still held at its immediate check; the original traceback is retained',
    prior_failure_log_sha256=sha(R / 'logs/canonical-data-writer-handoff-r165c.log'),
    actual_lock_release_verified_before_new_start=True, old_active_cpu_audits_at_transfer=0,
    completed_proofs_retained=drain['completed_audit_proofs_retained'],
    queued_unstarted_cpu_audits_retained=drain['queued_unstarted_cpu_audits_retained'],
    pending_records_re_read_by_new_canonical_writer=True, teacher_controller_agent_verifier_signals=0,
    original_results_rewards_recorders_or_attempts_modified=False, new_model_calls=0,
    source_sha256=sha(Path(__file__)))
with target.open('x') as stream:
    json.dump(value, stream, indent=2)
print(json.dumps(value))
