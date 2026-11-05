"""Leaf phase for the existing unique advance; not a controller or scheduler."""
import json,os,pathlib,shlex,subprocess,time,urllib.request
from environment_evidence_audit_r3 import read,write,sha
R=pathlib.Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'environment-preflight30';C=pathlib.Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
A='/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101';CACHE=A+'/public-verifier-cache/torch270-cp313-r1'
CONFIG=dict(revision='public-torch-cache-phase18-r1',ssh=['ssh','-p','18449','chenkeyi@127.0.0.1'],private_client_bin=str(R/'formal-controller18-client-bin-r1'),
 warm_unit='qwen35-public-torch270-dependency-warm-20261102-r2.service',seal_unit='qwen35-public-torch270-dependency-seal-20261102-r1.service',
 warm_receipt=CACHE+'/SEALED_CACHE_CURRENT.json',archive_receipt=CACHE+'/PUBLIC_DEPENDENCY_ARCHIVE_READY_R1.json',remote_seal_dispatch=CACHE+'/SEAL_DISPATCH_R1.json',
 warm_script=A+'/public-verifier-cache/scripts/warm-public-torch270-cache149-r2.py',warm_script_sha256='26ab5ecf45669776da23645aca77c806d85a1f5b4a6293d20f3e593cd98c6fc7',
 seal_script=A+'/public-verifier-cache/scripts/seal-public-verifier-cache149-r1.py',seal_script_sha256='6b05ea55ccb023fa823c99c218d130afa3f9f5f54043eb0a4ff04205c6ce45a5',
 materializer=A+'/scripts/materialize-public-verifier-cache149-r1.py',materializer_sha256='1c978bd48398183cf3cab1d7ee7cbf9573d72f9bf287032706c0be26d0f04b41',
 worker='run-env-preflight30-recheck18-r4.py',worker_sha256='bbc28585146409568fe728bcc17cc06bd4dda00755d4114cddbd6c33f9421610',
 runtime_spec=str(B/'public-cache-recheck-r4/specs/torch-tensor-parallelism.json'),runtime_spec_sha256='cf0c23a0e4b9c17e1d6b67796df65e6d1c82d4c5709d1311c6863f2aa13265e0',
 image_id='sha256:c50ac169e11465f41b49749fe87e4487f24d31a0c39c0906cd3242cc5499c690',engine_id='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5',uv_archive_sha256='2cf10babba653310606f8b49876cfb679928669e7ddaa1fb41fb00ce73e64f66')
OBSERVE=r'''import pathlib,json,hashlib,subprocess
c=json.loads(__import__('sys').argv[1])
def h(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def unit(name):return dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',name,'-p','LoadState','-p','ActiveState','-p','MainPID','-p','Result'],text=True,timeout=5).splitlines())
v=dict(warm_unit=unit(c['warm_unit']),seal_unit=unit(c['seal_unit']),script_sha256={})
for key in ['warm_script','seal_script','materializer']:
 p=pathlib.Path(c[key]);v['script_sha256'][key]=h(p)if p.exists()else None
for key in ['warm_receipt','archive_receipt','remote_seal_dispatch']:
 p=pathlib.Path(c[key]);v[key]=json.loads(p.read_text())if p.exists()else None;v[key+'_sha256']=h(p)if p.exists()else None
if v['warm_receipt']:
 w=v['warm_receipt'];v['warm_file_manifest_sha256']=h(w['file_manifest']);root=pathlib.Path(w['root']);prep=root/'PUBLIC_PREPARATION.json';v['public_preparation']=json.loads(prep.read_text());v['public_preparation_sha256']=h(prep)
print(json.dumps(v))'''
SEAL=r'''import pathlib,json,hashlib,subprocess,time
c=json.loads(__import__('sys').argv[1]);owner=json.loads(__import__('sys').argv[2]);p=pathlib.Path(c['remote_seal_dispatch']);source=pathlib.Path(c['seal_script']);assert hashlib.sha256(source.read_bytes()).hexdigest()==c['seal_script_sha256']
if p.exists():print(json.dumps(dict(already_registered=True,receipt=json.loads(p.read_text()))));raise SystemExit(0)
with p.open('x')as stream:stream.write(json.dumps(dict(at=time.time(),unique_controller_owner=owner,unit=c['seal_unit'],source_sha256=c['seal_script_sha256'],registered_once_before_dispatch=True),indent=2)+'\n')
log=pathlib.Path(c['seal_script']).parent.parent/'logs/seal-torch270-r1.log';log.parent.mkdir(exist_ok=True)
command=['systemd-run','--user','--unit='+c['seal_unit'],'--property=MemoryMax=8G','--property=CPUQuota=100%','--property=StandardOutput=append:'+str(log),'--property=StandardError=append:'+str(log),'/usr/bin/python3',c['seal_script']]
r=subprocess.run(command,capture_output=True,text=True,timeout=10);print(json.dumps(dict(returncode=r.returncode,stderr=r.stderr[-1000:],receipt=str(p))));r.check_returncode()'''
def remote(code,*args):
 env=dict(os.environ);env['PATH']=CONFIG['private_client_bin']+':'+env['PATH'];command=['python3','-c',code,*args]
 result=subprocess.run(CONFIG['ssh']+[shlex.join(command)],capture_output=True,text=True,timeout=25,env=env);result.check_returncode();return json.loads(result.stdout)
