"""Idle-boundary handoff of the same Ceph-locked controller; retain native workers."""
import fcntl,hashlib,importlib,json,subprocess,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control');B=R/'environment-preflight30';E=R/'formal-native-eval-r1'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def props(u):return dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',u,'-p','LoadState','-p','MainPID','-p','ActiveState','-p','Result'],text=True,timeout=5).splitlines())
def ident(pid):return dict(pid=pid,start_ticks=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[19])
def save(p,v):assert not p.exists(),p;p.write_text(json.dumps(v,indent=2)+'\n')
def main():
    owner=read(C/'NATIVE_ADVANCE_OWNER.json');assert owner['pid']==166409 and owner['start_ticks']=='97298793'
    old=owner['controller_unit'];new='qwen35-772-native-advance-node18-20261102-r32-env-repair.service'
    assert old=='qwen35-772-native-advance-node18-20261102-r31-env-repair.service'
    assert props(old)['ActiveState']=='active' and props(new)['LoadState']=='not-found'
    assert read(R/'checks/R32_REAL_STORAGE_GATE_NO_FALSE_RESTART_ACCEPTANCE_R1.json')['passed']
    assert read(R/'checks/R32_REAL_READER4_AND_FUTURE267_GATES_R1.json')['passed']
    assert not(R/'checks/WINNER_FROM_COMMON30_SELECTION_R1.json').exists()
    release=read(B/'EXECUTION_RELEASE_R8.json')
    for name,digest in release['source_sha256'].items():assert sha(R/name)==digest,name
    added=['run-native772-advance-r32-env-repair.py','disk-failure-recovery-phase18-r1.py',
        'run-accepted-common30-disk-recovery18-r2.py','materialize-public-verifier-cache149-r2.py',
        'winner267-phase18-r6.py','formal-native-eval-r1/scripts/read-diagnostic150-matrix18-r4.py',
        'formal-native-eval-r1/scripts/run-user-evaluation-native18-r5.py',
        'formal-controller18-docker-admission-r5/bin/docker',
        'disk-failure-recovery-r2/SOURCE_AUDIT_R2.json',
        'disk-failure-recovery-r2/new-m1-e3-diag/PLAN_R2.json',
        'disk-failure-recovery-r2/new-m2-e1-diag/PLAN_R2.json']
    source=dict(release['source_sha256']);source.update({n:sha(R/n)for n in added})
    policy=C/'ENV_PREFLIGHT30_DOCKER_ADMISSION_POLICY_R5.json'
    assert sha(policy)=='a92eab38738cff4245138c6d86087973f0f8e04cddc0297ef5c4113f729b3d35'
    import sys;sys.path[:0]=[str(R),str(E/'scripts')]
    winner=importlib.import_module('winner267-phase18-r6')
    cfg=read(R/'configs/diagnostic150-five-model-r1.json')
    units=[x['replica']['unit']for x in winner.current_roles(cfg).values()]
    units+=['qwen35-accepted30-'+m['tag']+'-20261102-r4.service'for m in cfg['models']]
    units+=['qwen35-user-synthetic32-eval-m1e3-n1-20261102-r5.service']
    before={}
    for unit in units:
        state=props(unit)
        if state['ActiveState']=='active':before[unit]=dict(identity=ident(int(state['MainPID'])),properties=state)
    save(B/'EXECUTION_RELEASE_R9.json',dict(at=time.time(),source_sha256=source,
        previous_release_sha256=sha(B/'EXECUTION_RELEASE_R8.json'),docker_policy_sha256=sha(policy),
        real_storage_gated_fixed_zero_model_continuations=True,nonblocking_unique_cpu_auditor=True,
        no_job_recreated_from_unit_gc=True,all_healthy_workers_and_services_preserved=True,
        original_tasks_protocol_wheel_resources_and_model_attempts_unchanged=True))
    for _ in range(60):
        p=Path('/proc')/str(owner['pid']);assert ident(owner['pid'])['start_ticks']==owner['start_ticks']
        if p.joinpath('wchan').read_text().strip() in ['hrtimer_nanosleep','do_nanosleep'] and not p.joinpath('task',str(owner['pid']),'children').read_text().strip():break
        time.sleep(1)
    else:raise RuntimeError('Previous controller never reached a native idle boundary')
    subprocess.run(['systemctl','--user','stop',old],check=True,timeout=30)
    assert props(old)['ActiveState']=='inactive'
    log=R/'logs/native-advance-r32.log'
    subprocess.run(['systemd-run','--user','--unit='+new,'--property=MemoryMax=16G',
        '--property=StandardOutput=append:'+str(log),'--property=StandardError=append:'+str(log),
        '--setenv=PYTHONPATH='+str(R)+':'+str(E/'scripts'),
        str(R/'env/harbor-native-eval-r1/bin/python'),str(R/'run-native772-advance-r32-env-repair.py')],
        check=True,capture_output=True,text=True,timeout=10)
    for _ in range(30):
        current=read(C/'NATIVE_ADVANCE_OWNER.json');state=props(new)
        if state['MainPID']!='0' and current['pid']==int(state['MainPID']) and current['deployment_revision']=='r32-storage-gated-continuations-and-native267':break
        time.sleep(1)
    else:raise RuntimeError('New controller did not acquire the same Ceph lock')
    with(C/'unique-native-advance.lock').open('a')as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:pass
        else:raise AssertionError('New owner failed to hold the unique shared lock')
    preserved={}
    for unit,row in before.items():
        path=Path('/proc')/str(row['identity']['pid'])
        if path.exists():assert ident(row['identity']['pid'])==row['identity'];preserved[unit]='ORIGINAL_PID_AND_TICKS_PRESERVED'
        else:
            state=props(unit);assert state['ActiveState']=='inactive' and state['Result']=='success';preserved[unit]='NATURAL_NATIVE_COMPLETION'
    value=dict(passed=True,at=time.time(),old_owner=owner,new_owner=current,
        previous_controller_inactive=True,same_shared_lock_held=True,
        healthy_native_workers_and_model_services=before,preservation_checks=preserved,
        source_sha256=sha(Path(__file__)),new_controller_sha256=sha(R/'run-native772-advance-r32-env-repair.py'),
        new_release_sha256=sha(B/'EXECUTION_RELEASE_R9.json'))
    save(R/'checks/NATIVE_ADVANCE_R32_HANDOFF_COMPLETED.json',value)
    print(json.dumps(dict(passed=True,new_owner=current,preserved=len(preserved),new_release_sha256=value['new_release_sha256'])))
if __name__=='__main__':main()
