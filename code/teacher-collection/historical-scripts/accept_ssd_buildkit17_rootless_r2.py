"""Official CPU-only rootless BuildKit, owned SSD state, native OCI exporter."""
from pathlib import Path
import hashlib,json,os,subprocess,time
R=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/buildkit-rootless-r2')
NAME='rsi-cftmax-buildkit-rootless-r2'
for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
def run(args,**kw):return subprocess.run(args,check=True,capture_output=True,text=True,**kw)
assert run(['docker','info','--format','{{.ID}}']).stdout.strip()=='9e09f846-3672-4739-b45b-2eb4330320d1'
source=json.loads((R/'checks/ssd-buildkit17-rootless-r2-pinned-image.json').read_text());image=source['pinned']
if subprocess.run(['docker','inspect',NAME],capture_output=True).returncode==0:raise FileExistsError('Inspect existing owned builder before reusing')
S.mkdir(parents=True,exist_ok=True);assert S.stat().st_uid==os.getuid()
state=S/'state';state.mkdir(exist_ok=True)
# Change only the new owned state mount to the official rootless image UID.
run(['docker','run','--rm','--user','0:0','--entrypoint','/bin/sh','--mount','type=bind,src='+str(state)+',dst=/owned-state',image,'-c','chown 1000:1000 /owned-state'],timeout=60)
reply=run(['docker','create','--name',NAME,'--label','rsi.campaign=qwen35-new-cf500-tmax500-20261029',
 '--runtime','runc','--init','--restart','unless-stopped','--cpus','4','--memory','16g','--network','host',
 '--security-opt','seccomp=unconfined','--security-opt','apparmor=unconfined','--security-opt','systempaths=unconfined',
 '--device','/dev/fuse','--mount','type=bind,src='+str(state)+',dst=/home/user/.local/share/buildkit',
 '--env','HTTP_PROXY=http://127.0.0.1:7890','--env','HTTPS_PROXY=http://127.0.0.1:7890','--env','NO_PROXY=localhost,127.0.0.1',
 image,'--oci-worker-snapshotter=fuse-overlayfs'],timeout=60)
container_id=reply.stdout.strip();container=json.loads(run(['docker','inspect',container_id]).stdout)[0]
assert not container['HostConfig'].get('DeviceRequests') and not container['HostConfig']['Privileged']
assert container['HostConfig']['Runtime']=='runc'
assert all(x['PathOnHost']=='/dev/fuse' for x in container['HostConfig']['Devices'])
assert container['Config']['User']=='1000:1000' or container['Config']['User'] in ['user','1000']
run(['docker','start',container_id],timeout=60)
address='unix:///run/user/1000/buildkit/buildkitd.sock'
for attempt in range(30):
 probe=subprocess.run(['docker','exec',container_id,'buildctl','--addr',address,'debug','workers'],capture_output=True,text=True,timeout=10)
 if probe.returncode==0:break
 inspect=json.loads(run(['docker','inspect',container_id]).stdout)[0]
 if not inspect['State']['Running']:raise RuntimeError('Rootless BuildKit failed; original container logs retained')
 time.sleep(1)
else:raise RuntimeError('Rootless BuildKit worker did not become ready')
space=run(['docker','exec',container_id,'df','-B1','/home/user/.local/share/buildkit'],timeout=30).stdout
assert '/dev/nvme0n1' in space
visible=run(['docker','exec',container_id,'sh','-c','test ! -e /dev/nvidia0; test ! -e /dev/nvidiactl; id'],timeout=30).stdout
binpath=R/'tools/buildkit-rootless-r2/buildctl';binpath.parent.mkdir(parents=True,exist_ok=True)
run(['docker','cp',container_id+':/usr/bin/buildctl',str(binpath)],timeout=30);binpath.chmod(0o755)
context=S/'diagnostic-context';context.mkdir(exist_ok=True)
(context/'Dockerfile').write_text('FROM scratch\nCOPY marker /rsi-ssd-buildkit-acceptance\n')
(context/'marker').write_text('CPU-only native SSD BuildKit acceptance; no benchmark task/model/oracle.\n')
archive=S/'diagnostic-image.oci.tar'
if archive.exists():raise FileExistsError('Never overwrite a frozen exporter artifact')
with (R/'logs/ssd-buildkit17-rootless-r2-exporter.log').open('x') as log:
 subprocess.run([str(binpath),'--addr','docker-container://'+NAME,'build','--frontend','dockerfile.v0',
  '--local','context='+str(context),'--local','dockerfile='+str(context),
  '--output','type=oci,dest='+str(archive)],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=180)
with archive.open('rb') as stream:digest=hashlib.sha256(stream.read()).hexdigest()
value=dict(passed=True,builder_container=NAME,builder_container_id=container_id,pinned_image=image,source_registry_identity=source,
 state_path=str(state),ssd_space_observed=space,visible_devices_check=visible,
 device_requests=container['HostConfig'].get('DeviceRequests'),privileged=False,gpu_devices_visible=False,
 resources=dict(cpus=4,memory_bytes=16*1024**3),native_client=str(binpath),native_client_sha256=hashlib.sha256(binpath.read_bytes()).hexdigest(),
 native_oci_export=dict(path=str(archive),sha256=digest,bytes=archive.stat().st_size),
 daemon_configuration_changed=False,default_builder_changed=False,teacher_backend_changed=False,
 model_calls=0,new_gpu_processes=0,benchmark_environments_claimed_ready=0,
 upstream_protocol='https://github.com/moby/buildkit/blob/master/docs/rootless.md')
(R/'checks/ssd-buildkit17-rootless-r2-acceptance.json').write_text(json.dumps(value,indent=2));print(json.dumps(value))
