"""Preserve and natively retire two exact finished scopes; never signal an Agent."""
import asyncio
import json
import os
from pathlib import Path,PurePosixPath
import shlex
import subprocess
import tomllib

from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.config import TaskConfig
from harbor.models.trial.config import TrialConfig
from harbor.models.trial.paths import TrialPaths
import collection_readiness_r21 as n

S=n.R/'stream/terminal-teacher-resource-cleanup17-r412'
REGISTRY=n.R/'checks/TERMINAL_SUBNET_LEAK_SCOPES_R399.json'


async def preserve(case):
 payload=dict(socket=n.NODE['socket'],engine_id=n.NODE['engine_id'],identity=case['identity'],
              containers=case['network']['containers'],trial_id=case['trial_id'])
 code="""from pathlib import Path
import subprocess,json,hashlib,os
v=json.loads(PAYLOAD);os.umask(0o077)
cli=['docker','--host','unix://'+v['socket']]
engine=subprocess.run(cli+['info','--format','{{.ID}}'],check=True,capture_output=True,text=True,timeout=20).stdout.strip()
assert engine==v['engine_id']
root=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/terminal-source-preservation-r412')/v['trial_id']
root.mkdir(parents=True,exist_ok=False)
out=[]
for cid in v['containers']:
 info=json.loads(subprocess.run(cli+['inspect',cid],check=True,capture_output=True,text=True,timeout=20).stdout)[0]
 assert info['Config']['Labels']['io.harbor.remote-docker.identity']==v['identity']
 top=subprocess.run(cli+['top',cid,'-eo','pid,stat,args'],check=True,capture_output=True,text=True,timeout=20).stdout
 assert not any(('open-harness' in line and '--prompt-file' in line) or '/tests/test.sh' in line for line in top.splitlines()),'Unexpected live Agent or official Verifier; preserve scope'
 cwd=info['Config']['WorkingDir'];assert cwd.startswith('/') and cwd not in ['/','/proc','/sys','/dev']
 for label,source in [('agent','/logs/agent'),('verifier','/logs/verifier'),('workspace',cwd)]:
  target=root/(cid[:12]+'-'+label+'.tar')
  with target.open('xb') as f:
   result=subprocess.run(cli+['cp','-a',cid+':'+source.rstrip('/')+'/.','-'],stdout=f,stderr=subprocess.PIPE,timeout=180)
  if result.returncode:
   with (root/(label+'-copy-error.json')).open('x') as error_log:json.dump(dict(returncode=result.returncode,stderr=result.stderr.decode(errors='replace')),error_log)
   if b'could not find' in result.stderr.lower() or b'no such file' in result.stderr.lower():
    out.append(dict(kind=label,source=source,observed=False,returncode=result.returncode));continue
   raise ValueError('Exact owned filesystem preservation failed')
  import tarfile
  with tarfile.open(target,'r:') as archive:members=archive.getmembers()
  digest_state=hashlib.sha256()
  with target.open('rb') as f:
   for block in iter(lambda:f.read(1048576),b''):digest_state.update(block)
  digest=digest_state.hexdigest()
  out.append(dict(kind=label,source=source,observed=True,path=str(target),bytes=target.stat().st_size,sha256=digest,tar_members=len(members)))
report=dict(engine_id=engine,identity=v['identity'],trial_id=v['trial_id'],artifacts=out,
 raw_tar_files_not_extracted=True,container_environment_or_credentials_exported=False,new_model_calls=0)
with (root/'PRESERVATION.json').open('x') as f:json.dump(report,f,indent=2)
print(json.dumps(report))""".replace('PAYLOAD',repr(json.dumps(payload)))
 reply=await asyncio.to_thread(subprocess.run,[*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],shlex.join(['python3','-c',code])],check=True,capture_output=True,text=True,timeout=600)
 return json.loads(reply.stdout)


