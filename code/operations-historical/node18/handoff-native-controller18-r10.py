import hashlib,json,py_compile,subprocess,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
EXPECTED={'gpu5_readiness18_r1.py': 'fe6e4e451922155b6ecf6cacdb55deee362b339bbbb16cc00868581d7b800668', 'new-validation-readouts18-r2.py': 'acacdd2a7cb61c608ce60a7ce165d8cec87f34c81a2e46a1dbd1b9781c3019c1', 'score-frozen-validation18-r3.py': 'b72cf6ee7501239c7199af9b1bf21442ee99b602e1d4410bce50a2ab6d0622a1', 'audit-native-cli-prefix-r2.py': '007f4c322994853712169d3d2e8b20c5d8a7aa08fc348a9570509b4902f310d1', 'audit-native-cli-smoke-r3.py': 'c6a1fc68128b16e424d7d1fcc7efcc9dd2341f94c1085f16a41b11464b9137cc', 'admit-formal-native-cli18-r1.py': '5f59e4baa5b5aa6cbc875fece143512febc2f7beb3b0ed1127c61a538eb29cf0', 'phase_progression18_r7.py': 'b01170c81f9e55a46b4d363d7367d3cf8faca85ada9e26f4d21fe7aa763c2332', 'run-native772-advance-r10.py': 'aae3a5e1f2ae6394dda13de9241636956ccb43f823386a88f9252a8bb6db7ffd', 'read-only-monitor18-r16.py': '842a6b0c15845cc221b3beae4d9e09ffe090a565e2aa114040a898f17fabbc2e', 'final-hf-admission18-r4.py': '98ae4778f2089e3409281d3282d4b10cc625548f60717aa6bffd862c5963e99b', 'cold-hf-native-cli-smoke-r5.py': 'e54574565ce6175f93125301f65677913e53f4a82edd34e9a7fe14b0ffe22843', 'cold-native-serving18-r2.py': '4cf4df49e6fba6278bef2a99341d544e7c76cc4a94f50008a274ef28c878064d'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def props(unit):
 return dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','-p','ActiveState','-p','LoadState'],text=True).splitlines())
def identity(pid):
 return dict(pid=pid,start_ticks=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19],cmdline=Path('/proc/'+str(pid)+'/cmdline').read_bytes().replace(b'\0',b' ').decode())
for name,expected in EXPECTED.items():
 assert sha(R/name)==expected,name
 py_compile.compile(str(R/name),doraise=True)
