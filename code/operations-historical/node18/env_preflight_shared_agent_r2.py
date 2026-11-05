"""Verification utility: inherit the frozen CLI installer, run native NOP only."""
import hashlib,json,os,shlex,subprocess,time
from pathlib import Path,PurePosixPath
from harbor.agents.installed.open_harness import OpenHarnessAgent
from harbor.agents.nop import NopAgent
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');BASE=Path(os.environ.get('RSI_ENV_PREFLIGHT_SPEC_BASE',str(R/'environment-preflight30')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
class OpenHarnessPreflightNopAgent(OpenHarnessAgent):
 @staticmethod
 def name():return 'open-harness-install-then-native-nop'
 async def setup(self,environment):
  await super().setup(environment)
  task=environment.environment_dir.parent.name;spec=json.loads((BASE/'specs'/f'{task}.json').read_text())
  spec['remote_wheel']=str(PurePosixPath(self._runtime_dir)/Path(self.options.wheel_path).name)
  public_spec={key:spec[key]for key in ['public_files','remote_wheel','wheel_sha256','model_endpoints']}
  local=self.logs_dir/'ENV_PREFLIGHT_PUBLIC_PROBE_INPUT.json';local.write_text(json.dumps(public_spec))
  remote_spec=str(PurePosixPath(self._runtime_dir)/'rsi-env-public-probe.json');remote_probe=str(PurePosixPath(self._runtime_dir)/'rsi-env-public-probe.py')
  await environment.upload_file(local,remote_spec);await environment.upload_file(R/'env_preflight30_probe_r1.py',remote_probe)
  command=shlex.join([self._remote_venv+'/bin/python',remote_probe,remote_spec]);result=await environment.exec(command,timeout_sec=180)
  output=self.logs_dir/'ENV_PREFLIGHT_CONTAINER_PROBE_RAW.json';output.write_text(json.dumps(dict(return_code=result.return_code,stdout=result.stdout,stderr=result.stderr),indent=2)+'\n')
  assert result.return_code==0,result.stderr[-1000:]
  probe=json.loads(result.stdout);assert probe['passed']and probe['model_generation_calls']==0
  ids=subprocess.check_output(['docker','--host',environment.endpoint,'ps','--filter','label=io.harbor.remote-docker.identity='+environment.identity,'-q'],text=True,timeout=15).split();assert len(ids)==1
  container=json.loads(subprocess.check_output(['docker','--host',environment.endpoint,'inspect',ids[0]],text=True,timeout=15))[0]
  engine=json.loads(subprocess.check_output(['docker','--host',environment.endpoint,'info','--format','{{json .}}'],text=True,timeout=15))
  assert engine['ID']==spec['engine_id']and container['State']['Running']
  if spec['expected_image_id']is not None:assert container['Image']==spec['expected_image_id']
  limits=container['HostConfig'];cpus=limits.get('NanoCpus',0)/1e9 or(limits.get('CpuQuota',0)/limits.get('CpuPeriod',100000)if limits.get('CpuQuota',0)>0 else 0)
  assert abs(cpus-spec['original_environment']['cpus'])<1e-6
  assert limits['Memory']==spec['original_environment']['memory_mb']*1024**2
  assert probe['available_bytes']>=spec['original_environment']['storage_mb']*1024**2 and probe['available_inodes']>100
  version=await environment.exec(self.get_version_command(),timeout_sec=30);assert version.return_code==0 and version.stdout.strip()
  proof=dict(passed=True,at=time.time(),task_id=task,container_id=container['Id'],container_name=container['Name'],container_created=container['Created'],engine_id=engine['ID'],engine_node=engine['Name'],engine_version=engine['ServerVersion'],endpoint=environment.endpoint,identity=environment.identity,project=environment.project,actual_image_id=container['Image'],original_image_id=spec['expected_image_id'],actual_cpus=cpus,actual_memory_bytes=limits['Memory'],mounts=container['Mounts'],container_probe=probe,cli_version=version.stdout.strip(),cli_return_code=version.return_code,utility_source_sha256=sha(Path(__file__)),probe_source_sha256=sha(R/'env_preflight30_probe_r1.py'),official_task_files_unchanged=True,model_generation_calls=0)
  (self.logs_dir/'ENV_PREFLIGHT_RUNTIME.json').write_text(json.dumps(proof,indent=2)+'\n')
 async def run(self,instruction,environment,context):
  context.metadata=dict(env_preflight_only=True,model_generation_calls=0,native_nop=True)
  return await NopAgent.run(self,instruction,environment,context)
