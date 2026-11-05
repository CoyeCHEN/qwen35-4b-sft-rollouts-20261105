"""One authorized empty-window handoff; refuse outstanding native lifecycles."""
import datetime,fcntl,json,os,signal,time
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
old=611441
waiter=3148531
def read(p):return json.loads(p.read_text())
def identity(pid,script):
 p=Path('/proc')/str(pid)/'cmdline'
 return p.exists() and str(R/'scripts'/script).encode() in p.read_bytes().split(b'\0')
def dead(pid):
 p=Path('/proc')/str(pid)/'status'
 return not p.exists() or any(x.startswith('State:') and 'Z' in x for x in p.read_text().splitlines())
assert identity(old,'run_collection_stream_r3.py')
assert not (R/'stream/collection-r4/CAMPAIGN.json').exists()
assert read(R/'checks/actual-teacher-slots-r5-native-contract.json')['passed']
if identity(waiter,'handoff_collection_r4_when_idle.py'):
 os.kill(waiter,signal.SIGTERM)
 for _ in range(100):
  if dead(waiter):break
  time.sleep(.05)
 assert dead(waiter),'Unpaid waiter still active; refuse another handoff'
for _ in range(300):
 state=read(R/'campaign-state.json')
 age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(state['checked_at'])).total_seconds()
 if state['pid']==old and not state['active_task_pipelines'] and age<.8:break
 time.sleep(.1)
else:raise RuntimeError('No freshly observed empty native admission window')
missing=[str(p) for p in R.glob('stream/collection-r3/dispatches/*/dispatch.json') if not (p.parents[2]/'trials'/read(p)['trial_name']/'result.json').exists()]
assert not missing,'Native Result missing; preserve and observe'
import subprocess
raw=subprocess.run(['docker','ps','-a','--format','{{.Names}} {{.Label "com.docker.compose.project"}}'],capture_output=True,text=True,check=True,timeout=10).stdout
assert not any('cftmaxstreamr320261030' in x for x in raw.splitlines()),'Original scope container still exists'
current=read(R/'campaign-state.json');assert current['pid']==old and not current['active_task_pipelines']
assert (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(current['checked_at'])).total_seconds()<2
environment={k.decode():v.decode() for part in (Path('/proc')/str(old)/'environ').read_bytes().split(b'\0') if part for k,v in [part.split(b'=',1)]}
assert environment.get('DEEPSEEK_API_KEY'),'Original authorized service environment unavailable'
record=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),old_controller_pid=old,unpaid_waiter_pid=waiter,actual_native_pipelines=[],missing_result_dispatches=[],owned_scope_containers=[],teacher_or_verifier_cancellations=0,
 boundary='Fresh empty native sleep window; SIGTERM only the idle controller; require process exit and controller lock release before exec')
os.kill(old,signal.SIGTERM)
for _ in range(200):
 if dead(old):break
 time.sleep(.05)
assert dead(old),'Old idle controller has not exited; refuse another writer'
lock=(R/'campaign-stream-controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
record.update(old_controller_exited=True,exclusive_controller_lock_verified_released=True)
p=R/'checks/controlled-idle-handoff-r5.json'
with p.open('x') as f:f.write(json.dumps(record,indent=2))
print('OLD_IDLE_CONTROLLER_EXITED_AND_EXCLUSIVE_LOCK_RELEASED',flush=True)
py='/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
os.execve(py,[py,str(R/'scripts/run_collection_stream_r5.py')],environment)
