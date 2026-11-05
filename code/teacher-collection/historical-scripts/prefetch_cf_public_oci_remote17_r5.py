"""Finite CF500 public-image preparation directly on17 SSD; no teacher dispatch."""
from collections import Counter
import argparse,datetime,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
from verify_public_oci import verify,file_sha
R=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/registry')
IMAGE='quay.io/skopeo/stable@sha256:ad1d2e25cf0234bb50476e753a8fc9debd4f0582cdd2ab6fd7bad9bacdfe3b9b'
for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--task-id');args=ap.parse_args()
planfile=R/'manifests/CF_PUBLIC_OCI_REMOTE17_R5.json';plan=json.loads(planfile.read_text());rows=plan['tasks']
assert len(rows)==500 and len({r['task_id'] for r in rows})==500
if args.task_id:
 rows=[r for r in rows if r['task_id']==args.task_id];assert len(rows)==1
rows.sort(key=lambda r:(r['source'].get('compressed_layer_bytes',0),r['task_id']))
label='cf-public17-r5-'+(args.task_id or 'full');statefile=R/'checks'/(label+'.json')
if statefile.exists():raise FileExistsError('Observe existing finite pass; do not duplicate')
records=[]
for row in rows:
 ident=row['task_id'];source=row['source'];start=time.monotonic();name='rsi-cf-public17-r5-'+hashlib.sha256(ident.encode()).hexdigest()[:16]
 item=dict(task_id=ident,pinned=source['pinned'])
 try:
  ready=next((p for dirname in ['tasks-local-skopeo-r1','tasks'] if (p:=S/dirname/ident/'cache.json').exists()),None)
  if ready:
   cached=json.loads(ready.read_text());assert cached['pinned']==source['pinned'] and Path(cached['archive']).exists()
   item['status']='VERIFIED_PUBLIC_ARCHIVE_ALREADY_STAGED'
  elif ident in plan['existing149']:
   assert plan['existing149'][ident]==source['top_manifest_digest'];item['status']='SNAPSHOT_VERIFIED_IMAGE_ALREADY_PREPARED_149'
  else:
   if shutil.disk_usage(S).free<100*1024**3:raise RuntimeError('17 SSD headroom below100GiB')
   directory=S/'tasks-skopeo-container-r5'/ident;directory.mkdir(parents=True,exist_ok=True)
   (directory/'tmp').mkdir(exist_ok=True);(directory/'home').mkdir(exist_ok=True);archive=directory/'image.oci.tar'
   # Existing receipt may come from the explicit preflight on this same task.
   completed=directory/'cache.json'
   if completed.exists():
    value=json.loads(completed.read_text());assert value['pinned']==source['pinned'] and file_sha(archive)==value['archive_sha256']
   else:
    command=['docker','create','--name',name,'--label','rsi.campaign='+R.name,'--runtime','runc','--network','host',
     '--user',str(os.getuid())+':'+str(os.getgid()),'--cpus','1','--memory','1g',
     '--mount','type=bind,src='+str(directory)+',dst=/cache','--env','HOME=/cache/home','--env','TMPDIR=/cache/tmp',
     '--env','HTTP_PROXY=http://127.0.0.1:7890','--env','HTTPS_PROXY=http://127.0.0.1:7890',
     IMAGE,'copy','--preserve-digests','--retry-times','2','--src-no-creds','docker://docker.io/'+source['pinned'],
     'oci-archive:/cache/image.oci.tar:'+ident]
    container_id=subprocess.run(command,check=True,capture_output=True,text=True,timeout=30).stdout.strip()
    inspected=json.loads(subprocess.run(['docker','inspect',container_id],check=True,capture_output=True,text=True).stdout)[0]
    assert not inspected['HostConfig']['Privileged'] and not inspected['HostConfig'].get('DeviceRequests')
    with (directory/'copy.log').open('x') as log:
     subprocess.run(['docker','start','--attach',container_id],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
    final=json.loads(subprocess.run(['docker','inspect',container_id],check=True,capture_output=True,text=True).stdout)[0]
    if final['State']['ExitCode']!=0:raise RuntimeError('Native Skopeo container returned nonzero; preserved original log')
    value=verify(source,archive);value['archive']=str(archive)
    value.update(cache_transport='Native Skopeo1.22.3 official pinned container on17; direct existing17 public proxy; no local or149 bulk cache',
     helper_image=IMAGE,helper_gpu_device_requests=None,helper_privileged=False,task_manifest_sha256=plan['task_manifest_sha256'])
    with completed.open('x') as stream:stream.write(json.dumps(value,indent=2))
   target=S/'tasks-local-skopeo-r1'/ident/'cache.json';target.parent.mkdir(parents=True,exist_ok=True)
   if target.exists():assert json.loads(target.read_text())['pinned']==value['pinned']
   else:
    temporary=target.with_suffix('.publish-tmp');temporary.write_text(json.dumps(value,indent=2));temporary.replace(target)
   item.update(status='PINNED_PUBLIC_IMAGE_ARCHIVE_READY',archive_sha256=value['archive_sha256'],archive_bytes=value['archive_bytes'])
 except (OSError,ValueError,AssertionError,RuntimeError,subprocess.SubprocessError) as error:
  item.update(status='PUBLIC_ASSET_PREPARATION_FAILED',error_type=type(error).__name__,error=str(error)[:600])
 finally:
  try:
   cleanup=subprocess.run(['docker','rm','-f',name],capture_output=True,text=True,timeout=60)
   item['helper_cleanup_confirmed']=cleanup.returncode==0 or 'no such' in cleanup.stderr.casefold()
  except (OSError,subprocess.SubprocessError) as error:
   item.update(helper_cleanup_confirmed=False,helper_cleanup_error=str(error)[:400])
 item['seconds']=time.monotonic()-start;records.append(item)
 state=dict(status='PREPARING_SAME_CF500_PUBLIC_ARCHIVES_ON17',pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
  planned_tasks=len(rows),observed_tasks=len(records),counts=dict(Counter(x['status'] for x in records)),records=records,task_manifest_sha256=plan['task_manifest_sha256'],
  helper_image=IMAGE,local_bulk_downloads=0,teacher_backend_changes=0,model_calls=0)
 tmp=statefile.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2));tmp.replace(statefile)
 print(json.dumps(item),flush=True)
state['status']='FINITE_PUBLIC_ARCHIVE_PASS_TERMINAL';statefile.write_text(json.dumps(state,indent=2))
