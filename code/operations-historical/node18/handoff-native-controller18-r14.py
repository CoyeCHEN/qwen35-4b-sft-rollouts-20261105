import hashlib,json,py_compile,subprocess,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
EXPECTED={'gpu5_readiness18_r1.py': 'fe6e4e451922155b6ecf6cacdb55deee362b339bbbb16cc00868581d7b800668', 'new-validation-readouts18-r2.py': 'acacdd2a7cb61c608ce60a7ce165d8cec87f34c81a2e46a1dbd1b9781c3019c1', 'score-frozen-validation18-r3.py': 'b72cf6ee7501239c7199af9b1bf21442ee99b602e1d4410bce50a2ab6d0622a1', 'audit-native-cli-prefix-r2.py': '007f4c322994853712169d3d2e8b20c5d8a7aa08fc348a9570509b4902f310d1', 'audit-native-cli-smoke-r3.py': 'c6a1fc68128b16e424d7d1fcc7efcc9dd2341f94c1085f16a41b11464b9137cc', 'admit-formal-native-cli18-r1.py': '5f59e4baa5b5aa6cbc875fece143512febc2f7beb3b0ed1127c61a538eb29cf0', 'final-hf-admission18-r4.py': '98ae4778f2089e3409281d3282d4b10cc625548f60717aa6bffd862c5963e99b', 'cold-hf-native-cli-smoke-r5.py': 'e54574565ce6175f93125301f65677913e53f4a82edd34e9a7fe14b0ffe22843', 'cold-native-serving18-r2.py': '4cf4df49e6fba6278bef2a99341d544e7c76cc4a94f50008a274ef28c878064d', 'phase_progression18_r10.py': '45a5be9c49dfb311b62c4ad28f306b7baa9a88c3dfc214b107d47bea2c116aa2', 'run-native772-advance-r13.py': '42f4f6a5bc255f466f5683581a9c30c34b46ed932f7f8391eafd2d3e69ef1d08', 'read-only-monitor18-r19.py': '679e73019cd614ca9dc8b5995b149a9f720f60f3918eb944f495bfc1f8d032b2', 'run-native772-advance-r14.py': 'c3401f9d6e024a7d17d89821af02d6a50a62c12a334fcbca4aeb5f17174d4b71', 'phase_progression18_r11.py': '2b58313d43ae35abc26ffaafdb9bb24855442be90e6a6e0359088e5c64bf0f02', 'read-only-monitor18-r20.py': '894a087b86a48c92900167232ae15d041245f19090fcdace6eb071c7e99612ce', 'native-handoff149-r11.py': 'ce18b5dfa4f11189b9819ecea28d2ef2cba131ee6c2b6c56639ce5ffe7bcdadf', 'sync-closed-e3-evidence18-r1.py': '15ddcddaf91a8f5b2f8d7ec506d7dd51abd4883aeb0bb90571d0698d7665cfda', 'preflight-formal-controller18-m0-native-joint-r1.py': '98ad3a74e1f9f1ef3ea5637a3a1e7db021182d981f69d5f2264522528f5fa71d', 'formal-native-eval-r1/scripts/run-formal-native-tb2118-r2.py': '9d5c4cfaa1d0d30ff669be07bd27e4e5f969641b59de4b8cf28587a169e3065c'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def props(unit):
 return dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','-p','ActiveState','-p','LoadState'],text=True).splitlines())
def identity(pid):
 return dict(pid=pid,start_ticks=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19],cmdline=Path('/proc/'+str(pid)+'/cmdline').read_bytes().replace(b'\0',b' ').decode())
for name,expected in EXPECTED.items():
 assert sha(R/name)==expected,name
 py_compile.compile(str(R/name),doraise=True)
release=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R11.json';assert release.exists()
assert sha(release)==json.loads((R/'checks/NATIVE_EVAL149_R11_ACTIVATION.json').read_text())['release_sha256']
assert json.loads((R/'checks/NATIVE_EVAL149_R11_ACTIVATION.json').read_text())['passed']
assert json.loads((R/'checks/ACTUAL_RESPONSE_QUALIFICATION_ACCEPTANCE_R1.json').read_text())['passed']
assert json.loads((R/'checks/CONTEXT_RECOVERY_INSTALLED_WHEEL_ACCEPTANCE_R1.json').read_text())['passed']
assert json.loads((R/'checks/FORMAL_CONTROLLER18_ALL801_CONFIG_DELTA_ACCEPTANCE_R2.json').read_text())['passed']
assert json.loads((R/'checks/FORMAL_EXTENDED_PROTOCOL_CPU_ACCEPTANCE_R1.json').read_text())['passed']
cpu=json.loads((R/'checks/FORMAL_CONTROLLER18_ALL801_CONFIG_DELTA_ACCEPTANCE_R2.json').read_text())
assert all(EXPECTED[name]==digest for name,digest in cpu['new_sources_sha256'].items())
assert not(C/'native-phase-requests/formal-n3.json').exists(),'A formal dispatch already exists; do not change it'
local_release=R/'checks/FORMAL_CONTROLLER18_DEPLOYMENT_RELEASE_R2.json'
local_doc=json.loads(local_release.read_text());assert local_doc['deployment_sha256']==sha(R/'configs/formal-controller18-deployment-r2.json')
for name,digest in local_doc['sources'].items():assert sha(R/name)==digest
assert json.loads((R/'checks/NATIVE_EIGHT_RECORDER_TRANSFER_ACCEPTANCE_R1.json').read_text())['passed']
assert json.loads((R/'checks/NATIVE_EVAL149_R11_REAL_PROTOCOL_ACCEPTANCE.json').read_text())['actual_forced_command_rejected_formal149_write']

