"""Only failed, terminal native NOPs: resume provider's exact scoped cleanup."""
import asyncio,fcntl,os,time
from pathlib import Path,PurePosixPath
from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.task import Task
from harbor.models.trial.config import TrialConfig
from harbor.models.trial.paths import TrialPaths
from environment_evidence_audit_r3 import read,write,sha
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101'); B=R/'environment-preflight30/terminal-cleanup-r2';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
async def clean(cfg):
 source=Path(cfg['trials_dir'])/cfg['trial_name'];result=read(source/'result.json');cfg=TrialConfig.model_validate(cfg)
 assert cfg.agent.import_path in ['env_preflight30_agent_r1:OpenHarnessPreflightNopAgent','env_preflight_shared_agent_r2:OpenHarnessPreflightNopAgent','env_preflight_synthetic32_agent_r3:OpenHarnessPreflightNopAgent']
 events=list(source.glob('remote-docker-*.jsonl'))
 if len(events)!=1:return
 lines=[__import__('json').loads(s)for s in events[0].read_text().splitlines()];record=lines[0];identity=record['identity'];p=B/(identity+'.json')
 if p.exists():return
 if not any(s.get('action')=='prepared'for s in lines):return
 assert record['project'].startswith(('q35envpreflight30','q35synth32prep'))
 value=dict(at=time.time(),identity=identity,original_trial_path=str(source),original_result_sha256=sha(source/'result.json'),model_generation_calls=0,original_result_unchanged=True)
 try:
  task=Task(cfg.task.path);paths=TrialPaths(B/identity);paths.mkdir();env=EnvironmentFactory.create_environment_from_config(cfg.environment,environment_dir=task.paths.environment_dir,environment_name=task.short_name,session_id='nop-cleanup-'+identity,trial_paths=paths,task_env_config=task.config.environment)
  env.identity=identity;env.project=record['project'];env.workspace=PurePosixPath(record['workspace']);env.root=env.workspace.parent;env._remote_compose=events[0].with_suffix('.compose.json');env._prepared=True;env._workspace_created=True;env.evidence=B/identity/'provider-cleanup.jsonl';await env._connect()
  before=await env._resources();value['resources_before']=before
  if any(before.values()):await env.stop(delete=True)
  after=await env._resources();assert not any(after.values());value.update(passed=True,resources_after=after)
 except Exception as exc:value.update(passed=False,blocker=repr(exc),cleanup_unconfirmed=True)
 write(p,value)
async def main():
 assert read(B/'ADMISSION_R2.json')['unique_controller_owner']==read(C/'NATIVE_ADVANCE_OWNER.json');os.environ['PATH']=str(R/'formal-controller18-client-bin-r1')+':'+os.environ['PATH'];os.environ['TMPDIR']=str(R/'tmp')
 paths=[R/'environment-preflight30/ACTUAL_NATIVE_TRIALS_R1.json',R/'synthetic32/prep-ACTUAL_NATIVE_TRIALS_R1.json']
 for base in [R/'environment-preflight30',R/'synthetic32/env-runtime']:
  p=base/'RECHECK_REGISTRY_R1.json'
  if p.exists():paths += [Path(s)for s in read(p)['actual_trial_manifests']]
 configs=[]
 for path in paths:
  if path.exists():
   for cfg in read(path)['trials']:
    p=Path(cfg['trials_dir'])/cfg['trial_name']/'result.json'
    if p.exists()and(read(p).get('exception_info')or read(p).get('infrastructure_errors')):configs.append(cfg)
 semaphore=asyncio.Semaphore(2)
 async def bounded(cfg):
  async with semaphore:await clean(cfg)
 with(B/'cleanup.lock').open('a')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);await asyncio.gather(*(bounded(cfg)for cfg in configs))
 write(B/'COMPLETE.json',dict(at=time.time(),checked=len(configs),results=[read(p)for p in B.glob('*.json')if p.name not in ['ADMISSION_R2.json','COMPLETE.json']]))
if __name__=='__main__':asyncio.run(main())
