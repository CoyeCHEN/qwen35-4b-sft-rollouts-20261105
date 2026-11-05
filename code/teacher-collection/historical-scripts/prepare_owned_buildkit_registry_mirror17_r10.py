"""Configure a documented registry mirror on the idle campaign builder only."""
import datetime,hashlib,json,os,signal,subprocess,time
from pathlib import Path
R=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/buildkit-rootless-r2')
NAME='rsi-cftmax-buildkit-rootless-r2'
def run(a,timeout=90):return subprocess.run(a,capture_output=True,text=True,check=True,timeout=timeout)
def freeze(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(x,f,indent=2)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 shared=json.loads(run(['docker','info','--format','{{json .}}']).stdout);assert shared['ID']=='9e09f846-3672-4739-b45b-2eb4330320d1'
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   a=(p/'cmdline').read_bytes().decode(errors='replace').split('\0')
   if a and a[0]==str(R/'tools/buildkit-rootless-r2/buildctl') and '--output' in a:raise RuntimeError('Existing native build remains active')
  except OSError:pass
 waiting=R/'checks/tmax-original-registry-recovery-r9.json';x=json.loads(waiting.read_text());pid=x['pid']
 assert x['status']=='ENV_BLOCKED_REGISTRY_AUTH_TLS_WAITING' and x['observed_tasks']==0
 proc=Path('/proc')/str(pid)
 assert str(R/'scripts/recover_original_tmax_registry_eof17_r9.py').encode() in (proc/'cmdline').read_bytes().split(b'\0')
 assert (proc/'wchan').read_text().strip()=='hrtimer_nanosleep'
 plan=json.loads((R/'manifests/TMAX_ORIGINAL_REGISTRY_EOF_RECOVERY_R9.json').read_text())
 assert not any((S/'archives'/v['task_id']/'registry-auth-recovery-r9').exists() for v in plan['tasks'])
 freeze(R/'checks/registry-recovery-r9-retired-before-any-build-r10.json',dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),prior_state=x,actual_wait_channel='hrtimer_nanosleep',build_attempts=0,teacher_or_verifier_actions=0,reason='Registry-auth endpoint remains unavailable; use the documented campaign-owned BuildKit registry mirror instead. Original wait plan and source retained.'))
 os.kill(pid,signal.SIGTERM)
 for _ in range(50):
  if not proc.exists():break
  time.sleep(.1)
 assert not proc.exists()
 original=json.loads(run(['docker','inspect',NAME]).stdout)[0]
 assert original['Config']['Labels']['rsi.campaign']==R.name and not original['HostConfig']['Privileged']
 assert original['HostConfig']['NanoCpus']==4*10**9 and original['HostConfig']['Memory']==16*1024**3
 config=S/'registry-mirror-r10/buildkitd.toml';config.parent.mkdir(exist_ok=False)
 with config.open('x') as f:f.write('[registry."docker.io"]\n  mirrors = ["mirror.gcr.io"]\n')
 config.chmod(0o444)
 freeze(config.parent/'PLAN.json',dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_sha256=sha(Path(__file__)),original_builder_id=original['Id'],image=original['Image'],original_command=original['Config']['Cmd'],configuration_sha256=sha(config),shared_docker_daemon_changed=False,task_source_contexts_changed=False,teacher_model_service_changed=False,resources=dict(cpus=4,memory_bytes=16*1024**3),references=['https://docs.cloud.google.com/artifact-registry/docs/pull-cached-dockerhub-images','https://raw.githubusercontent.com/moby/buildkit/master/docs/buildkitd.toml.md']))
 run(['docker','stop','--time','30',NAME]);run(['docker','rename',NAME,NAME+'-before-mirror-r10'])
 args=['docker','create','--name',NAME,'--label','rsi.campaign='+R.name,'--runtime','runc','--init','--restart','unless-stopped','--cpus','4','--memory','16g','--network','host',
  '--security-opt','seccomp=unconfined','--security-opt','apparmor=unconfined','--security-opt','systempaths=unconfined','--device','/dev/fuse',
  '--mount','type=bind,src='+str(S/'state')+',dst=/home/user/.local/share/buildkit',
  '--mount','type=bind,src='+str(config)+',dst=/home/user/.config/buildkit/buildkitd.toml,readonly',
  '--env','HTTP_PROXY=http://127.0.0.1:7890','--env','HTTPS_PROXY=http://127.0.0.1:7890','--env','NO_PROXY=localhost,127.0.0.1',
  original['Image'],'--oci-worker-snapshotter=fuse-overlayfs','--config','/home/user/.config/buildkit/buildkitd.toml']
 container=run(args).stdout.strip();run(['docker','start',container])
 tool=str(R/'tools/buildkit-rootless-r2/buildctl')
 for _ in range(60):
  q=subprocess.run([tool,'--addr','docker-container://'+NAME,'debug','workers'],capture_output=True,text=True,timeout=10)
  if q.returncode==0:break
  time.sleep(1)
 else:raise RuntimeError('Owned rootless builder did not become ready; preserve logs')
 current=json.loads(run(['docker','inspect',NAME]).stdout)[0]
 assert current['Image']==original['Image'] and current['HostConfig']['NanoCpus']==original['HostConfig']['NanoCpus'] and current['HostConfig']['Memory']==original['HostConfig']['Memory'] and not current['HostConfig']['Privileged'] and not current['HostConfig'].get('DeviceRequests')
 assert run(['docker','info','--format','{{.ID}}']).stdout.strip()==shared['ID']
 freeze(R/'checks/owned-buildkit17-registry-mirror-r10.json',dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='OWNED_BUILDER_READY_ORIGINAL_CONTEXT_BUILD_ACCEPTANCE_PENDING',old_builder_id=original['Id'],new_builder_id=container,image_id=current['Image'],configuration=str(config),configuration_sha256=sha(config),worker_metadata=q.stdout,source_contexts_modified=0,shared_daemon_configuration_changes=0,teacher_actions=0,model_calls=0))
 print('OWNED_BUILDER_MIRROR_READY_ORIGINAL_TASK_BUILD_PENDING',flush=True)
if __name__=='__main__':
 for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
 os.environ['HTTP_PROXY']=os.environ['HTTPS_PROXY']='http://127.0.0.1:7890'
 main()
