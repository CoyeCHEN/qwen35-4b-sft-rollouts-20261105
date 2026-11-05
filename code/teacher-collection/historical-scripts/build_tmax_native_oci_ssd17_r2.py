"""Build an exact preregistered native TMax context on owned17 SSD. No teacher."""
from pathlib import Path
import datetime,hashlib,json,os,shutil,stat,subprocess,sys,tarfile,time
R=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/buildkit-rootless-r2')
for name in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(name,None)
ident=sys.argv[1]
if not ident.startswith('task_') or not ident.replace('_','').isalnum():raise ValueError('Invalid frozen TaskID')
meta=S/'contexts'/(ident+'.context.json');source=json.loads(meta.read_text());context=S/'contexts'/ident
if source['source_manifest_sha256']!='35628e5d83b46384f5d53abb4b2603c7bba1e807ea04e718653a59df2726c6fd' or source['source_revision']!='e3ded940596cc611c9815684ba51a7e8ee0cffc9':raise ValueError('Source scope changed')
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
files=[dict(path=str(p.relative_to(context)),mode=stat.S_IMODE(p.stat().st_mode),sha256=sha(p)) for p in sorted(context.rglob('*')) if p.is_file()]
if files!=source['build_context_files'] or hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()!=source['build_context_sha256']:raise ValueError('Native context bytes/modes differ')
acceptance=R/'checks/ssd-buildkit17-rootless-r2-acceptance.json';assert json.loads(acceptance.read_text())['passed']
dest=S/'archives'/ident;dest.mkdir(parents=True,exist_ok=True);receipt=dest/'build.json'
if receipt.exists():raise FileExistsError('Observe frozen build receipt, never overwrite')
if shutil.disk_usage(S).free<100*1024**3:raise RuntimeError('SSD headroom below100GiB')
archive=dest/'image.oci.tar';metadata=dest/'buildctl-metadata.json'
command=[str(R/'tools/buildkit-rootless-r2/buildctl'),'--addr','docker-container://rsi-cftmax-buildkit-rootless-r2',
 'build','--frontend','dockerfile.v0','--local','context='+str(context),'--local','dockerfile='+str(context),
 '--opt','platform=linux/amd64','--opt','label:rsi.campaign=qwen35-new-cf500-tmax500-20261029',
 '--opt','build-arg:HTTP_PROXY=http://127.0.0.1:7890','--opt','build-arg:HTTPS_PROXY=http://127.0.0.1:7890',
 '--output','type=oci,name=rsi-ssd-tmax-r2:'+ident+',dest='+str(archive),'--metadata-file',str(metadata)]
start=time.monotonic();record=dict(task_id=ident,source_context=source,context_receipt_sha256=sha(meta),
 builder_acceptance_sha256=sha(acceptance),command=command,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 model_calls=0,environment_ready=False,teacher_backend_changed=False)
try:
 with (dest/'build.log').open('x') as log:
  subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT,timeout=3600)
 with tarfile.open(archive,'r') as tar:
  index=json.loads(tar.extractfile('index.json').read());assert len(index['manifests'])==1
  descriptor=index['manifests'][0];digest=descriptor['digest'];raw=tar.extractfile('blobs/sha256/'+digest.split(':')[1]).read()
  assert hashlib.sha256(raw).hexdigest()==digest.split(':')[1];manifest=json.loads(raw)
  for item in [manifest['config'],*manifest['layers']]:
   h=hashlib.sha256()
   with tar.extractfile('blobs/sha256/'+item['digest'].split(':')[1]) as f:
    for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
   assert h.hexdigest()==item['digest'].split(':')[1]
  config=json.loads(tar.extractfile('blobs/sha256/'+manifest['config']['digest'].split(':')[1]).read())
  assert config['config']['Labels']['rsi.campaign']=='qwen35-new-cf500-tmax500-20261029'
 record.update(status='ORIGINAL_NATIVE_OCI_ARCHIVE_BUILT_INITIAL_AND_VERIFIER_TESTS_PENDING',archive=str(archive),archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,
  native_manifest_digest=digest,config_digest=manifest['config']['digest'],all_manifest_config_layer_hashes_verified=True)
except (OSError,ValueError,AssertionError,subprocess.SubprocessError) as error:
 record.update(status='NATIVE_SSD_BUILD_FAILED',error_type=type(error).__name__,error=str(error))
record['seconds']=time.monotonic()-start
receipt.write_text(json.dumps(record,indent=2));print(json.dumps(record))
if record['status']=='NATIVE_SSD_BUILD_FAILED':raise SystemExit(1)
