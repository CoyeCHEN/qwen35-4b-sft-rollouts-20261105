"""One-time idle handoff; no native Trial is cancelled or replayed."""
import datetime,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
old_pid=611441
old_script=R/'scripts/run_collection_stream_r3.py'
new_script=R/'scripts/run_collection_stream_r4.py'
py='/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def save(status,**kwargs):
 p=R/'checks/collection-r4-idle-handoff.json';tmp=p.with_suffix('.tmp')
 tmp.write_text(json.dumps(dict(status=status,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
  old_pid=old_pid,handoff_pid=os.getpid(),active_trial_cancellations=0,teacher_dispatches_by_waiter=0,**kwargs),indent=2));tmp.replace(p)
ready=read(R/'checks/collection-r4-promotion-ready.json')
if not ready['passed']:raise ValueError('Native/offline acceptance is incomplete')
sources=ready['frozen_source_sha256']
def validate():
 for name,expected in sources.items():
  if sha(R/name)!=expected:raise ValueError('Accepted handoff source changed: '+name)
def outstanding():
 return [str(p) for p in R.glob('stream/collection-r3/dispatches/*/dispatch.json')
  if not (p.parents[2]/'trials'/read(p)['trial_name']/'result.json').exists()]
def old_identity():
 return str(old_script).encode() in (Path('/proc')/str(old_pid)/'cmdline').read_bytes().split(b'\0')
validate()
for turn in range(8640):  # Bounded24h observation of the unchanged controller.
 if not old_identity():raise ValueError('Expected old controller identity changed; do not start another writer')
 state=read(R/'campaign-state.json')
 if state['pid']!=old_pid:raise ValueError('Another controller owns the campaign')
 if state['active_task_pipelines'] or outstanding():
  save('WAITING_FOR_EXISTING_NATIVE_LIFECYCLES',active_task_pipelines=state['active_task_pipelines'])
  time.sleep(10);continue
 # Freeze the idle parent only while validating the boundary. Container agent
 # processes are never signalled. If a new native dispatch raced, resume it.
 os.kill(old_pid,signal.SIGSTOP)
 stopped=False
 try:
  time.sleep(.1)
  for line in (Path('/proc')/str(old_pid)/'status').read_text().splitlines():
   if line.startswith('State:'):stopped='T' in line
  state=read(R/'campaign-state.json')
  if not stopped or state['active_task_pipelines'] or outstanding():
   continue
  containers=subprocess.run(['docker','ps','-a','--format','{{.Names}} {{.Label "com.docker.compose.project"}}'],
   capture_output=True,text=True,check=True,timeout=30).stdout
  owned=[line for line in containers.splitlines() if 'cftmaxstreamr320261030' in line]
  if owned:
   save('WAITING_FOR_ORIGINAL_NATIVE_CLEANUP',remaining_container_count=len(owned))
   continue
  validate()
  # Preserve private authorized service semantics in memory only. Do not write
  # values, print environment or pass credentials as command arguments.
  raw=(Path('/proc')/str(old_pid)/'environ').read_bytes().split(b'\0')
  environment={k.decode():v.decode() for item in raw if item for k,v in [item.split(b'=',1)]}
  if not environment.get('DEEPSEEK_API_KEY'):raise ValueError('Original authorized service environment is absent')
  frozen=R/'checks/collection-r3-idle-final-state.json'
  with frozen.open('x') as stream:stream.write(json.dumps(state,indent=2))
  os.kill(old_pid,signal.SIGTERM);os.kill(old_pid,signal.SIGCONT);stopped=False
  for _ in range(100):
   if not (Path('/proc')/str(old_pid)).exists():break
   time.sleep(.1)
  if (Path('/proc')/str(old_pid)).exists():raise ValueError('Old controller has not exited; refuse another writer')
  save('IDLE_HANDOFF_EXECUTING_ACCEPTED_R4',old_controller_exited=True)
  log=os.open(R/'logs/campaign-stream-r4.log',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
  os.dup2(log,1);os.dup2(log,2);os.close(log)
  os.execve(py,[py,str(new_script)],environment)
 finally:
  if stopped:os.kill(old_pid,signal.SIGCONT)
  time.sleep(10)
save('BOUNDED_IDLE_OBSERVATION_EXPIRED_OLD_CONTROLLER_RETAINED')

