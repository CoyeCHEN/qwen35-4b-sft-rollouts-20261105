import hashlib,json,py_compile,subprocess,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
EXPECTED={'run-native772-advance-r8.py': 'e048c1d26f6fc55d2a34224bc1f9d366bf369f784a80364cd95613f453c4cc2c', 'phase_progression18_r5.py': 'c5d4d53d67dd5b213211d4b27baef6a3752ddbed7fd7e04379c0d02f27e9be68', 'read-only-monitor18-r14.py': '57956b1e4251713b560c4a880d88c47a0b6d60f047f24945a00b446a37056d3e', 'final-hf-admission18-r3.py': 'f42e3c52bc66c67eba58e37afc3eec2f4ed79f2599d9adad5f45301405bc67c1', 'cold-hf-native-cli-smoke-r4.py': '780098b1a1ac8ffd09791151eda6d0392733b6ac4a9da7a544f3097213e9b70a'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def props(unit):
 return dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','-p','ActiveState','-p','LoadState'],text=True).splitlines())
def identity(pid):
 return dict(pid=pid,start_ticks=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19],cmdline=Path('/proc/'+str(pid)+'/cmdline').read_bytes().replace(b'\0',b' ').decode())
for name,expected in EXPECTED.items():
 assert sha(R/name)==expected,name
 py_compile.compile(str(R/name),doraise=True)
release=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R6.json';assert release.exists()
assert json.loads((R/'checks/CONTEXT_RECOVERY_INSTALLED_WHEEL_ACCEPTANCE_R1.json').read_text())['passed']
old='qwen35-772-native-advance-node18-20261101-r7.service'
new='qwen35-772-native-advance-node18-20261101-r8.service'
units=['qwen35-772-new-sft-new772-new-cf416-m1.service','qwen35-new772-cold-new-m1-epoch3-20261101.service']
before={unit:identity(int(props(unit)['MainPID']))for unit in units}
assert before[units[0]]['pid']==3179152 and before[units[0]]['start_ticks']=='86376371'
previous=props(old);pid=int(previous['MainPID']);owner=json.loads((C/'NATIVE_ADVANCE_OWNER.json').read_text())
assert pid==2260573 and owner['pid']==pid and owner['start_ticks']==identity(pid)['start_ticks']
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='5ed5b9fc-6915-46c8-b9ad-04e790f6b65b'
assert not Path('/proc/'+str(pid)+'/task/'+str(pid)+'/children').read_text().strip(),'Controller inside native operation; retry only at idle boundary'
assert Path('/proc/'+str(pid)+'/wchan').read_text().strip()=='hrtimer_nanosleep','Controller not at sleep boundary'
assert props(new)['LoadState']=='not-found','New unit already exists; inspect before dispatch'
subprocess.run(['systemctl','--user','stop',old],check=True,timeout=20)
assert props(old)['ActiveState']=='inactive'
for unit,item in before.items():assert identity(item['pid'])==item
args=['systemd-run','--user','--unit='+new,'--property=MemoryMax=192G',
 '--property=StandardOutput=append:'+str(R/'logs/native-advance-r8.log'),
 '--property=StandardError=append:'+str(R/'logs/native-advance-r8.log'),
 '--setenv=OMP_NUM_THREADS=2','--setenv=HF_HUB_OFFLINE=1','--setenv=TMPDIR='+str(R/'tmp'),
 '--setenv=TRITON_CACHE_DIR='+str(R/'cache/triton'),'--setenv=TORCH_EXTENSIONS_DIR='+str(R/'cache/torch-extensions'),
 str(R/'env/train-r1/bin/python'),str(R/'run-native772-advance-r8.py')]
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
p=C/'NATIVE_ADVANCE_R8_CONTROLLED_HANDOFF.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+'\n')
a=Path.home()/'.ssh/authorized_keys';raw=a.read_text();lines=raw.splitlines(keepends=True)
indices=[i for i,x in enumerate(lines)if 'read-only-monitor18-r13.py'in x];assert len(indices)==1
backup=a.with_name('authorized_keys.before-monitor-r14-'+str(int(time.time())));backup.write_text(raw);backup.chmod(0o600)
lines[indices[0]]=lines[indices[0]].replace('read-only-monitor18-r13.py','read-only-monitor18-r14.py')
temp=a.with_name('authorized_keys.monitor-r14.tmp');temp.write_text(''.join(lines));temp.chmod(0o600);temp.replace(a)
print(json.dumps(proof))
