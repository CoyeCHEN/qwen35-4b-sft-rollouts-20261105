"""One-time replacement of the CPU audit worker between subprocesses only."""
import datetime,json,os,signal,time
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
old_pid=1102818
proc=Path('/proc')/str(old_pid)
old=R/'scripts/audit_stream_data_worker149.py'
new=R/'scripts/audit_stream_data_worker149_r4.py'
py='/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
for key in ['DEEPSEEK_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
for _ in range(8640):
 if str(old).encode() not in proc.joinpath('cmdline').read_bytes().split(b'\0'):
  raise ValueError('Expected original CPU worker identity changed')
 children=proc/'task'/str(old_pid)/'children'
 if children.read_text().strip():
  time.sleep(10);continue
 os.kill(old_pid,signal.SIGSTOP)
 stopped=True
 try:
  time.sleep(.1)
  if children.read_text().strip():continue
  os.kill(old_pid,signal.SIGTERM);os.kill(old_pid,signal.SIGCONT);stopped=False
  for _ in range(100):
   if not proc.exists():break
   time.sleep(.1)
  if proc.exists():raise ValueError('Prior CPU worker did not exit; no second audit writer')
  proof=dict(status='IDLE_CPU_AUDIT_WORKER_HANDOFF',old_pid=old_pid,new_pid=os.getpid(),
   checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),native_trials_cancelled=0,
   model_calls=0,old_subprocesses_active_at_handoff=0)
  with (R/'checks/stream-r4-data-worker-handoff.json').open('x') as stream:stream.write(json.dumps(proof,indent=2))
  os.execv(py,[py,str(new)])
 finally:
  if stopped:os.kill(old_pid,signal.SIGCONT)
  time.sleep(10)
raise TimeoutError('CPU worker retained; finite idle handoff observation expired')

