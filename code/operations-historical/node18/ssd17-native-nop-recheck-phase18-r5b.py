"""Existing sole-controller leaf: one independent finite NOP after the passed runtime on SSD17."""
import hashlib
import json
import shlex
import subprocess
import time
from pathlib import Path

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
T='/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1'
CONFIG = {'root': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1',
 'ssh_config': '/ssd/chenkeyi/qwen35-sft-772-20261101/control-ssh/backend17-exec-r1.conf',
 'ssh_config_sha256': 'b49e8d3be67ef1f991ba278418620929ec2b7925000b726ef9e71c8bf3f2c84f',
 'known_hosts_sha256': 'f6aaf5bc483e7c6f6902be06c2cdc4dd6eea2af4f7e2e60c3ce07bbbe31d57ef',
 'ssh_alias': 'rsi-ssd17',
 'plan': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/NATIVE_SSD17_FIXGIT_NOP_PLAN_R5.json',
 'plan_sha256': 'be0ae752bce4da8e85dcdc40da5f4a7b5488d403e91ba4fa79cbf40e7709c876',
 'deployment': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/SSD17_BACKEND_DEPLOYMENT_R1.json',
 'deployment_sha256': '2da1abefed7fd9dd7ba72c2d0e903f869736a696d276cce9ee344aa3c1340a66',
 'image_ready': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/image-prewarm/fix-git/IMAGE_READY_R1.json',
 'image_source_sha256': '920b17f2161152a4a172e1ffa67d7a23740ae1c945855e883f0f9c03cdaad7ac',
 'engine_id': '59c8ba22-0aa4-4aed-bc43-4e1b5989fa22',
 'image_id': 'sha256:389b9c8247610c2c5be080b1ac00429007c2c69bf57f7f26c79f0f75ba2d5c74',
 'steps': {'runtime': {'unit': 'qwen35-ssd17-native-runtime-prepare-20261103-r1.service',
                       'script': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/prepare-native-ssd17-runtime-r1.py',
                       'source_sha256': '1e4114d354f2b936236e9a3e74d8dc2bd0bb5656a0509c38aa67759826904314',
                       'python': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/controller17-r1/python/cpython-3.12.3-linux-x86_64-gnu/bin/python3.12',
                       'admission': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/ROOT_RUNTIME_ADMISSION_ACTUAL_R1.json',
                       'intent': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/ROOT_RUNTIME_NATIVE_DISPATCH_R1.json',
                       'ack': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/ROOT_RUNTIME_NATIVE_SYSTEMD_ACK_R1.json',
                       'receipt': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/NATIVE_RUNTIME_CPU_READY_R1.json',
                       'receipt_kind': 'SSD17_NATIVE_RUNTIME_CPU_READY_R1',
                       'log': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/logs/runtime-native-r1.log',
                       'started_paths': ['/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/native-runtime-r1'],
                       'plan_sha256': 'a6feabcab2ecf0bc559ec267e5f616e3adb8cea63a0b0b3c28f9d2cb3cb78658'},
           'nop': {'unit': 'qwen35-ssd17-fixgit-native-nop-20261103-r5.service',
                   'script': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/run-native-ssd17-fixgit-nop-r5.py',
                   'source_sha256': '2b3a37ebf540d4a6d1f9678385d4998a52464b6e3717c19cee13bf30633d8886',
                   'python': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/native-runtime-r1/bin/python',
                   'admission': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/ROOT_NOP_ADMISSION_ACTUAL_R5.json',
                   'intent': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/ROOT_NOP_NATIVE_DISPATCH_R5.json',
                   'ack': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/ROOT_NOP_NATIVE_SYSTEMD_ACK_R5.json',
                   'receipt': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/nop-fixgit-r5/actual-run-r5/SSD17_FIXGIT_NATIVE_NOP_ACCEPTANCE_R5.json',
                   'receipt_kind': 'ACTUAL_SSD17_FIXGIT_NATIVE_NOP_ACCEPTANCE_R5',
                   'log': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/logs/nop-native-r5.log',
                   'started_paths': ['/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/nop-fixgit-r5/actual-run-r5',
                                     '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/nop-fixgit-r5/jobs/qwen35-ssd17-fixgit-newwheel5-nop-20261103-r5']}},
 'nop_metadata': {'actual_native_configs': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/nop-fixgit-r5/actual-run-r5/ACTUAL_NATIVE_TRIAL_R5.json',
                  'actual_nop_agent_start': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/nop-fixgit-r5/jobs/qwen35-ssd17-fixgit-newwheel5-nop-20261103-r5/fix-git__ssd17-newwheel5-nop-r5/ACTUAL_NATIVE_NOP_AGENT_START_R5.json',
                  'raw_result': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/nop-fixgit-r5/jobs/qwen35-ssd17-fixgit-newwheel5-nop-20261103-r5/fix-git__ssd17-newwheel5-nop-r5/result.json',
                  'worker_exception': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/nop-fixgit-r5/actual-run-r5/FINITE_WORKER_EXCEPTION_R5.json'},
 'runtime_receipt_sha256': '07d34731482c4695def1e56cd1cc17fbcdc3bb65c30d3370d755dbbdaab93921',
 'image_ready_sha256': '9ee167804d6c8c7ad974a6592cfdfabdee1a443e9c0f16ebd5fd4141e35791e5',
 'public_wheelhouses': {'cli_wheelhouse': {'root': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/cli-wheelhouse-cp313-r2/sealed/wheelhouse',
                                           'receipt_path': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/cli-wheelhouse-cp313-r2/sealed/CLI_WHEELHOUSE_READY_R2.json',
                                           'preparation_source_sha256': 'd941ffd787ec8c52199f64ace4438b9977720e2be9f4a8ca2832ae2368f6cd8f',
                                           'ready_kind': 'PUBLIC_CLI_WHEEL5_CP313_OFFICIAL_FILES_LOCAL_ACQUISITION_R2',
                                           'required_versions': {'anyio': '4.16.0',
                                                                 'attrs': '26.1.0',
                                                                 'beautifulsoup4': '4.15.0',
                                                                 'certifi': '2026.10.23',
                                                                 'h11': '0.16.0',
                                                                 'httpcore': '1.0.9',
                                                                 'httpx': '0.28.1',
                                                                 'idna': '3.20',
                                                                 'jsonschema': '4.26.0',
                                                                 'jsonschema-specifications': '2025.9.1',
                                                                 'markdownify': '1.2.3',
                                                                 'partial-json-parser': '0.2.1.1.post7',
                                                                 'pypdf': '6.21.4',
                                                                 'pyyaml': '6.0.3',
                                                                 'referencing': '0.37.0',
                                                                 'rpds-py': '2026.9.1',
                                                                 'six': '1.17.0',
                                                                 'soupsieve': '3.0.4',
                                                                 'typing-extensions': '4.16.0'},
                                           'container_target': '/opt/rsi-public-cli-wheels',
                                           'source_preparation_not_a_Task_PASS': True,
                                           'expected_receipt_sha256': 'c0c8d3062c2169a61f4a4003b2ab155c9d0966b4f426efe45b1084a30fab7ff0',
                                           'lock_sha256': '5b9c665eb090c313b2b9e0923427d9c60fb6647cc55b9a8619cd1b0e144616af',
                                           'transfer_receipt': {'path': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/cli-wheelhouse-cp313-r2/SOURCE_TARGET_SHA_TRANSFER_ACCEPTANCE_R2.json',
                                                                'sha256': 'ac6cd3f63dd1017af29ae60ce37b9fa44ce61ee5c9562a2373e0cef1055a8b49'}},
                        'verifier_wheelhouse': {'root': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/fixgit-verifier-wheelhouse-local-r1/sealed/wheelhouse',
                                                'receipt_path': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/fixgit-verifier-wheelhouse-local-r1/sealed/FIXGIT_VERIFIER_WHEELHOUSE_READY_R1.json',
                                                'preparation_source_sha256': 'ac881bdcf6d31fa354a090b73a5027338b792f247ececb813600aef85ee0cc9a',
                                                'ready_kind': 'FIXGIT_VERIFIER_WHEELHOUSE_READY_R1',
                                                'required_versions': {'pytest': '8.4.1',
                                                                      'pytest-json-ctrf': '0.3.5'},
                                                'container_target': '/opt/rsi-fixgit-verifier-cache/wheels',
                                                'source_preparation_not_a_Task_PASS': True,
                                                'expected_receipt_sha256': '398f34f4fbf2811a713a64502c4a60be48f10d52c7814a9e3bf62c49c4515d1e'}},
 'public_apt_cache': {'root': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/bookworm-public-apt-cache-r1/sealed', 'receipt_path': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/bookworm-public-apt-cache-r1/sealed/PUBLIC_BOOKWORM_APT_CACHE_READY_R1.json', 'expected_receipt_sha256': '380887f06d148f9b51a5df2d7c5bd6b0805309e8460250ba772196e35517e7a0', 'seal_source_sha256': '493a176dc22a4aa7d0bf1381b06e3d6da24552afcb2094488a184465e3dfcf61', 'acquisition_source_sha256': 'e68c43f66b9935b4cf722235b3afd09b3b90902fddd80e9e165f570e05e9c421', 'transfer_receipt': {'path': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/bookworm-public-apt-cache-r1/SOURCE_TARGET_SHA_TRANSFER_ACCEPTANCE_R1.json', 'sha256': '83514511f253424cf58f2fc243e4104419604684487e19fca7329a517be2a981'}, 'materializer': {'path': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/materialize_public_bookworm_apt_cache_r1.py', 'sha256': '216c13525dcd693ed657357e5e50f2fa73cf23e4da0b15317a651e785cc4b1c0'}, 'read_only_target': '/opt/rsi-public-bookworm-apt-cache', 'source_keyring_and_dpkg_status_not_overwritten': True, 'original_APT_update_install_and_cleanup_hooks_preserved': True, 'no_fully_offline_success_claim': True},
 'public_uv_archive': {'path': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/uv095-public-release-r1/uv-x86_64-unknown-linux-gnu.tar.gz',
                       'bytes': 21370871,
                       'sha256': '2cf10babba653310606f8b49876cfb679928669e7ddaa1fb41fb00ce73e64f66',
                       'source149_path': '/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/public-verifier-cache/torch270-cp313-r1/tools/uv-0.9.5-linux-x64.tar.gz',
                       'source_readonly_receipt_sha256': '2ba01f00f840ac0127dbc7759b707f9cc5b489a31b0198771760facc579fe8c8'}}
TEMPLATES = {'runtime': {'frozen': False,
             'admitted': False,
             'operation': 'PREPARE_SSD17_NATIVE_RUNTIME_R1',
             'source_sha256': '1e4114d354f2b936236e9a3e74d8dc2bd0bb5656a0509c38aa67759826904314',
             'plan_sha256': 'a6feabcab2ecf0bc559ec267e5f616e3adb8cea63a0b0b3c28f9d2cb3cb78658',
             'unique_controller_node': '18',
             'unique_controller_owner': None,
             'limits': {'native_jobs': 0,
                        'native_trials': 0,
                        'concurrency': 0,
                        'model_generation_calls': 0},
             'required_evidence': {}},
 'nop': {'frozen': False,
         'admitted': False,
         'operation': 'NATIVE_FIXGIT_SSD17_NOP_R5',
         'source_sha256': '2b3a37ebf540d4a6d1f9678385d4998a52464b6e3717c19cee13bf30633d8886',
         'plan_sha256': 'be0ae752bce4da8e85dcdc40da5f4a7b5488d403e91ba4fa79cbf40e7709c876',
         'unique_controller_node': '18',
         'unique_controller_owner': None,
         'limits': {'native_jobs': 1,
                    'native_trials': 1,
                    'concurrency': 1,
                    'model_generation_calls': 0},
         'required_evidence': {'public_apt_cache': {'path': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/bookworm-public-apt-cache-r1/sealed/PUBLIC_BOOKWORM_APT_CACHE_READY_R1.json', 'sha256': '380887f06d148f9b51a5df2d7c5bd6b0805309e8460250ba772196e35517e7a0'}, 'image_ready': {'path': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/image-prewarm/fix-git/IMAGE_READY_R1.json',
                                               'sha256': '9ee167804d6c8c7ad974a6592cfdfabdee1a443e9c0f16ebd5fd4141e35791e5'},
                               'runtime_ready': {'path': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/NATIVE_RUNTIME_CPU_READY_R1.json',
                                                 'sha256': '07d34731482c4695def1e56cd1cc17fbcdc3bb65c30d3370d755dbbdaab93921'},
                               'backend_deployment': {'path': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/SSD17_BACKEND_DEPLOYMENT_R1.json',
                                                      'sha256': '2da1abefed7fd9dd7ba72c2d0e903f869736a696d276cce9ee344aa3c1340a66'},
                               'cli_wheelhouse': {'path': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/cli-wheelhouse-cp313-r2/sealed/CLI_WHEELHOUSE_READY_R2.json',
                                                  'sha256': 'c0c8d3062c2169a61f4a4003b2ab155c9d0966b4f426efe45b1084a30fab7ff0'},
                               'verifier_wheelhouse': {'path': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/fixgit-verifier-wheelhouse-local-r1/sealed/FIXGIT_VERIFIER_WHEELHOUSE_READY_R1.json',
                                                       'sha256': '398f34f4fbf2811a713a64502c4a60be48f10d52c7814a9e3bf62c49c4515d1e'},
                               'cli_transfer': {'path': '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/reliability-qwen35-reliability-20261103-r1/cli-wheelhouse-cp313-r2/SOURCE_TARGET_SHA_TRANSFER_ACCEPTANCE_R2.json',
                                                'sha256': 'ac6cd3f63dd1017af29ae60ce37b9fa44ce61ee5c9562a2373e0cef1055a8b49'}}}}

REMOTE = r'''
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
c=json.loads(sys.argv[1]);owner=json.loads(sys.argv[2]);step=sys.argv[3];phase_sha=sys.argv[4];templates=json.loads(sys.argv[5])
root=Path(c['root']);s=c['steps'][step]
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def artifact(path):
 p=Path(path)
 if not p.exists():return None
 data=p.read_bytes();return dict(path=str(p),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),value=json.loads(data))
def exclusive(path,value):
 p=Path(path)
 with p.open('x')as f:
  f.write(json.dumps(value,indent=2)+'\n');f.flush();os.fsync(f.fileno())
 fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def props():
 p=subprocess.run(['systemctl','--user','show',s['unit'],'-p','LoadState','-p','ActiveState','-p','SubState','-p','MainPID','-p','Result','-p','ExecMainStatus','-p','ExecMainStartTimestampMonotonic'],capture_output=True,text=True,timeout=4)
 rows=dict(line.split('=',1)for line in p.stdout.splitlines()if '='in line)
 if not rows or 'LoadState'not in rows:raise RuntimeError('Native unit metadata UNKNOWN:'+p.stderr[-500:])
 pid=int(rows.get('MainPID','0'));rows['actual_process']=None
 if pid:
  p=Path('/proc')/str(pid)
  try:
   argv=[v.decode()for v in p.joinpath('cmdline').read_bytes().split(b'\0')if v]
   expected=[s['python'],s['script'],'--plan',c['plan'],'--admission',s['admission']]
   cg=p.joinpath('cgroup').read_text()
   if argv!=expected or not any(line.endswith('/'+s['unit'])for line in cg.splitlines()):raise RuntimeError('Native unit process identity differs')
   rows['actual_process']=dict(pid=pid,start_ticks=p.joinpath('stat').read_text().rsplit(')',1)[1].split()[19],argv=argv,cgroup=cg)
  except FileNotFoundError:rows['process_state']='UNKNOWN_EXIT_DURING_QUERY'
 return rows
def validated_receipt(name):
 v=artifact(c['steps'][name]['receipt'])
 if v is None:return None
 body=v['value'];spec=c['steps'][name]
 if body['source_sha256']!=spec['source_sha256']or body['plan_sha256']!=spec.get('plan_sha256',c['plan_sha256'])or body['kind']!=spec['receipt_kind']:raise RuntimeError('Actual receipt source/plan/kind differs:'+name)
 if body.get('model_generation_calls')!=0:raise RuntimeError('Environment utility must not generate')
 if body.get('passed')is True:
  if name=='runtime':
   if v['sha256']!=c['runtime_receipt_sha256']:raise RuntimeError('Actual passed runtime receipt bytes changed')
   if body['new_venv']!=str(root/'native-runtime-r1')or body['actual']['passed']is not True or body['actual']['python']!=str(root/'native-runtime-r1/bin/python')or not Path(body['actual']['python']).is_file():raise RuntimeError('Actual runtime receipt is not the private17 runtime')
  else:
   row=body['row'];reward=(row['official_verifier'].get('rewards')or{}).get('reward')
   if row['status']!='PASS'or not row.get('native_trial_id')or row['actual_runtime']['engine_id']!=c['engine_id']or not row['cleanup']['complete']or row['official_verifier']['return_code']!=0 or reward not in[0,1]or body.get('eligible_for_student_model_trials')is not False:raise RuntimeError('Actual NOP acceptance is incomplete')
 return v
sources={p:sha(p)if Path(p).is_file()else None for p in[c['plan'],s['script'],c['deployment']]}
if sources[c['plan']]!=c['plan_sha256']or sources[s['script']]!=s['source_sha256']or sources[c['deployment']]!=c['deployment_sha256']:raise RuntimeError('Frozen17 source/plan/deployment not ready or changed')
p=props();admission=artifact(s['admission']);intent=artifact(s['intent']);ack=artifact(s['ack']);receipt=validated_receipt(step)
v=dict(step=step,at=time.time(),unit=p,admission=admission,intent=intent,ack=ack,receipt=receipt,source_sha256=s['source_sha256'],plan_sha256=c['plan_sha256'],model_generation_calls=0,new_dispatch=False)
if step=='nop':
 v['native_metadata']={}
 for name,path in c['nop_metadata'].items():
  try:
   item=artifact(path)
   if item and name=='raw_result':
    body=item['value'];item['value']={k:body.get(k)for k in['id','started_at','finished_at','agent_setup','agent_execution','verifier','verifier_result','exception_info','infrastructure_errors']}
   v['native_metadata'][name]=item
  except Exception as exc:v['native_metadata'][name]=dict(status='UNKNOWN',error=repr(exc),path=path)
active=p.get('ActiveState')in['active','activating','deactivating']or int(p.get('MainPID','0'))>0
if admission:
 a=admission['value'];expected=templates[step]
 if set(a)!=set(expected)or not(a['frozen']and a['admitted'])or any(a[k]!=expected[k]for k in['operation','source_sha256','plan_sha256','unique_controller_node','limits']):raise RuntimeError('Existing immutable admission identity differs')
 # Its original owner is preserved across controlled parent handoffs.
 if not isinstance(a['unique_controller_owner'],dict):raise RuntimeError('Existing admission owner missing')
 if ack and ack['value'].get('returncode')!=0:v['status']='FAILED_NATIVE_START_NO_REPLAY'
 elif active:v['status']='RUNNING_OR_NATIVE_FINALIZING'
 elif p.get('ActiveState')=='failed'or(p.get('Result')not in[None,'','success']and p.get('LoadState')!='not-found'):v['status']='FAILED_NO_REPLAY'
 elif receipt:v['status']='PASSED'if receipt['value'].get('passed')is True else'FAILED_RECEIPT_NO_REPLAY'
 else:v['status']='REGISTERED_TERMINAL_UNKNOWN_NO_REPLAY'
elif active or p.get('LoadState')!='not-found'or intent or ack or receipt or any(Path(x).exists()for x in s['started_paths']):
 v['status']='PREEXISTING_NATIVE_EVIDENCE_WITHOUT_ADMISSION_NO_REPLAY'
else:
 required={}
 if step=='nop':
  runtime=validated_receipt('runtime');image=artifact(c['image_ready'])
  v['runtime_prerequisite']=runtime;v['image_prerequisite']=image
  runtime_unit=c['steps']['runtime']['unit']
  q=subprocess.run(['systemctl','--user','show',runtime_unit,'-p','ActiveState','-p','MainPID','-p','Result'],capture_output=True,text=True,timeout=4)
  rp=dict(x.split('=',1)for x in q.stdout.splitlines()if '='in x)
  if not {'ActiveState','MainPID','Result'}<=set(rp):
   v['status']='WAIT_RUNTIME_UNIT_QUERY_UNKNOWN';print(json.dumps(v));raise SystemExit(0)
  if not runtime or runtime['value'].get('passed')is not True or rp.get('ActiveState')in['active','activating','deactivating']or int(rp.get('MainPID','0'))>0 or rp.get('ActiveState')=='failed':
   v['status']='WAIT_REAL_RUNTIME_READY_AND_CLOSED';print(json.dumps(v));raise SystemExit(0)
  if not image:
   v['status']='WAIT_REAL_FIXGIT_IMAGE_READY';print(json.dumps(v));raise SystemExit(0)
  if image['sha256']!=c['image_ready_sha256']:raise RuntimeError('Actual image-ready receipt bytes changed')
  im=image['value'];rows=im.get('rows',[])
  if im.get('passed')is not True or im.get('source_sha256')!=c['image_source_sha256']or im.get('deployment_sha256')!=c['deployment_sha256']or len(rows)!=1 or rows[0].get('task_id')!='fix-git'or rows[0].get('actual_engine_id')!=c['engine_id']or rows[0].get('image_id')!=c['image_id']or rows[0].get('official_task_image')!='alexgshaw/fix-git:20260403':raise RuntimeError('Actual image-ready identity differs')
  required=dict(image_ready={k:image[k]for k in['path','sha256']},runtime_ready={k:runtime[k]for k in['path','sha256']},backend_deployment=dict(path=c['deployment'],sha256=c['deployment_sha256']))
  apt=c['public_apt_cache'];a=artifact(apt['receipt_path']);t=artifact(apt['transfer_receipt']['path'])
  if a is None or t is None:v['status']='WAIT_REAL_PUBLIC_APT_CACHE_READY';print(json.dumps(v));raise SystemExit(0)
  if a['sha256']!=apt['expected_receipt_sha256']or t['sha256']!=apt['transfer_receipt']['sha256']or not a['value']['passed']or not t['value']['passed']or not t['value']['all_SHA_sizes_mtime_verified']or not t['value']['atomic_sealed']:raise RuntimeError('Actual17 public APT receipt/transfer identity differs')
  required['public_apt_cache']=dict(path=apt['receipt_path'],sha256=a['sha256'])
  v['public_wheelhouse_prerequisites']={}
  for role,cache in c['public_wheelhouses'].items():
   meta=artifact(cache['receipt_path']);v['public_wheelhouse_prerequisites'][role]=meta
   if not meta:
    v['status']='WAIT_REAL_PUBLIC_WHEELHOUSE_READY:'+role;print(json.dumps(v));raise SystemExit(0)
   if meta['sha256']!=cache['expected_receipt_sha256']:raise RuntimeError('Frozen actual public wheel manifest bytes differ:'+role)
   body=meta['value']
   if body.get('passed')is not True or body.get('kind')!=cache['ready_kind']or body.get('source_sha256')!=cache['preparation_source_sha256']or body.get('model_calls')!=0 or body.get('container_calls')!=0:raise RuntimeError('Public wheelhouse provenance differs:'+role)
   wheels=body['packages'];names={r['name'].lower().replace('_','-'):r['version']for r in wheels};cache_root=Path(cache['root'])
   if not cache_root.is_dir()or any(not(cache_root/r['filename']).is_file()for r in wheels):
    v['status']='WAIT_ACTUAL_PUBLIC_WHEELHOUSE_FILES:'+role;print(json.dumps(v));raise SystemExit(0)
   if any(Path(r['filename']).name!=r['filename']or(cache_root/r['filename']).is_symlink()or(cache_root/r['filename']).stat().st_size!=r['bytes']or sha(cache_root/r['filename'])!=r['sha256']for r in wheels):raise RuntimeError('Actual copied public dependency wheel SHA differs:'+role)
   if any(names.get(k)!=val for k,val in cache['required_versions'].items())or(role=='cli_wheelhouse'and names!=cache['required_versions']):raise RuntimeError('Frozen public dependency versions differ:'+role)
   required[role]={k:meta[k]for k in['path','sha256']}
  transfer=c['public_wheelhouses']['cli_wheelhouse']['transfer_receipt'];proof=artifact(transfer['path'])
  if not proof or proof['sha256']!=transfer['sha256']:raise RuntimeError('Actual17 original CLI transfer receipt differs')
  required['cli_transfer']={k:proof[k]for k in['path','sha256']}
  uv=c['public_uv_archive'];archive=Path(uv['path'])
  if not archive.is_file():
   v['status']='WAIT_REAL_UV095_RELEASE_ARCHIVE';print(json.dumps(v));raise SystemExit(0)
  if archive.is_symlink()or archive.stat().st_size!=uv['bytes']or sha(archive)!=uv['sha256']:raise RuntimeError('Original public UV0.9.5 archive SHA differs')


 for path in[root/'tmp',root/'cache',root/'cache/pip',root/'cache/uv',root/'logs']:
  path.mkdir(mode=0o700,parents=True,exist_ok=True)
  if path.resolve()!=path or path.stat().st_uid!=os.getuid():raise RuntimeError('SSD local directory ownership differs')
 a=dict(templates[step]);a.update(frozen=True,admitted=True,unique_controller_owner=owner,required_evidence=required)
 exclusive(s['admission'],a)
 exclusive(s['intent'],dict(at=time.time(),unit=s['unit'],source_sha256=s['source_sha256'],plan_sha256=c['plan_sha256'],unique_controller_owner=owner,phase_sha256=phase_sha,registered_once_before_native_start=True,admission_sha256=sha(s['admission'])))
 command=['systemd-run','--user','--unit='+s['unit'],'--collect','--no-block','--property=MemoryMax=16G','--property=StandardOutput=append:'+s['log'],'--property=StandardError=append:'+s['log']]
 for key,path in dict(TMPDIR=root/'tmp',XDG_CACHE_HOME=root/'cache',PIP_CACHE_DIR=root/'cache/pip',UV_CACHE_DIR=root/'cache/uv',PIP_DISABLE_PIP_VERSION_CHECK='1').items():command+=['--setenv='+key+'='+str(path)]
 command+=[s['python'],s['script'],'--plan',c['plan'],'--admission',s['admission']]
 result=subprocess.run(command,capture_output=True,text=True,timeout=6)
 exclusive(s['ack'],dict(at=time.time(),returncode=result.returncode,stdout=result.stdout[-1500:],stderr=result.stderr[-1500:],command=command,admission_sha256=sha(s['admission']),phase_sha256=phase_sha))
 v.update(status='NATIVE_START_REQUESTED'if result.returncode==0 else'NATIVE_START_FAILED_NO_REPLAY',new_dispatch=True,command=command,returncode=result.returncode,unit=props(),admission=artifact(s['admission']),intent=artifact(s['intent']),ack=artifact(s['ack']))
print(json.dumps(v))
'''

def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def guard(owner):
    if read(C/'NATIVE_ADVANCE_OWNER.json')!=owner:raise RuntimeError('Unique controller owner changed')
    if(Path('/proc')/str(owner['pid'])/'stat').read_text().rsplit(')',1)[1].split()[19]!=str(owner['start_ticks']):raise RuntimeError('Unique controller process identity changed')
    path=Path(CONFIG['ssh_config'])
    if sha(path)!=CONFIG['ssh_config_sha256']:raise RuntimeError('Registered17 exec SSH configuration differs')
    hosts=[shlex.split(line,comments=True)[1]for line in path.read_text().splitlines()if shlex.split(line,comments=True)and shlex.split(line,comments=True)[0].lower()=='userknownhostsfile']
    if len(hosts)!=1 or sha(hosts[0])!=CONFIG['known_hosts_sha256']:raise RuntimeError('Registered17 private known_hosts differs')

def remote(step,owner):
    if step!='nop':raise RuntimeError('R4 only dispatches the independent NOP; never reprepare the passed runtime')
    guard(owner)
    payload=['/usr/bin/python3','-c',REMOTE,json.dumps(CONFIG),json.dumps(owner),step,sha(__file__),json.dumps(TEMPLATES)]
    argv=['/usr/bin/ssh','-F',CONFIG['ssh_config'],'-T','-o','BatchMode=yes','-o','ConnectTimeout=5',CONFIG['ssh_alias'],shlex.join(payload)]
    start=time.monotonic();p=subprocess.run(argv,capture_output=True,text=True,timeout=18)
    if p.returncode:raise RuntimeError('SSD17 finite control RPC failed:'+p.stderr[-1500:])
    value=json.loads(p.stdout);value['controller_rpc_seconds']=time.monotonic()-start;return value

def advance(owner,state,launch):
    """Only R4 NOP; reuse actual R1 runtime/image; local launch is unused."""
    guard(owner)
    status=dict(at=time.time(),status='SSD17_NATIVE_INDEPENDENT_NOP_R5',model_generation_calls=0,unique_controller_owner=owner,phase_sha256=sha(__file__))
    state['ssd17_native_nop_r5']=status
    try:
        nop=remote('nop',owner);status['nop']=nop;status['status']='SSD17_NOP_'+nop['status']
        if nop.get('receipt'):
            body=nop['receipt']['value'];status['nop_environment_passed']=body.get('passed')
            status['backend_task_network_and_model_metadata_ready']=body.get('backend_task_network_and_model_metadata_ready',False)
            status['model_service_connectivity_status']=body.get('model_service_connectivity_status')
            status['end_to_end_student_ready']=False;status['eligible_for_student_model_trials']=False
    except Exception as error:
        status.update(status='SSD17_NATIVE_CONTROL_REQUIRES_INSPECTION_NO_REPLAY',error=repr(error))

if __name__=='__main__':raise SystemExit('Only the existing unique advance may call this leaf')