release=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R7.json';assert release.exists()
assert json.loads((R/'checks/CONTEXT_RECOVERY_INSTALLED_WHEEL_ACCEPTANCE_R1.json').read_text())['passed']
assert json.loads((R/'checks/CONTROL_R10_CPU_SOURCE_ACCEPTANCE_R1.json').read_text())['passed']
assert json.loads((R/'checks/FORMAL_EXTENDED_PROTOCOL_CPU_ACCEPTANCE_R1.json').read_text())['passed']
cpu=json.loads((R/'checks/CONTROL_R10_CPU_SOURCE_ACCEPTANCE_R1.json').read_text())
assert all(EXPECTED[name]==digest for name,digest in cpu['new_sources_sha256'].items())
assert not(C/'native-phase-requests/formal-n3.json').exists(),'A formal dispatch already exists; do not change it'
old='qwen35-772-native-advance-node18-20261101-r9.service'
new='qwen35-772-native-advance-node18-20261101-r10.service'
units=['qwen35-772-new-sft-new772-new-cf416-tmax356-m2.service','qwen35-new772-cold-new-m1-epoch3-fixed-20261101.service']
before={unit:identity(int(props(unit)['MainPID']))for unit in units}
assert before[units[0]]['pid']==1194582 and before[units[0]]['start_ticks']=='91798358'
assert before[units[1]]['pid']==1890941
previous=props(old);pid=int(previous['MainPID']);owner=json.loads((C/'NATIVE_ADVANCE_OWNER.json').read_text())
assert pid==1244593 and owner['pid']==pid and owner['start_ticks']==identity(pid)['start_ticks']
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='5ed5b9fc-6915-46c8-b9ad-04e790f6b65b'
assert not Path('/proc/'+str(pid)+'/task/'+str(pid)+'/children').read_text().strip(),'Controller inside native operation; retry only at idle boundary'
assert Path('/proc/'+str(pid)+'/wchan').read_text().strip()=='hrtimer_nanosleep','Controller not at sleep boundary'
assert props(new)['LoadState']=='not-found','New unit already exists; inspect before dispatch'
subprocess.run(['systemctl','--user','stop',old],check=True,timeout=20)
assert props(old)['ActiveState']=='inactive'
for unit,item in before.items():assert identity(item['pid'])==item
args=['systemd-run','--user','--unit='+new,'--property=MemoryMax=192G',
 '--property=StandardOutput=append:'+str(R/'logs/native-advance-r10.log'),
 '--property=StandardError=append:'+str(R/'logs/native-advance-r10.log'),
 '--setenv=OMP_NUM_THREADS=2','--setenv=HF_HUB_OFFLINE=1','--setenv=TMPDIR='+str(R/'tmp'),
 '--setenv=TRITON_CACHE_DIR='+str(R/'cache/triton'),'--setenv=TORCH_EXTENSIONS_DIR='+str(R/'cache/torch-extensions'),
 str(R/'env/train-r1/bin/python'),str(R/'run-native772-advance-r10.py')]
subprocess.run(args,check=True,capture_output=True,text=True)
for _ in range(30):
 current=props(new);newpid=int(current['MainPID']);live=json.loads((C/'NATIVE_ADVANCE_OWNER.json').read_text())
 if newpid and live['pid']==newpid:break
 time.sleep(1)
else:raise ValueError('New controller did not acquire existing cross-node Ceph lock')
for unit,item in before.items():assert identity(item['pid'])==item
proof=dict(passed=True,at=time.time(),old_controller=previous,new_controller=current,
 preserved_native_processes=before,all_native_process_identities_unchanged=True,source_hashes=EXPECTED,
 native_deployment_release_sha256=sha(release),student_wheel_release_sha256=sha(R/'checks/NEW11_STUDENT_HARNESS_RELEASE_R5.json'),
 original_cross_node_lock=str(C/'unique-native-advance.lock'),
 training_source_sha256='293ba2a7dca8569bb39e11bc0137a0e1180a0391402f10d49ff5b4ad00ce6c93',
 resource_gate_cpu_acceptance_sha256=sha(R/'checks/CONTROL_R10_CPU_SOURCE_ACCEPTANCE_R1.json'),
 formal_extended_cpu_acceptance_sha256=sha(R/'checks/FORMAL_EXTENDED_PROTOCOL_CPU_ACCEPTANCE_R1.json'),
 formal_three_models_require_actual_extended_cli_before801=True,
 original_model_recipe_data_sampling_budgets_and_wheel_unchanged=True,
 handoff_source_sha256=sha(Path(__file__)))
p=C/'NATIVE_ADVANCE_R10_CONTROLLED_HANDOFF.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+'\n')
a=Path.home()/'.ssh/authorized_keys';raw=a.read_text();lines=raw.splitlines(keepends=True)
indices=[i for i,x in enumerate(lines)if 'read-only-monitor18-r15.py'in x];assert len(indices)==1
backup=a.with_name('authorized_keys.before-monitor-r16-'+str(int(time.time())));backup.write_text(raw);backup.chmod(0o600)
lines[indices[0]]=lines[indices[0]].replace('read-only-monitor18-r15.py','read-only-monitor18-r16.py')
temp=a.with_name('authorized_keys.monitor-r16.tmp');temp.write_text(''.join(lines));temp.chmod(0o600);temp.replace(a)
print(json.dumps(proof))
