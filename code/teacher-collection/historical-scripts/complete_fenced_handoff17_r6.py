"""Finish the already accepted admission fence after a pre-import exec failure."""
import fcntl
import json
import os
from pathlib import Path
import collection_readiness_r6 as n

lock = (n.R / 'checks/dispatch-handoff17-r6.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
if (n.D / 'CAMPAIGN.json').exists() or (n.R / 'checks/CURRENT_DISPATCH_AUTHORITY_R6.json').exists():
    raise FileExistsError('Dispatch authority already started; no duplicate writer')
fence = json.loads((n.R / 'checks/controller-r5-admission-fence-r6.json').read_text())
assert fence['old_native_admission_disabled']
assert n.sha(n.R / 'stream/collection-r4/DRAIN_REQUESTED.json') == fence['drain_request_sha256']
proc = Path('/proc') / str(fence['old_pid'])
assert (proc / 'stat').read_text().split()[21] == fence['old_process_start_ticks']
assert str(n.R / 'scripts/run_collection_stream_r5.py').encode() in (proc / 'cmdline').read_bytes().split(b'\0')
old = dict(x.split(b'=', 1) for x in (proc / 'environ').read_bytes().split(b'\0') if b'=' in x)
env = dict(os.environ)
env['DEEPSEEK_API_KEY'] = old[b'DEEPSEEK_API_KEY'].decode()
interpreter = '/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
n.freeze(n.R / 'checks/fenced-handoff17-preimport-exec-recovery-r6.json', dict(
    failed_launcher_pid=2765193, failure='Incorrect argv0 lost virtualenv resolution before Harbor import; zero native Trials/model calls by failed child',
    previous_fence_preserved=True, teacher_or_verifier_signals=0, recovery_pid=os.getpid(), interpreter=interpreter,
    interpreter_argv0_preserved=True, source_sha256=n.sha(Path(__file__))))
os.execve(interpreter, [interpreter, str(n.R / 'scripts/run_collection_stream_r6.py')], env)