async def main():
 import fcntl
 S.mkdir(parents=True,exist_ok=True)
 lock=(S/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if (S/'PLAN.json').exists():raise FileExistsError('Observe existing exact cleanup; no replay')
 if n.sha(REGISTRY)!='3fdefa5f653efef4fd6e70f16c812ddad1acb66db94b893c8e08e5aa7c3812f7':raise ValueError('Terminal cleanup scope changed')
 registry=json.loads(REGISTRY.read_text());assert len(registry['cases'])==2
 n.freeze(S/'PLAN.json',dict(previous_failed_preservation=str(n.R/'stream/terminal-teacher-resource-cleanup17-r401'),previous_failure_not_rewritten=True,corrected_failure_cause='System Python3.10 lacks hashlib.file_digest; complete prior tar and all original scopes retained',live_read_only_archive_probe_after_failure='2026-10-31: same owned source docker cp returned0; no active Agent or official Verifier',source_sha256=n.sha(Path(__file__)),scope_sha256=n.sha(REGISTRY),model_calls=0,teacher_admissions=0,exact_original_native_stop_only=True))
 for case in registry['cases']:
  trial=Path(case['trial']);result=trial/'result.json';journal=trial/'agent/openharness-rollout/events.jsonl'
  assert n.sha(result)==case['result_sha256'] and n.sha(journal)==case['recorder_sha256']
  raw=json.loads(result.read_text());assert raw['id']==case['trial_id'] and raw['finished_at']
  assert raw['agent_execution']['finished_at'] and raw['verifier']['finished_at']
  events=[json.loads(line) for line in (n.R/'stream/collection-r4/teacher-lifecycle.jsonl').open()]
  kinds={e['event'] for e in events if e['trial_name']==trial.name}
  assert {'TEACHER_ADMITTED','TEACHER_AGENT_ENDED','TEACHER_FINALIZED'}<=kinds
  destination=S/case['trial_id'];destination.mkdir(exist_ok=False)
  n.freeze(destination/'SOURCE_ARCHIVE.json',await asyncio.to_thread(n.archive_trial,trial))
  n.freeze(destination/'PRESERVED_CONTAINER_FILES.json',await preserve(case))
  cfg=TrialConfig.model_validate_json((trial/'config.json').read_text())
  assert cfg.environment.kwargs['endpoint']==n.DEPLOYMENT['environment']['kwargs']['endpoint'] and cfg.environment.kwargs['remote_socket_path']==n.NODE['socket']
  evidence,=trial.glob('remote-docker-*.jsonl');native=[json.loads(line) for line in evidence.open()]
  original=native[0];identity=case['identity'];project=cfg.environment.kwargs['project_namespace']+'-'+identity
  assert original['identity']==identity and original['project']==project
  assert all(x['identity']==identity and x['project']==project and x['workspace']==original['workspace'] for x in native)
  connected=[x for x in native if x['action']=='connected'];assert connected and all(x['daemon_id']==n.NODE['engine_id'] for x in connected)
  assert original['workspace']==n.DEPLOYMENT['environment']['kwargs']['staging_root']+'/'+project
  task=Path(cfg.task.path);resources=TaskConfig.model_validate(tomllib.loads((task/'task.toml').read_text())).environment
  env=EnvironmentFactory.create_environment_from_config(config=cfg.environment,environment_dir=task/'environment',environment_name=trial.name,session_id=original['session_id'],trial_paths=TrialPaths(trial_dir=destination/'native-cleanup'),task_env_config=resources)
  env.identity=identity;env.project=project;env.workspace=PurePosixPath(original['workspace']);env.evidence=destination/'remote-docker-cleanup.jsonl'
  await env._connect();before=await env._resources()
  assert len(before['container'])==len(case['network']['containers']) and all(sum(full.startswith(short) for full in case['network']['containers'])==1 for short in before['container'])
  present=await env._shell('test -d '+shlex.quote(original['workspace']),check=False)
  assert present.return_code in (0,1);env._workspace_created=present.return_code==0
  await env.stop(delete=True);after=await env._resources();assert not any(after.values())
  assert n.sha(result)==case['result_sha256'] and n.sha(journal)==case['recorder_sha256']
  proof=dict(passed=True,trial_id=case['trial_id'],task_id=case['task_id'],identity=identity,engine_id=n.NODE['engine_id'],before=before,after=after,source_result_sha256=case['result_sha256'],source_recorder_sha256=case['recorder_sha256'],model_calls=0,source_results_rewards_recorders_modified=False,active_agent_or_verifier_signals=0,native_terminal_scope_cleanup=True)
  n.freeze(destination/'ACCEPTANCE.json',proof);print(json.dumps(proof),flush=True)
 n.freeze(S/'TERMINAL.json',dict(passed=True,exact_terminal_scopes_cleaned=2,model_calls=0,teacher_dispatches=0))


if __name__=='__main__':
 os.environ['PATH']=n.DEPLOYMENT['native_client_bin']+':'+str(n.R/'client-bin-v2')+':'+os.environ['PATH']
 os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
 for name in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(name,None)
 asyncio.run(main())
