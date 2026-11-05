"""Native upload-boundary proof, then one official NOP verifier Trial; no teacher."""
import asyncio,hashlib,json,os,shlex
from pathlib import Path
from uuid import uuid4
from harbor.models.task.task import Task
from harbor.models.trial.paths import TrialPaths
from harbor.models.job.config import JobConfig
from harbor.job import Job
from harbor_remote_docker import RemoteDockerEnvironment

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


async def main():
 ident='task_000173_27f3fc33';path=R/'prepared-tasks/tmax-public-input-review-r6'/ident
 task=Task(path);base=json.loads((R/'configs/original-environment-corrective-verifier-probe.json').read_text())
 out=R/'diagnostics/native-public-input-upload-r6';out.mkdir(exist_ok=False)
 paths=TrialPaths(out)
 for p in [paths.agent_dir,paths.verifier_dir,paths.artifacts_dir]:p.mkdir(parents=True,exist_ok=True)
 options=dict(base['environment']['kwargs']);options['project_namespace']='publicinputboundary20261030'
 env=RemoteDockerEnvironment(environment_dir=task.paths.environment_dir,environment_name='public-input-boundary',
  session_id=uuid4().hex,trial_paths=paths,task_env_config=task.config.environment,**options)
 env.configure_agent_runtime(writable=True,executable=True)
 boundary=json.loads((R/'checks/public-input-boundaries'/(ident+'.json')).read_text())
 expected={v['path']:v['sha256'] for v in boundary['files']}
 result=dict(passed=False,task_id=ident,model_calls=0,teacher_attempts=0,
  official_task_files_changed=False,task_toml_sha256=sha(path/'task.toml'),
  boundary_manifest_sha256=sha(R/'checks/public-input-boundaries'/(ident+'.json')))
 try:
  await asyncio.wait_for(env.start(force_build=False),timeout=180)
  for phase in ['before_private_upload','after_private_upload']:
   if phase=='after_private_upload':
    await env.upload_dir(path/'tests','/tests')
    expected.update({'/tests/'+p.name:sha(p) for p in (path/'tests').iterdir() if p.is_file()})
   code=('from pathlib import Path; import hashlib,json; '
     'actual={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path("/tests").rglob("*") if p.is_file()}; '
     'assert actual=='+repr(expected)+'; print(json.dumps({"matched":True,"files":len(actual)}))')
   checked=await env.exec(shlex.join(['python3','-c',code]),cwd='/home/user',timeout_sec=60)
   (out/(phase+'-stdout.txt')).write_text(checked.stdout or '');(out/(phase+'-stderr.txt')).write_text(checked.stderr or '')
   if checked.return_code:raise RuntimeError('Native public/private upload boundary failed: '+phase)
   result[phase]=json.loads(checked.stdout)
  result['passed']=True
 finally:
  await env.stop(delete=True);result['cleanup_confirmed']=True
  (R/'checks/tmax-public-input-native-upload-r6.json').write_text(json.dumps(result,indent=2))
 if not result['passed']:return
 name='tmax-public-input-native-verifier-probe-20261030';config_file=R/'configs/tmax-public-input-native-verifier-probe.json'
 if config_file.exists() or (R/'jobs'/name).exists():raise FileExistsError('Native NOP identity already exists; inspect, never replay')
 base.update(job_name=name,n_attempts=1,n_concurrent_trials=1,retry={'max_retries':0},tasks=[dict(path=str(path))])
 base['agents']=[dict(name='nop')];base['environment']['kwargs']['project_namespace']='publicinputverifier20261030'
 parsed=JobConfig.model_validate(base)
 with config_file.open('x') as stream:stream.write(parsed.model_dump_json(indent=2))
 job=await Job.create(parsed);await job.run()
 files=list((R/'jobs'/name).glob('*/result.json'));assert len(files)==1
 native=json.loads(files[0].read_text());log=(files[0].parent/'verifier/test-stdout.txt').read_text(errors='replace')
 evidence=dict(model_calls=0,teacher_attempts=0,job_name=name,trial_id=native['id'],native_result_sha256=sha(files[0]),
  reward=(native.get('verifier_result') or {}).get('rewards'),native_exception=native.get('exception_info'),
  verifier_actually_completed=bool((native.get('verifier') or {}).get('finished_at')),
  verifier_log_sha256=sha(files[0].parent/'verifier/test-stdout.txt'),
  no_import_or_missing_input_failure=not any(x in log for x in ['ERROR collecting','ModuleNotFoundError','ImportError','FileNotFoundError']),
  scope='Actual original verifier and native lifecycle, NOP diagnostic only; not teacher attempt or success trajectory')
 evidence['passed']=evidence['verifier_actually_completed'] and not evidence['native_exception'] and evidence['no_import_or_missing_input_failure']
 (R/'checks/tmax-public-input-native-verifier-r6.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(evidence))


if __name__=='__main__':
 os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH'];os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
 for k in ['DEEPSEEK_API_KEY','GH_TOKEN']:os.environ.pop(k,None)
 asyncio.run(main())