def advance(owner,state,launch):
 value=dict(at=time.time(),status='PUBLIC_DEPENDENCIES_DOWNLOADING',warm_and_seal_are_not_task_pass=True,model_generation_calls=0)
 state['public_torch_cache']=value
 try:
  assert read(C/'NATIVE_ADVANCE_OWNER.json')==owner
  observed=remote(OBSERVE,json.dumps(CONFIG));value['observed']=observed
  assert observed['script_sha256']['warm_script']==CONFIG['warm_script_sha256'],'Warm source SHA mismatch'
  warm=observed['warm_receipt']
  if warm is None:
   if observed['warm_unit']['ActiveState']=='failed':value.update(status='PUBLIC_WARM_FAILED',blocker=observed['warm_unit'])
   return
  assert warm['ready_public_cache']and warm['engine_id']==CONFIG['engine_id']and warm['image_id']==CONFIG['image_id']
  assert warm['uv_version']=='uv 0.9.5'and warm['python_version'].startswith('3.13.9')
  assert observed['warm_file_manifest_sha256']==warm['file_manifest_sha256']and observed['public_preparation_sha256']==warm['preparation_sha256']
  prep=observed['public_preparation'];assert prep['pins']==['pytest==8.4.1','torch==2.7.0','pytest-json-ctrf==0.3.5']and prep['uv_archive_sha256']==CONFIG['uv_archive_sha256']
  assert observed['script_sha256']['seal_script']==CONFIG['seal_script_sha256'],'Seal source SHA mismatch'
  assert observed['script_sha256']['materializer']==CONFIG['materializer_sha256'],'Materializer source SHA mismatch'
  archive=observed['archive_receipt']
  if archive is None:
   receipt=B/'PUBLIC_TORCH_SEAL_DISPATCH_REQUEST_R1.json';value['status']='PUBLIC_CACHE_SEAL_REGISTERED_OR_RUNNING'
   if not receipt.exists():
    write(receipt,dict(at=time.time(),owner=owner,config=CONFIG,remote_warm_receipt_sha256=observed['warm_receipt_sha256'],registered_once_before_remote_dispatch=True))
    response=remote(SEAL,json.dumps(CONFIG),json.dumps(owner));write(B/'PUBLIC_TORCH_SEAL_DISPATCH_ACK_R1.json',dict(at=time.time(),response=response))
   elif observed['seal_unit']['ActiveState']=='failed':value.update(status='PUBLIC_CACHE_SEAL_FAILED',blocker=observed['seal_unit'])
   elif observed['seal_unit']['LoadState']=='not-found'and observed['remote_seal_dispatch']is None:value.update(status='PUBLIC_CACHE_SEAL_DISPATCH_UNKNOWN_NO_REPLAY')
   return
  assert archive['public_cache_receipt_sha256']==observed['warm_receipt_sha256']and archive['file_manifest_sha256']==warm['file_manifest_sha256']
  assert archive['archive_source_read_only']and archive['contains_only_public_dependency_cache_and_managed_python']and not archive['contains_task_tests_solution_oracle']
  spec=pathlib.Path(CONFIG['runtime_spec']);assert sha(spec)==CONFIG['runtime_spec_sha256'];endpoints=read(spec)['model_endpoints'];assert len(endpoints)==8
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));services=[]
  for item in endpoints:
   port=int(item['url'].split(':')[-1].split('/')[0])
   with opener.open('http://127.0.0.1:'+str(port)+'/model_info',timeout=3)as response:live=json.load(response)
   assert live['model_path']==item['model_path']and live['weight_version']==item['weight_version'],('Serving role not ready',port)
   services.append(dict(port=port,model_info=live))
  binding=dict(archive_receipt_sha256=observed['archive_receipt_sha256'],archive_sha256=archive['archive_sha256'],materializer_sha256=CONFIG['materializer_sha256'],remote_materializer_path=CONFIG['materializer'],runtime_spec_path=CONFIG['runtime_spec'],runtime_spec_sha256=CONFIG['runtime_spec_sha256'],warm_receipt_sha256=observed['warm_receipt_sha256'],seal_source_sha256=CONFIG['seal_script_sha256'])
  path=B/'PUBLIC_VERIFIER_CACHE_BINDING_R1.json'
  if path.exists():assert read(path)==binding,'Existing frozen public cache binding changed'
  else:write(path,binding)
  proof=B/'PUBLIC_TORCH_CACHE_SERVING_READY_R1.json'
  if not proof.exists():write(proof,dict(at=time.time(),owner=owner,services=services,config=CONFIG,binding_sha256=sha(path),warm_receipt=warm,archive_receipt=archive))
  assert sha(R/CONFIG['worker'])==CONFIG['worker_sha256']
  dispatch=B/'PUBLIC_TORCH_NOP_R4_DISPATCH_REQUEST_R1.json';value['status']='PUBLIC_CACHE_READY_NATIVE_TORCH_NOP_REGISTERED'
  if not dispatch.exists():
   write(dispatch,dict(at=time.time(),owner=owner,binding_sha256=sha(path),source_sha256=CONFIG['worker_sha256'],registered_once_before_native_launch=True))
   result=launch('qwen35-env-preflight30-native-recheck-20261102-r4.service',CONFIG['worker'],[],B/'RECHECK_ADMISSION_R4.json',owner,dict(tasks=['torch-tensor-parallelism'],public_cache_archive_receipt_sha256=observed['archive_receipt_sha256'],public_cache_materializer_sha256=CONFIG['materializer_sha256'],public_cache_runtime_spec_sha256=CONFIG['runtime_spec_sha256']))
   write(B/'PUBLIC_TORCH_NOP_R4_DISPATCH_ACK_R1.json',dict(at=time.time(),native_launch=result))
  value['binding_sha256']=sha(path)
 except Exception as error:value.update(status='PUBLIC_TORCH_CACHE_REQUIRES_INSPECTION',blocker=repr(error))
