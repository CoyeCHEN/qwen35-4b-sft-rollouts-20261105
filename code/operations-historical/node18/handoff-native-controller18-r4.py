import hashlib,json,os,py_compile,subprocess,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
EXPECTED={'run-native772-advance-r4.py': 'ebde537c2b0541e897d9adc9194c41294ee049f7c9a5d8c7d640b8f7c4245299', 'phase_progression18_r2.py': '8a7fa4637511bb96bbfac7ce6068627def686b5296bf63ef3b1f6108c8cf3880', 'read-only-monitor18-r9.py': 'ccde7e723592bb65c874f1e16f823072502e4d9b6f6f43e3ac6db75a33240c78', 'resume-old-four-native18-r2.py': 'a4273fe28527ee83477154a851004588e919c5fb917dfd8bb193dccfc5e8d912'}
def props(unit):
 return dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','-p','ActiveState','-p','LoadState'],text=True).splitlines())
def identity(pid):
 return dict(pid=pid,start_ticks=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19],cmdline=Path('/proc/'+str(pid)+'/cmdline').read_bytes().replace(b'\0',b' ').decode())
for name,value in EXPECTED.items():
 if hashlib.sha256((R/name).read_bytes()).hexdigest()!=value:raise ValueError('Source mismatch: '+name)
 py_compile.compile(str(R/name),doraise=True)
release=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R2.json'
if not release.exists():raise ValueError('Release R2 copy is incomplete')
old='qwen35-772-native-advance-node18-20261101-r3.service'
new='qwen35-772-native-advance-node18-20261101-r4.service'
training='qwen35-772-new-sft-new772-new-cf416-m1.service'
before=identity(int(props(training)['MainPID']))
previous=props(old);pid=int(previous['MainPID']);owner=json.loads((C/'NATIVE_ADVANCE_OWNER.json').read_text())
if pid!=3259699 or owner['pid']!=pid or owner['start_ticks']!=identity(pid)['start_ticks']:raise ValueError('Previous CPU controller identity changed')
if Path('/proc/'+str(pid)+'/task/'+str(pid)+'/children').read_text().strip():raise ValueError('Controller is inside a native lifecycle operation; retry at idle boundary')
if Path('/proc/'+str(pid)+'/wchan').read_text().strip()!='hrtimer_nanosleep':raise ValueError('Controller is not at its observation sleep boundary')
if props(new)['LoadState']!='not-found':raise ValueError('New CPU controller unit already exists; inspect rather than duplicate')
subprocess.run(['systemctl','--user','stop',old],check=True,timeout=20)
if props(old)['ActiveState']!='inactive':raise ValueError('Previous CPU controller did not stop')
if identity(before['pid'])!=before:raise ValueError('Healthy native GPU identity changed')
args=['systemd-run','--user','--unit='+new,'--property=MemoryMax=192G',
 '--property=StandardOutput=append:'+str(R/'logs/native-advance-r4.log'),
 '--property=StandardError=append:'+str(R/'logs/native-advance-r4.log'),
 '--setenv=OMP_NUM_THREADS=2','--setenv=HF_HUB_OFFLINE=1','--setenv=TMPDIR='+str(R/'tmp'),
 '--setenv=TRITON_CACHE_DIR='+str(R/'cache/triton'),
 '--setenv=TORCH_EXTENSIONS_DIR='+str(R/'cache/torch-extensions'),
 str(R/'env/train-r1/bin/python'),str(R/'run-native772-advance-r4.py')]
subprocess.run(args,check=True,capture_output=True,text=True)
for n in range(30):
 current=props(new);newpid=int(current['MainPID']);live=json.loads((C/'NATIVE_ADVANCE_OWNER.json').read_text())
 if newpid and live['pid']==newpid:break
 time.sleep(1)
else:raise ValueError('New controller has not acquired the original Ceph ownership lock')
if identity(before['pid'])!=before:raise ValueError('GPU training identity changed after handoff')
proof=dict(passed=True,at=time.time(),old_controller=previous,new_controller=current,
 before_training_identity=before,after_training_identity=identity(before['pid']),
 native_training_untouched=True,source_hashes=EXPECTED,
 native_deployment_release_sha256=hashlib.sha256(release.read_bytes()).hexdigest(),
 original_cross_node_lock=str(C/'unique-native-advance.lock'),
 training_source_sha256='293ba2a7dca8569bb39e11bc0137a0e1180a0391402f10d49ff5b4ad00ce6c93')
(C/'NATIVE_ADVANCE_R4_CONTROLLED_HANDOFF.json').write_text(json.dumps(proof,indent=2)+'\n')
a=Path.home()/'.ssh/authorized_keys';raw=a.read_text();lines=raw.splitlines(keepends=True)
indices=[i for i,v in enumerate(lines)if 'read-only-monitor18-r8.py'in v]
if len(indices)!=1:raise ValueError('Expected exactly one own monitor forced-command entry')
a.with_name('authorized_keys.before-monitor-r9-'+str(int(time.time()))).write_text(raw)
lines[indices[0]]=lines[indices[0]].replace('read-only-monitor18-r8.py','read-only-monitor18-r9.py')
temp=a.with_name('authorized_keys.monitor-r9.tmp');temp.write_text(''.join(lines));temp.chmod(0o600);temp.replace(a)
print(json.dumps(proof))
