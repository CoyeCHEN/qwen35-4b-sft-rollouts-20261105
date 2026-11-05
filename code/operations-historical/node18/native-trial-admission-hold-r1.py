"""Install only a native Job START hook; existing Trial instances keep their hooks."""
import asyncio,gc,hashlib,json,os,time
from pathlib import Path
try:
 spec=json.loads(Path(PAUSE_SPEC).read_text())
 assert os.getpid()==spec['pid']and Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]==spec['start_ticks']
 assert hashlib.sha256(Path(spec['hook_source']).read_bytes()).hexdigest()==spec['hook_source_sha256']
 from harbor.job import Job
 jobs=[v for v in gc.get_objects()if type(v)is Job];assert len(jobs)==1
 job=jobs[0];before=len(job._trial_queue._hooks[__import__('harbor.trial.hooks',fromlist=['TrialEvent']).TrialEvent.START])
 async def hold_new_trial(event):
  status=Path(spec['receipt_path']).with_name('paused-start-'+str(os.getpid())+'-'+event.trial_name+'.json')
  status.write_text(json.dumps(dict(at=time.time(),trial_name=event.trial_name,held_before_environment=True,actual_model_calls=0))+'\n')
  while True:
   try:
    gate=json.loads(Path(spec['gate_release_path']).read_text());manifest_path=Path(gate['manifest_path']);raw=manifest_path.read_bytes();manifest=json.loads(raw)
    ready=gate['scope']=='ENV_PREFLIGHT30'and gate['manifest_sha256']==hashlib.sha256(raw).hexdigest()and manifest['frozen']and len(manifest['tasks'])==30 and all(t['status']=='PASS'for t in manifest['tasks'])and manifest['sampling_manifest_sha256']==spec['sampling_manifest_sha256']
   except(FileNotFoundError,KeyError,ValueError):ready=False
   if ready:break
   await asyncio.sleep(.5)
  status.write_text(json.dumps(dict(at=time.time(),trial_name=event.trial_name,held_before_environment=False,released_by_verified_env30_gate=True))+'\n')
 job.on_trial_started(hold_new_trial)
 receipt=dict(passed=True,at=time.time(),pid=os.getpid(),start_ticks=spec['start_ticks'],native_hook='Job.on_trial_started',hook_count_before=before,hook_count_after=before+1,existing_trial_hooks_unmodified=True,existing_agent_processes_unmodified=True,hook_source_sha256=spec['hook_source_sha256'],gate_release_path=spec['gate_release_path'])
 Path(spec['receipt_path']).write_text(json.dumps(receipt,indent=2)+'\n')
except BaseException as error:
 Path(PAUSE_SPEC+'.install-error.json').write_text(json.dumps(dict(at=time.time(),error=repr(error)))+'\n')
