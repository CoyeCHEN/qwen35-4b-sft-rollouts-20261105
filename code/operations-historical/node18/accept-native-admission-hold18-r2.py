"""Native queue fixture: in-flight finishes; queued work waits; verified gate resumes."""
import asyncio,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');D=R/'tmp'/('admission-hook-cpu-'+str(time.time_ns()));D.mkdir();PY=R/'env/harbor-native-eval-r1/bin/python'
child=D/'native-fixture.py';child.write_text('''import asyncio,json,os,signal,time
from pathlib import Path
from types import SimpleNamespace
from harbor.job import Job
from harbor.trial.queue import TrialQueue
from harbor.trial.hooks import TrialEvent
D=Path(__file__).parent
job=Job.__new__(Job);job._trial_queue=TrialQueue(1)
def log(kind,name):
 with(D/'trace.jsonl').open('a')as s:s.write(json.dumps(dict(at=time.time(),kind=kind,name=name))+'\\n')
async def execute(config):
 hooks=list(job._trial_queue._hooks[TrialEvent.START]);event=SimpleNamespace(trial_name=config.trial_name)
 for hook in hooks:await hook(event)
 log('environment_started',config.trial_name)
 if config.trial_name=='healthy':
  (D/'healthy-started').write_text('1');await asyncio.sleep(2)
 log('finished',config.trial_name);return None
job._trial_queue._execute_trial_with_retries=execute
async def main():
 configs=[SimpleNamespace(trial_name=n,agent=SimpleNamespace(n_concurrent=None))for n in ['healthy','queued1','queued2']]
 coros=[asyncio.create_task(job._trial_queue.submit(c))for c in configs]
 while not(D/'healthy-started').exists():await asyncio.sleep(.01)
 os.kill(os.getpid(),signal.SIGSTOP)
 await asyncio.gather(*coros)
asyncio.run(main())
''')
p=subprocess.Popen([str(PY),str(child)],stdout=(D/'stdout.log').open('w'),stderr=(D/'stderr.log').open('w'))
for _ in range(100):
 s=(Path('/proc')/str(p.pid)/'stat').read_text().rsplit(')',1)[1].split()
 if s[0]=='T':break
 time.sleep(.05)
else:raise RuntimeError('CPU fixture did not stop')
spec=dict(pid=p.pid,start_ticks=s[19],required_command_substring=str(child),hook_source=str(R/'native-trial-admission-hold-r1.py'),hook_source_sha256=hashlib.sha256((R/'native-trial-admission-hold-r1.py').read_bytes()).hexdigest(),receipt_path=str(D/'receipt.json'),gate_release_path=str(D/'release.json'),sampling_manifest_sha256='cf3e08b04fb455c3ef1c2c23a501cbf2a649328235f33f6b83cce6ff44f41858',tool_image='8cc640f05a64')
f=D/'target.json';f.write_text(json.dumps(spec));run=subprocess.run([str(PY),str(R/'inject-native-admission-hold-r2.py'),str(f)],capture_output=True,text=True,timeout=50);print(run.stdout,end='');assert run.returncode==0,run.stderr
# No new environment while the original healthy item finishes naturally.
time.sleep(3);rows=[json.loads(x)for x in(D/'trace.jsonl').read_text().splitlines()];assert any(x['kind']=='finished'and x['name']=='healthy'for x in rows);assert not any(x['kind']=='environment_started'and x['name']!='healthy'for x in rows)
synthetic=D/'CPU_ONLY_SIMULATED_MANIFEST_NOT_ENV_EVIDENCE.json';raw=json.dumps(dict(cpu_fixture_only=True,frozen=True,sampling_manifest_sha256=spec['sampling_manifest_sha256'],tasks=[dict(task_id=str(i),status='PASS')for i in range(30)])).encode();synthetic.write_bytes(raw);(D/'release.json').write_text(json.dumps(dict(scope='ENV_PREFLIGHT30',manifest_path=str(synthetic),manifest_sha256=hashlib.sha256(raw).hexdigest())))
assert p.wait(timeout=10)==0,(D/'stderr.log').read_text();rows=[json.loads(x)for x in(D/'trace.jsonl').read_text().splitlines()];assert len([x for x in rows if x['kind']=='finished'])==3
proof=dict(passed=True,at=time.time(),fixture_directory=str(D),actual_model_calls=0,actual_environment_starts=0,inflight_finished_naturally=True,queued_work_blocked_before_environment=True,resumed_after_verified_gate=True,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),hook_source_sha256=spec['hook_source_sha256'],trace=rows)
q=R/'checks/NATIVE_ADMISSION_HOLD_REAL_PROCESS_ACCEPTANCE_R2.json';assert not q.exists();q.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
