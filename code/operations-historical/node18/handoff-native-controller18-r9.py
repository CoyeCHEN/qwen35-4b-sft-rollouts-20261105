import hashlib,json,py_compile,subprocess,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
EXPECTED={'run-native772-advance-r9.py': '69815b299bf160ad01453725c73f06cc64cdc83c55983c724316104295390953', 'phase_progression18_r6.py': 'f2be8ba1b3ae844e04be6fe377987943c95d1ca36ae0f2954e6376c8fb9f3093', 'read-only-monitor18-r15.py': 'cf70b0a8a0405994407284b328f1ae11605337f54516706edf234f7675bfaf96', 'final-hf-admission18-r4.py': '98ae4778f2089e3409281d3282d4b10cc625548f60717aa6bffd862c5963e99b', 'cold-hf-native-cli-smoke-r5.py': 'e54574565ce6175f93125301f65677913e53f4a82edd34e9a7fe14b0ffe22843', 'cold-native-serving18-r2.py': '4cf4df49e6fba6278bef2a99341d544e7c76cc4a94f50008a274ef28c878064d'}
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
old='qwen35-772-native-advance-node18-20261101-r8.service'
new='qwen35-772-native-advance-node18-20261101-r9.service'
units=['qwen35-772-new-sft-new772-new-cf416-m1.service']
before={unit:identity(int(props(unit)['MainPID']))for unit in units}
assert before[units[0]]['pid']==3179152 and before[units[0]]['start_ticks']=='86376371'
previous=props(old);pid=int(previous['MainPID']);owner=json.loads((C/'NATIVE_ADVANCE_OWNER.json').read_text())
assert pid==900777 and owner['pid']==pid and owner['start_ticks']==identity(pid)['start_ticks']
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='5ed5b9fc-6915-46c8-b9ad-04e790f6b65b'
assert not Path('/proc/'+str(pid)+'/task/'+str(pid)+'/children').read_text().strip(),'Controller inside native operation; retry only at idle boundary'
assert Path('/proc/'+str(pid)+'/wchan').read_text().strip()=='hrtimer_nanosleep','Controller not at sleep boundary'
assert props(new)['LoadState']=='not-found','New unit already exists; inspect before dispatch'
subprocess.run(['systemctl','--user','stop',old],check=True,timeout=20)
assert props(old)['ActiveState']=='inactive'
for unit,item in before.items():assert identity(item['pid'])==item
args=['systemd-run','--user','--unit='+new,'--property=MemoryMax=192G',
 '--property=StandardOutput=append:'+str(R/'logs/native-advance-r9.log'),
 '--property=StandardError=append:'+str(R/'logs/native-advance-r9.log'),
 '--setenv=OMP_NUM_THREADS=2','--setenv=HF_HUB_OFFLINE=1','--setenv=TMPDIR='+str(R/'tmp'),
 '--setenv=TRITON_CACHE_DIR='+str(R/'cache/triton'),'--setenv=TORCH_EXTENSIONS_DIR='+str(R/'cache/torch-extensions'),
 str(R/'env/train-r1/bin/python'),str(R/'run-native772-advance-r9.py')]
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
 training_source_sha256='293ba2a7dca8569bb39e11bc0137a0e1180a0391402f10d49ff5b4ad00ce6c93')
p=C/'NATIVE_ADVANCE_R9_CONTROLLED_HANDOFF.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+'\n')
a=Path.home()/'.ssh/authorized_keys';raw=a.read_text();lines=raw.splitlines(keepends=True)
indices=[i for i,x in enumerate(lines)if 'read-only-monitor18-r14.py'in x];assert len(indices)==1
backup=a.with_name('authorized_keys.before-monitor-r15-'+str(int(time.time())));backup.write_text(raw);backup.chmod(0o600)
lines[indices[0]]=lines[indices[0]].replace('read-only-monitor18-r14.py','read-only-monitor18-r15.py')
temp=a.with_name('authorized_keys.monitor-r15.tmp');temp.write_text(''.join(lines));temp.chmod(0o600);temp.replace(a)
print(json.dumps(proof))
