"""One registered terminal NOP identity; resume unchanged native scoped cleanup."""
import asyncio,importlib,json,os,time
from pathlib import Path,PurePosixPath
from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.task import Task
from harbor.models.trial.config import TrialConfig
from harbor.models.trial.paths import TrialPaths
base=importlib.import_module('environment_evidence_audit_r4');read=base.read;write=base.write;sha=base.sha
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'environment-preflight59-r1';Q=B/'extract-elf-recheck-r1';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
IDENTITY='ef4f76a0654748cb9b8badfe6ae0b9be'

def original(plan):
 assert plan['task_id']=='extract-elf'and plan['original_identity']==IDENTITY
 p=Path(plan['original_actual_manifest_path']);assert sha(p)==plan['original_actual_manifest_sha256']
 actual=read(p);assert actual['native_job_id']==plan['original_native_job_id']
 cfg=next(c for c in actual['trials']if Path(c['task']['path']).name=='extract-elf');d=Path(cfg['trials_dir'])/cfg['trial_name']
 assert sha(d/'result.json')==plan['original_result_sha256']and sha(d/'config.json')==plan['original_config_sha256']
 raw=read(d/'result.json');assert raw['id']==plan['original_native_trial_id']and raw['exception_info']['exception_type']=='TimeoutError'
 assert raw['verifier_result']['return_code']==0 and raw['verifier_result']['rewards']['reward']==0
 assert cfg['agent']['import_path']=='env_preflight_shared_agent_r2:OpenHarnessPreflightNopAgent'
 runtime=read(d/'agent/ENV_PREFLIGHT_RUNTIME.json');assert runtime['passed']and runtime['model_generation_calls']==0 and runtime['identity']==IDENTITY
 events=list(d.glob('remote-docker-*.jsonl'));assert len(events)==1;record=json.loads(events[0].open().readline())
 assert record['identity']==IDENTITY and record['project']=='q35envpreflight59r1-'+IDENTITY
 assert record['workspace']==plan['original_workspace']and runtime['engine_id']==plan['engine_id']
 return cfg,d,record,events[0]

async def main():
 admission=read(Q/'CLEANUP_ADMISSION_R1.json');assert admission['unique_controller_owner']==read(C/'NATIVE_ADVANCE_OWNER.json')and admission['source_sha256']==sha(Path(__file__))
 plan=read(Q/'PLAN_R1.json');assert sha(Q/'PLAN_R1.json')==admission['plan_sha256'];cfg,d,record,events=original(plan)
 for path,digest in admission['required_source_sha256'].items():assert sha(Path(path))==digest,path
 assert not(Q/'CLEANUP_COMPLETE_R1.json').exists(),'Never overwrite cleanup receipt'
 guard=R/'formal-controller18-docker-admission-env59-r1/bin/docker';assert sha(guard)==admission['docker_guard_sha256']
 os.environ['PATH']=str(guard.parent)+':'+str(R/'formal-controller18-client-bin-r1')+':'+os.environ['PATH'];os.environ['TMPDIR']=str(R/'tmp')
 value=dict(at=time.time(),original_identity=IDENTITY,original_result_sha256=sha(d/'result.json'),source_sha256=sha(Path(__file__)),plan_sha256=sha(Q/'PLAN_R1.json'),model_generation_calls=0)
 try:
  async with asyncio.timeout(180):
   c=TrialConfig.model_validate(cfg);task=Task(c.task.path);paths=TrialPaths(Q/'native-cleanup-evidence');paths.mkdir()
   env=EnvironmentFactory.create_environment_from_config(c.environment,environment_dir=task.paths.environment_dir,environment_name=task.short_name,session_id='env59-terminal-cleanup-'+IDENTITY,trial_paths=paths,task_env_config=task.config.environment)
   env.identity=IDENTITY;env.project=record['project'];env.workspace=PurePosixPath(record['workspace']);env.root=env.workspace.parent;env._remote_compose=events.with_suffix('.compose.json');env._prepared=True;env._workspace_created=True;env.evidence=Q/'native-cleanup-evidence/provider-cleanup.jsonl';await env._connect()
   connected=json.loads((await env._run(env._docker('info','--format','{{json .}}'))).stdout);assert connected['ID']==plan['engine_id']
   before=await env._resources();value['resources_before']=before
   assert not before['container'],'A container appeared for the terminal identity; require inspection'
   assert set(before['network'])<=set(plan['expected_network_ids'])and set(before['volume'])<=set(plan['expected_volume_names'])
   value['native_cleanup_timeout_sec']=env.cleanup_timeout
   await env.stop(delete=True)
   after=await env._resources();assert not any(after.values());value.update(passed=True,resources_after=after)
 except Exception as exc:value.update(passed=False,cleanup_unconfirmed=True,error=repr(exc))
 assert sha(d/'result.json')==value['original_result_sha256'];write(Q/'CLEANUP_COMPLETE_R1.json',value)
 if not value.get('passed'):raise RuntimeError('Exact terminal NOP cleanup unconfirmed; no recheck admitted')
if __name__=='__main__':asyncio.run(main())
