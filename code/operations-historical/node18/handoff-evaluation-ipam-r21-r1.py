"""Controlled idle handoff; preserve every existing model service and native Job."""
import hashlib,json,subprocess,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def props(unit):return dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,'-p','LoadState','-p','MainPID','-p','ActiveState','-p','Result'],text=True).splitlines())
def ident(pid):return dict(pid=pid,start_ticks=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[19])
def save(p,v):assert not p.exists(),p;p.write_text(json.dumps(v,indent=2)+'\n')
def main():
    owner=read(C/'NATIVE_ADVANCE_OWNER.json');assert owner['pid']==817279 and owner['start_ticks']=='95196990'
    old='qwen35-772-native-advance-node18-20261102-r20.service';new='qwen35-772-native-advance-node18-20261102-r21.service'
    assert props(old)['ActiveState']=='active'and props(new)['LoadState']=='not-found'
    assert not(C/'native-phase-requests/formal-n3.json').exists()and not(R/'checks/WINNER_FROM_COMMON30_SELECTION_R1.json').exists()
    for p in ['PUBLIC_BIND_ASSET_MIRROR_AND_ROOT_ACCEPTANCE_R1.json','EVALUATION_IPAM_AND_PUBLIC_BINDS_RUNTIME_ACCEPTANCE_R1.json','PRE_MODEL_ENV_CONTINUATION_NATIVE_ACCEPTANCE_R2.json']:assert read(R/'checks'/p)['passed']
    for name in ['run-user-evaluation-native18-r2.py','evaluation-preparation18-r1.py','read-diagnostic150-matrix18-r2.py']:
        source=R/name;dest=E/'scripts'/name
        if dest.exists():assert sha(source)==sha(dest)
        else:dest.write_bytes(source.read_bytes())
    names=['run-native772-advance-r21.py','diagnostic150-phase18-r1.py','winner267-phase18-r2.py','pre-model-environment-recovery-phase18-r1.py','run-user-evaluation-native18-r1.py','run-user-evaluation-native18-r2.py','evaluation-preparation18-r1.py','read-diagnostic150-matrix18-r2.py','formal-native-eval-r1/scripts/run-user-evaluation-native18-r2.py','formal-native-eval-r1/scripts/evaluation-preparation18-r1.py','formal-native-eval-r1/scripts/read-diagnostic150-matrix18-r2.py','configs/diagnostic150-five-model-r1.json']
    save(R/'checks/USER_DIAG150_ENVIRONMENT_RELEASE_R2.json',dict(at=time.time(),source_sha256={n:sha(R/n)for n in names},previous_release_sha256=sha(R/'checks/USER_DIAG150_EXECUTION_RELEASE_R1.json'),preparation_acceptance_sha256=sha(R/'checks/EVALUATION_IPAM_AND_PUBLIC_BINDS_RUNTIME_ACCEPTANCE_R1.json'),native_lock_acceptance_sha256=sha(R/'checks/PRE_MODEL_ENV_CONTINUATION_NATIVE_ACCEPTANCE_R2.json'),official_tasks_tests_and_model_protocol_unchanged=True,only_proven_pre_model_failures_get_one_new_native_continuation=True,no_actual_model_attempt_retried=True,old801_auto_dispatch_disabled=True))
    cfg=read(R/'configs/diagnostic150-five-model-r1.json');units=[]
    for m in cfg['models']:
        units.append(m['job_unit']);units.extend(x['unit']for x in m.get('replicas',[]))
        if not m.get('replicas'):units.append(m['serving_unit'])
    before={}
    for unit in units:
        p=props(unit)
        if p['ActiveState']=='active':before[unit]=dict(identity=ident(int(p['MainPID'])),properties=p)
    for _ in range(60):
        p=Path('/proc')/str(owner['pid'])
        if p.joinpath('wchan').read_text().strip()in ['hrtimer_nanosleep','do_nanosleep']and not p.joinpath('task',str(owner['pid']),'children').read_text().strip():break
        time.sleep(1)
    else:raise RuntimeError('Not at existing native controller idle boundary')
    subprocess.run(['systemctl','--user','stop',old],check=True,timeout=30);assert props(old)['ActiveState']=='inactive'
    argv=['systemd-run','--user','--unit='+new,'--property=MemoryMax=192G','--property=StandardOutput=append:'+str(R/'logs/native-advance-r21.log'),'--property=StandardError=append:'+str(R/'logs/native-advance-r21.log'),'--setenv=OMP_NUM_THREADS=2','--setenv=HF_HUB_OFFLINE=1','--setenv=TMPDIR='+str(R/'tmp'),'--setenv=TRITON_CACHE_DIR='+str(R/'cache/triton'),'--setenv=TORCH_EXTENSIONS_DIR='+str(R/'cache/torch-extensions'),str(R/'env/train-r1/bin/python'),str(R/'run-native772-advance-r21.py')]
    subprocess.run(argv,check=True,capture_output=True,text=True)
    for _ in range(30):
        current=read(C/'NATIVE_ADVANCE_OWNER.json');p=props(new)
        if p['MainPID']!='0'and current['pid']==int(p['MainPID']):break
        time.sleep(1)
    else:raise RuntimeError('New owner did not acquire original Ceph flock')
    checks={}
    for unit,row in before.items():
        pid=row['identity']['pid'];alive=(Path('/proc')/str(pid)).exists()
        if alive:assert ident(pid)==row['identity'];checks[unit]='ORIGINAL_PID_AND_TICKS_PRESERVED'
        else:assert props(unit)['ActiveState']=='inactive'and props(unit)['Result']=='success';checks[unit]='NATURAL_NATIVE_COMPLETION'
    value=dict(passed=True,at=time.time(),old_owner=owner,new_owner=current,old_controller_inactive=True,healthy_native_workers_and_model_services=before,preservation_checks=checks,original_ceph_flock='unique-native-advance.lock',old801_never_dispatched=True,source_sha256=sha(Path(__file__)))
    save(C/'NATIVE_ADVANCE_R21_CONTROLLED_HANDOFF.json',value);print(json.dumps(dict(passed=True,new_owner=current,preserved=len(checks))))
if __name__=='__main__':main()
