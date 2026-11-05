"""Build an exact preregistered native TMax context on owned17 SSD. No teacher."""
from pathlib import Path
import datetime,hashlib,json,os,re,shutil,stat,subprocess,sys,tarfile,time
R=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
CAMPAIGN=R/'configs/campaign-build17-r17.json'
campaign=json.loads(CAMPAIGN.read_text())
S=Path(campaign['native_context_root'])
for name in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(name,None)
# Buildctl fetches registry authentication in its client session as well.
os.environ['HTTP_PROXY']=os.environ['HTTPS_PROXY']='http://127.0.0.1:7890'
ident=sys.argv[1]
if not ident.startswith('task_') or not ident.replace('_','').isalnum():raise ValueError('Invalid frozen TaskID')
expected_manifest_sha256=sys.argv[2] if len(sys.argv)==3 else '35628e5d83b46384f5d53abb4b2603c7bba1e807ea04e718653a59df2726c6fd'
if not re.fullmatch('[0-9a-f]{64}',expected_manifest_sha256):raise ValueError('Invalid explicit registered manifest SHA256')
meta=S/'contexts'/(ident+'.context.json');source=json.loads(meta.read_text());context=S/'contexts'/ident
if source['source_manifest_sha256']!=expected_manifest_sha256 or source['source_revision']!='e3ded940596cc611c9815684ba51a7e8ee0cffc9':raise ValueError('Source scope changed')
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
files=[dict(path=str(p.relative_to(context)),mode=stat.S_IMODE(p.stat().st_mode),sha256=sha(p)) for p in sorted(context.rglob('*')) if p.is_file()]
if files!=source['build_context_files'] or hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()!=source['build_context_sha256']:raise ValueError('Native context bytes/modes differ')
acceptance=Path(campaign['native_build_service_acceptance']);deployment=json.loads(acceptance.read_text());assert deployment['passed']
if sha(acceptance)!=campaign['native_build_service_acceptance_sha256']:raise ValueError('Accepted private builder deployment changed')
if deployment['builder_engine_id']!=campaign['runtime_engine_id']:raise ValueError('Build and Task runtime Engine identity differ')
if sha(deployment['deployment']['native_buildctl'])!=deployment['deployment']['native_buildctl_sha256']:raise ValueError('Accepted native buildctl changed')
os.environ['DOCKER_CONFIG']=deployment['deployment']['docker_client_config'];os.environ.pop('DOCKER_HOST',None)
engine=subprocess.run(['docker','--context',deployment['deployment']['docker_context'],'info','--format','{{.ID}}'],check=True,capture_output=True,text=True).stdout.strip()
if engine!=deployment['builder_engine_id']:raise ValueError('Explicit private build context Engine changed')
dest=S/'archives'/ident/'client-proxy-r3';dest.mkdir(parents=True,exist_ok=True);receipt=dest/'build.json'
if receipt.exists():raise FileExistsError('Observe frozen build receipt, never overwrite')
if shutil.disk_usage(S).free<100*1024**3:raise RuntimeError('SSD headroom below100GiB')
archive=dest/'image.oci.tar';metadata=dest/'buildctl-metadata.json'
command=[str(R/'tools/buildkit-rootless-r2/buildctl'),'--addr',deployment['buildctl_address'],
 'build','--frontend','dockerfile.v0','--local','context='+str(context),'--local','dockerfile='+str(context),
 '--opt','platform=linux/amd64','--opt','label:rsi.campaign=qwen35-new-cf500-tmax500-20261029',
 '--opt','build-arg:HTTP_PROXY='+deployment['deployment']['public_dependency_proxy']['bridge'],'--opt','build-arg:HTTPS_PROXY='+deployment['deployment']['public_dependency_proxy']['bridge'],
 '--output','type=oci,name=rsi-ssd-tmax-r2:'+ident+',dest='+str(archive),'--metadata-file',str(metadata)]
start=time.monotonic();record=dict(task_id=ident,source_context=source,context_receipt_sha256=sha(meta),
 expected_source_manifest_sha256=expected_manifest_sha256,builder_source_sha256=sha(Path(__file__)),
 campaign_build_deployment=str(CAMPAIGN),campaign_build_deployment_sha256=sha(CAMPAIGN),
 builder_acceptance_sha256=sha(acceptance),builder_engine_id=engine,private_buildkit_container=deployment['deployment']['buildkit_container'],docker_context=deployment['deployment']['docker_context'],command=command,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
