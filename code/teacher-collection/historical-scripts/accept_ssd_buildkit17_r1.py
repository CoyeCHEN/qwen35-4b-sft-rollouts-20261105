"""Accept one owned native Buildx builder with its state on17 SSD. No teacher."""
from pathlib import Path
import hashlib,json,os,shlex,subprocess
R=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/buildkit-r1')
NAME='rsicftmax17r1';NODE='rsicftmax17r1node';VOLUME='buildx_buildkit_'+NODE+'_state'
for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
def run(args,**kw):return subprocess.run(args,check=True,capture_output=True,text=True,**kw)
assert run(['docker','info','--format','{{.ID}}']).stdout.strip()=='9e09f846-3672-4739-b45b-2eb4330320d1'
source=json.loads((R/'checks/ssd-buildkit17-r1-pinned-image.json').read_text());image=source['pinned']
S.mkdir(parents=True,exist_ok=True);assert S.stat().st_uid==os.getuid()
state=S/'state';state.mkdir(exist_ok=True)
if subprocess.run(['docker','buildx','inspect',NAME],capture_output=True).returncode==0:raise FileExistsError('Observe existing builder; never recreate')
if subprocess.run(['docker','volume','inspect',VOLUME],capture_output=True).returncode==0:raise FileExistsError('Existing volume requires ownership audit')
run(['docker','volume','create','--name',VOLUME,'--label','rsi.campaign=qwen35-new-cf500-tmax500-20261029','--opt','type=none','--opt','o=bind','--opt','device='+str(state)],timeout=30)
run(['docker','buildx','create','--name',NAME,'--node',NODE,'--driver','docker-container',
 '--driver-opt','image='+image,'--driver-opt','network=host','--driver-opt','memory=16g',
 '--driver-opt','cpu-quota=400000','--driver-opt','cpu-period=100000',
 '--driver-opt','env.HTTP_PROXY=http://127.0.0.1:7890','--driver-opt','env.HTTPS_PROXY=http://127.0.0.1:7890',
 '--driver-opt','env.NO_PROXY=localhost','--driver-opt','default-load=false'],timeout=30)
bootstrap=run(['docker','buildx','inspect','--bootstrap',NAME],timeout=180)
container=json.loads(run(['docker','inspect','buildx_buildkit_'+NODE]).stdout)[0]
volume=json.loads(run(['docker','volume','inspect',VOLUME]).stdout)[0]
assert volume['Options']==dict(device=str(state),o='bind',type='none')
assert volume['Labels']['rsi.campaign']=='qwen35-new-cf500-tmax500-20261029'
assert any(m['Destination']=='/var/lib/buildkit' and m.get('Name')==VOLUME for m in container['Mounts'])
assert not container['HostConfig'].get('DeviceRequests')
space=run(['docker','exec',container['Id'],'df','-B1','/var/lib/buildkit'],timeout=30).stdout
if '/dev/nvme0n1' not in space:raise ValueError('Builder state is not on selected SSD')
# Native exporter acceptance; synthetic marker is a diagnostic, never a Task.
context=S/'diagnostic-context';context.mkdir(exist_ok=True)
(context/'Dockerfile').write_text('FROM scratch\nCOPY marker /rsi-ssd-buildkit-acceptance\n')
(context/'marker').write_text('Native SSD BuildKit exporter probe; no benchmark task, no model, no oracle.\n')
archive=S/'diagnostic-image.oci.tar'
if archive.exists():raise FileExistsError('Do not overwrite an accepted exporter artifact')
with (R/'logs/ssd-buildkit17-r1-exporter.log').open('x') as log:
 subprocess.run(['docker','buildx','build','--builder',NAME,'--provenance=false','--progress=plain',
  '--output','type=oci,dest='+str(archive),str(context)],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=120)
with archive.open('rb') as stream:archive_sha=hashlib.sha256(stream.read()).hexdigest()
value=dict(passed=True,builder=NAME,node=NODE,pinned_builder_image=image,builder_container_id=container['Id'],
 builder_image_id=container['Image'],state_volume=volume,ssd_space_observed=space,
 resources=dict(cpus=4,memory_bytes=16*1024**3),default_builder_not_changed=True,daemon_configuration_changed=False,
 native_oci_export=dict(path=str(archive),bytes=archive.stat().st_size,sha256=archive_sha),
 source_registry_identity=source,model_calls=0,benchmark_environments_claimed_ready=0,new_gpu_processes=0,
 scope='Native builder/exporter only; original task build and149 runtime acceptance still required')
(R/'checks/ssd-buildkit17-r1-acceptance.json').write_text(json.dumps(value,indent=2));print(json.dumps(value))