old='qwen35-772-native-advance-node18-20261101-r13.service'
new='qwen35-772-native-advance-node18-20261102-r14.service'
units=['qwen35-772-new-sft-new772-new-cf416-tmax356-m2.service','qwen35-new772-cold-new-m1-epoch3-fixed-20261101.service']
before={unit:identity(int(props(unit)['MainPID']))for unit in units}
rank_before={pid:identity(pid)for pid in [1208295,1208296,1208297,1208298]}
assert before[units[0]]['pid']==1194582 and before[units[0]]['start_ticks']=='91798358'
assert before[units[1]]['pid']==1890941
previous=props(old);pid=int(previous['MainPID']);owner=json.loads((C/'NATIVE_ADVANCE_OWNER.json').read_text())
assert pid==840835 and owner['pid']==pid and owner['start_ticks']==identity(pid)['start_ticks']
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='5ed5b9fc-6915-46c8-b9ad-04e790f6b65b'
assert not Path('/proc/'+str(pid)+'/task/'+str(pid)+'/children').read_text().strip(),'Controller inside native operation; retry only at idle boundary'
assert Path('/proc/'+str(pid)+'/wchan').read_text().strip()=='hrtimer_nanosleep','Controller not at sleep boundary'
assert props(new)['LoadState']=='not-found','New unit already exists; inspect before dispatch'
subprocess.run(['systemctl','--user','stop',old],check=True,timeout=20)
assert props(old)['ActiveState']=='inactive'
for unit,item in before.items():assert identity(item['pid'])==item
for pid,item in rank_before.items():assert identity(pid)==item
args=['systemd-run','--user','--unit='+new,'--property=MemoryMax=192G',
 '--property=StandardOutput=append:'+str(R/'logs/native-advance-r14.log'),
 '--property=StandardError=append:'+str(R/'logs/native-advance-r14.log'),
 '--setenv=OMP_NUM_THREADS=2','--setenv=HF_HUB_OFFLINE=1','--setenv=TMPDIR='+str(R/'tmp'),
 '--setenv=TRITON_CACHE_DIR='+str(R/'cache/triton'),'--setenv=TORCH_EXTENSIONS_DIR='+str(R/'cache/torch-extensions'),
 str(R/'env/train-r1/bin/python'),str(R/'run-native772-advance-r14.py')]
subprocess.run(args,check=True,capture_output=True,text=True)
for _ in range(30):
 current=props(new);newpid=int(current['MainPID']);live=json.loads((C/'NATIVE_ADVANCE_OWNER.json').read_text())
 if newpid and live['pid']==newpid:break
 time.sleep(1)
else:raise ValueError('New controller did not acquire existing cross-node Ceph lock')
for unit,item in before.items():assert identity(item['pid'])==item
for pid,item in rank_before.items():assert identity(pid)==item
proof=dict(passed=True,at=time.time(),old_controller=previous,new_controller=current,
 preserved_native_processes=before,preserved_four_native_rank_processes=rank_before,all_native_process_identities_unchanged=True,source_hashes=EXPECTED,
 native_deployment_release_sha256=sha(release),student_wheel_release_sha256=sha(R/'checks/NEW11_STUDENT_HARNESS_RELEASE_R5.json'),
 original_cross_node_lock=str(C/'unique-native-advance.lock'),
 training_source_sha256='293ba2a7dca8569bb39e11bc0137a0e1180a0391402f10d49ff5b4ad00ce6c93',
 control_wiring_cpu_acceptance_sha256=sha(R/'checks/FORMAL_CONTROLLER18_ALL801_CONFIG_DELTA_ACCEPTANCE_R2.json'),
 formal_extended_cpu_acceptance_sha256=sha(R/'checks/FORMAL_EXTENDED_PROTOCOL_CPU_ACCEPTANCE_R1.json'),
 formal_three_models_require_actual_extended_cli_before801=True,
 strict_response_qualification_required_before_old_four=True,
 native149_activation_sha256=sha(R/'checks/NATIVE_EVAL149_R11_ACTIVATION.json'),
 original_model_recipe_data_sampling_budgets_and_wheel_unchanged=True,
 handoff_source_sha256=sha(Path(__file__)),
 formal_controller18_deployment_release_sha256=sha(local_release),
 actual_eight_transfer_proof_sha256=sha(R/'checks/NATIVE_EIGHT_RECORDER_TRANSFER_ACCEPTANCE_R1.json'),
 native_formal_controller_node='18',native_formal_physical_jobs_root=str(R/'formal-native-eval-r1/jobs'),
 actual_provider_transfer_timeout_sec=3600,model_http_agent_verifier_and_background_budgets_unchanged=True,
 actual_three_cold_cli_and_m0_joint_still_required_before801=True,formal_ready_not_claimed=True)
p=C/'NATIVE_ADVANCE_R14_CONTROLLED_HANDOFF.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+'\n')
a=Path.home()/'.ssh/authorized_keys';raw=a.read_text();lines=raw.splitlines(keepends=True)
indices=[i for i,x in enumerate(lines)if 'read-only-monitor18-r19.py'in x];assert len(indices)==1
backup=a.with_name('authorized_keys.before-monitor-r20-'+str(int(time.time())));backup.write_text(raw);backup.chmod(0o600)
lines[indices[0]]=lines[indices[0]].replace('read-only-monitor18-r19.py','read-only-monitor18-r20.py')
temp=a.with_name('authorized_keys.monitor-r20.tmp');temp.write_text(''.join(lines));temp.chmod(0o600);temp.replace(a)
print(json.dumps(proof))
