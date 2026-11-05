"""Owned SSD Docker-in-Docker bootstrap; never edits the shared daemon."""
import datetime,hashlib,json,os,subprocess,time
from pathlib import Path

R=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/engine17-r1')
HELPER='quay.io/skopeo/stable@sha256:ad1d2e25cf0234bb50476e753a8fc9debd4f0582cdd2ab6fd7bad9bacdfe3b9b'
SOURCE='docker.io/library/docker:29.9.2-dind'
NAME='rsi-cftmax-ssd-engine17-r1'
def run(args,timeout=120,**kwargs):return subprocess.run(args,capture_output=True,text=True,check=True,timeout=timeout,**kwargs)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def freeze(p,value):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:f.write(json.dumps(value,indent=2))
def state(stage,**kwargs):
 p=R/'checks/private-ssd-engine17-r1.json';tmp=p.with_suffix('.tmp')
 tmp.write_text(json.dumps(dict(status=stage,pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),model_calls=0,shared_daemon_configuration_changes=0,**kwargs),indent=2));tmp.replace(p)
def main():
 S.mkdir(mode=0o700,parents=True,exist_ok=False)
 before=run(['docker','info','--format','{{json .}}']);shared=json.loads(before.stdout)
 assert shared['ID']=='9e09f846-3672-4739-b45b-2eb4330320d1'
 freeze(S/'PLAN.json',dict(source=SOURCE,source_sha256=sha(Path(__file__)),shared_engine_before=dict(id=shared['ID'],docker_root_dir=shared['DockerRootDir']),
  mechanism='Official dedicated Docker-in-Docker engine, own namespace and SSD bind mounts; private Unix socket only',
  bootstrap_parent_privileged=True,task_containers_privileged=False,model_calls=0,rootless_not_selected='Missing uidmap binaries and no delegated CPU controller; original CPU enforcement must be proven'))
 base=['docker','run','--rm','--network','host','--user',str(os.getuid())+':'+str(os.getgid()),'--env','HTTP_PROXY=http://127.0.0.1:7890','--env','HTTPS_PROXY=http://127.0.0.1:7890','--volume',str(S)+':/work',HELPER]
 state('RESOLVING_OFFICIAL_BOOTSTRAP_IMAGE')
 raw=run(base+['inspect','--raw','docker://'+SOURCE],timeout=120).stdout
 (S/'source-index.json').write_text(raw);index=json.loads(raw)
 if 'manifests' in index:
  choices=[x for x in index['manifests'] if x.get('platform',{}).get('os')=='linux' and x.get('platform',{}).get('architecture')=='amd64']
  selected,=choices;digest=selected['digest']
 else:digest='sha256:'+hashlib.sha256(raw.encode()).hexdigest()
 pinned='docker.io/library/docker@'+digest
 freeze(S/'PINNED_SOURCE.json',dict(source=SOURCE,pinned=pinned,selected_manifest_digest=digest))
 state('COPYING_PINNED_BOOTSTRAP_IMAGE_TO_SSD',pinned=pinned)
 with (S/'bootstrap-copy.log').open('x') as log:
  subprocess.run(base+['copy','--preserve-digests','docker://'+pinned,'oci-archive:/work/bootstrap.oci.tar:rsi-cftmax-dind17-r1'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
 archive=S/'bootstrap.oci.tar';freeze(S/'BOOTSTRAP_ARCHIVE.json',dict(archive=str(archive),archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,pinned=pinned))
 state('LOADING_BOUNDED_BOOTSTRAP_PARENT_ONLY',bootstrap_archive_bytes=archive.stat().st_size)
 with (S/'bootstrap-load.log').open('x') as log:
  subprocess.run(['docker','image','load','--input',str(archive)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
 info=json.loads(run(['docker','image','inspect',digest]).stdout)[0]
 for name in ['docker','containerd','socket','config','logs']:(S/name).mkdir(mode=0o700)
 configuration={'hosts':['unix:///campaign-socket/docker.sock'],'data-root':'/var/lib/docker','exec-root':'/run/campaign-dockerd','pidfile':'/run/campaign-dockerd.pid',
  'features':{'containerd-snapshotter':True},'bip':'10.242.255.1/24','default-address-pools':[{'base':'10.242.0.0/16','size':24}],
  'log-driver':'local','log-opts':{'max-size':'20m','max-file':'2'}}
 freeze(S/'config/daemon.json',configuration)
 command=['docker','run','-d','--name',NAME,'--label','rsi.campaign='+R.name,'--runtime','runc','--privileged','--restart','unless-stopped','--log-driver','none',
  '--mount','type=bind,src='+str(S/'docker')+',dst=/var/lib/docker',
  '--mount','type=bind,src='+str(S/'containerd')+',dst=/var/lib/containerd',
  '--mount','type=bind,src='+str(S/'socket')+',dst=/campaign-socket',
  '--mount','type=bind,src='+str(S/'config')+',dst=/campaign-config,readonly',
  '--mount','type=bind,src='+str(S/'logs')+',dst=/campaign-logs',
  '--tmpfs','/run','--tmpfs','/tmp','--env','DOCKER_TLS_CERTDIR=',
  '--entrypoint','/bin/sh',info['Id'],'-c','exec dockerd --config-file /campaign-config/daemon.json >> /campaign-logs/dockerd.log 2>&1']
 freeze(S/'PARENT_COMMAND.json',dict(command=command,bootstrap_image_id=info['Id'],bounded_shared_system_bootstrap_image_bytes=info['Size']))
 state('STARTING_OWN_SSD_ENGINE',bootstrap_image_id=info['Id'])
 parent=run(command).stdout.strip()
 host='unix://'+str(S/'socket/docker.sock')
 for _ in range(120):
  if (S/'socket/docker.sock').exists():
   run(['docker','exec',NAME,'sh','-c','chgrp '+str(os.getgid())+' /campaign-socket/docker.sock && chmod 660 /campaign-socket/docker.sock'])
   reply=subprocess.run(['docker','--host',host,'info','--format','{{json .}}'],capture_output=True,text=True,timeout=10)
   if reply.returncode==0:break
  time.sleep(1)
 else:raise RuntimeError('Dedicated engine did not become ready; retain own logs, do not alter shared daemon')
 dedicated=json.loads(reply.stdout)
 after=json.loads(run(['docker','info','--format','{{json .}}']).stdout)
 assert after['ID']==shared['ID'] and after['DockerRootDir']==shared['DockerRootDir']
 assert dedicated['ID']!=shared['ID']
 mounts=json.loads(run(['docker','inspect',NAME]).stdout)[0]['Mounts']
 accepted=dict(status='PRIVATE_SSD_ENGINE_READY_NATIVE_RESOURCES_AND_TASK_ACCEPTANCE_PENDING',node='17',engine_id=dedicated['ID'],socket=host,
  parent_container_id=parent,parent_name=NAME,parent_bootstrap_privileged=True,daemon_root_inside=dedicated['DockerRootDir'],mounts=mounts,
  shared_engine_unchanged=True,shared_engine_id=after['ID'],bootstrap_parent_image_bytes=info['Size'],model_calls=0)
 freeze(S/'ENGINE_READY.json',accepted);state(accepted['status'],engine_id=dedicated['ID'],socket=host)
 print(json.dumps(accepted),flush=True)

if __name__=='__main__':
 for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY','DOCKER_HOST','DOCKER_CONTEXT']:os.environ.pop(key,None)
 try:main()
 except Exception as error:
  state('PRIVATE_ENGINE_PREPARATION_FAILED',error_type=type(error).__name__,reason=str(error)[:1600]);raise
