"""Only two registered terminal NOP identities; unchanged native cleanup120."""
import asyncio,importlib,json,os,time
from pathlib import Path,PurePosixPath
from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.task import Task
from harbor.models.trial.config import TrialConfig
from harbor.models.trial.paths import TrialPaths
base=importlib.import_module('environment_evidence_audit_r4');read=base.read;write=base.write;sha=base.sha
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'environment-preflight59-r1';T=B/'torch271-recheck-r1';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control');TASKS={'pytorch-model-cli','pytorch-model-recovery'}
def original(plan,item):
 assert len(plan['rows'])==2 and {x['task_id']for x in plan['rows']}==TASKS and item['task_id']in TASKS
 p=Path(plan['original_actual_manifest_path']);assert sha(p)==plan['original_actual_manifest_sha256'];actual=read(p);assert actual['native_job_id']==plan['original_native_job_id']
 cfg=next(c for c in actual['trials']if Path(c['task']['path']).name==item['task_id']);d=Path(cfg['trials_dir'])/cfg['trial_name'];raw=read(d/'result.json')
 assert sha(d/'result.json')==item['original_result_sha256']and sha(d/'config.json')==item['original_config_sha256']and raw['id']==item['original_native_trial_id']
 assert raw['exception_info']['exception_type']=='TimeoutError'and raw['verifier_result']['return_code']==0 and raw['verifier_result']['rewards']['reward']==0
 runtime=read(d/'agent/ENV_PREFLIGHT_RUNTIME.json');assert runtime['passed']and runtime['model_generation_calls']==0 and runtime['identity']==item['identity']and runtime['engine_id']==plan['engine_id']
 assert cfg['agent']['import_path']=='env_preflight_shared_agent_r2:OpenHarnessPreflightNopAgent'
 events=list(d.glob('remote-docker-*.jsonl'));assert len(events)==1;record=json.loads(events[0].open().readline());assert record['identity']==item['identity']and record['project']=='q35envpreflight59r1-'+item['identity']and record['workspace']==item['original_workspace']
 for evidence in item['official_verifier_sources']:assert sha(Path(evidence['path']))==evidence['sha256']
 return cfg,d,record,events[0]
async def clean(plan,item):
 cfg,d,record,events=original(plan,item);p=T/'cleanup-receipts'/(item['task_id']+'.json')
 if p.exists():return read(p)
 value=dict(at=time.time(),task_id=item['task_id'],identity=item['identity'],original_result_sha256=sha(d/'result.json'),source_sha256=sha(Path(__file__)),plan_sha256=sha(T/'PLAN_R1.json'),model_generation_calls=0)
 try:
  async with asyncio.timeout(180):
   c=TrialConfig.model_validate(cfg);task=Task(c.task.path);paths=TrialPaths(T/'native-cleanup-evidence'/item['task_id']);paths.mkdir()
   env=EnvironmentFactory.create_environment_from_config(c.environment,environment_dir=task.paths.environment_dir,environment_name=task.short_name,session_id='env59-terminal-cleanup-'+item['identity'],trial_paths=paths,task_env_config=task.config.environment)
   env.identity=item['identity'];env.project=record['project'];env.workspace=PurePosixPath(record['workspace']);env.root=env.workspace.parent;env._remote_compose=events.with_suffix('.compose.json');env._prepared=True;env._workspace_created=True;env.evidence=T/'native-cleanup-evidence'/item['task_id']/'provider-cleanup.jsonl';await env._connect()
   info=json.loads((await env._run(env._docker('info','--format','{{json .}}'))).stdout);assert info['ID']==plan['engine_id'];before=await env._resources();value['resources_before']=before
   assert not before['container'],'An original container reappeared; require identity inspection'
   assert set(before['network'])<=set(item['expected_network_ids'])and set(before['volume'])<=set(item['expected_volume_names'])
   assert env.cleanup_timeout==120;value['native_cleanup_timeout_sec']=env.cleanup_timeout;await env.stop(delete=True);after=await env._resources();assert not any(after.values());value.update(passed=True,resources_after=after)
 except Exception as exc:value.update(passed=False,cleanup_unconfirmed=True,error=repr(exc))
 assert sha(d/'result.json')==value['original_result_sha256'];write(p,value);return value
async def main():
 admission=read(T/'CLEANUP_ADMISSION_R1.json');assert admission['unique_controller_owner']==read(C/'NATIVE_ADVANCE_OWNER.json')and admission['source_sha256']==sha(Path(__file__))and admission['plan_sha256']==sha(T/'PLAN_R1.json')
 for path,digest in admission['required_source_sha256'].items():assert sha(Path(path))==digest,path
 assert not(T/'CLEANUP_COMPLETE_R1.json').exists(),'Never overwrite the cleanup aggregate'
 guard=R/'formal-controller18-docker-admission-env59-r1/bin/docker';assert sha(guard)==admission['docker_guard_sha256'];os.environ['PATH']=str(guard.parent)+':'+str(R/'formal-controller18-client-bin-r1')+':'+os.environ['PATH'];os.environ['TMPDIR']=str(R/'tmp')
 plan=read(T/'PLAN_R1.json');rows=[await clean(plan,item)for item in plan['rows']];value=dict(at=time.time(),passed=all(r.get('passed')for r in rows),rows=rows,model_generation_calls=0,original_raw_results_preserved=True,source_sha256=sha(Path(__file__)));write(T/'CLEANUP_COMPLETE_R1.json',value)
 if not value['passed']:raise RuntimeError('Two exact terminal NOP cleanups not confirmed')
if __name__=='__main__':asyncio.run(main())
