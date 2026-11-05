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
    owner=read(C/'NATIVE_ADVANCE_OWNER.json');assert owner['pid']==1467594 and owner['start_ticks']=='99871113'
    old=owner['controller_unit'];new='qwen35-772-native-advance-node18-20261103-r38-env-repair.service'
    assert old=='qwen35-772-native-advance-node18-20261103-r37-env-repair.service'
    assert props(old)['ActiveState']=='active' and props(new)['LoadState']=='not-found'
    assert read(R/'checks/R38_REAL_DEPLOYMENT_AND_NEGATIVE_GATES_R1.json')['passed']
    assert read(R/'checks/R32_REAL_READER4_AND_FUTURE267_GATES_R1.json')['passed']
    assert not(R/'checks/WINNER_FROM_COMMON30_SELECTION_R1.json').exists()
    release=read(B/'EXECUTION_RELEASE_R13.json')
    for name,digest in release['source_sha256'].items():assert sha(R/name)==digest,name
    deployed=read(R/'checks/R38_SOURCE_DEPLOYMENT_ACCEPTANCE_R1.json')
    assert sha(R/'checks/R38_SOURCE_DEPLOYMENT_ACCEPTANCE_R1.json')=='c46112db4c372a421ebfbc52ad86164e062fb1fcc41b78bc7d0983a831b3c808'
    assert deployed['passed'] and len(deployed['new_files'])==15
    env59=read(R/'checks/ENV59_SOURCE_DEPLOYMENT_ACCEPTANCE_R1.json')
    assert sha(R/'checks/ENV59_SOURCE_DEPLOYMENT_ACCEPTANCE_R1.json')=='91648d7b32a17b48d4e3bc3d6e7858d38462ba1f0f8e5603d93205934f85f60e'
    assert env59['candidate_index_sha256']=='ab9d9db0c57420f24c3cd4adb1ae7760b630c993c515fbb31228a22f10393acf'
    assert len(env59['files'])==125
    for row in deployed['new_files']+env59['files']:assert sha(Path(row['destination']))==row['sha256']
    assert sha(R/'checks/R38_REAL_DEPLOYMENT_AND_NEGATIVE_GATES_R1.json')=='5821df43e247a0cc828e669ee843d773f20c52aa6c07df083e6dbc7b4b00234b'
    added=['checks/R38_SOURCE_DEPLOYMENT_ACCEPTANCE_R1.json','checks/ENV59_SOURCE_DEPLOYMENT_ACCEPTANCE_R1.json','checks/R38_REAL_DEPLOYMENT_AND_NEGATIVE_GATES_R1.json']+[str(Path(row['destination']).relative_to(R)) if Path(row['destination']).is_relative_to(R) else row['destination'] for row in deployed['new_files']+env59['files']]
    assert sha(R/'run-native772-advance-r38-env-repair.py')=='59e56ab4a1a685e7abc282e66cac13969d4cbbbd482f2f0b567d62eabba3908c'
    recheck_proof=R/'checks/ENV59_EXTRACT_ELF_RECHECK_SOURCE_DEPLOYMENT_R1.json'
    assert sha(recheck_proof)=='26de599cc64bf648fa6a88d93d57499b70dc8f7bfe60625b9dbd5da4341b6429'
    for row in read(recheck_proof)['rows']:assert sha(Path(row['destination_path']))==row['sha256'];added.append(row['destination_path'])
    review=R/'checks/INDEPENDENT_R38_EXECUTION_GATES_REVIEW_R1.json'
    handoff_admission=read(R/'checks/NATIVE_ADVANCE_R38_HANDOFF_ADMISSION_R1.json')
    assert read(review)['passed'] and sha(review)==handoff_admission['independent_review_sha256']
    added += [str(review),str(recheck_proof),'run-native-boundary-remote-fixture18-r2.py']
    fixture=R/'lifecycle-boundary-r1/remote-docker-fixtures-source-r2';manifest=fixture/'SOURCE_MANIFEST_R2.json'
    assert sha(manifest)=='72e85fe69b43155843b6fea7b55ec7e3d014728d30f2d9bce9a7fbd1f4471c48';added.append(str(manifest))
    for row in read(manifest)['files']:assert sha(fixture/row['path'])==row['sha256'];added.append(str(fixture/row['path']))
    receipt=R/'lifecycle-boundary-r1/INSTALLED_NATIVE_PACKAGE_SOURCE_ACCEPTANCE_R3.json';assert sha(receipt)=='2f858716cd45d9512aa7741c84d985299dd98e777764ec9d8cb42061bfe75978';added.append(str(receipt))
    for row in read(receipt)['installed_source_files']:assert sha(Path(row['path']))==row['sha256'];added.append(row['path'])
    assert sha(Path(read(receipt)['harbor_wheel_path']))==read(receipt)['harbor_wheel_sha256'];added.append(read(receipt)['harbor_wheel_path'])
    for row in deployed['verify_only']:assert sha(Path(row['destination']))==row['sha256'];added.append(row['destination'])
    added+=['checks/INDEPENDENT_R38_FINAL_ENV59_MERGE_REVIEW_R1.json','checks/INDEPENDENT_SELECTED267_PIPELINE_CACHE_REVIEW_R1.json','checks/INDEPENDENT_OLD112_NATIVE_BOUNDARY_CANDIDATE_REVIEW_R1.json','checks/NATIVE_CHILD_INTERPRETER_CPU_CONTRACT_R1.json']
    source=dict(release['source_sha256']);source.update({n:sha(R/n)for n in added})
    policy=C/'ENV_PREFLIGHT30_DOCKER_ADMISSION_POLICY_R5.json'
    assert sha(policy)=='a92eab38738cff4245138c6d86087973f0f8e04cddc0297ef5c4113f729b3d35'
    import sys;sys.path[:0]=[str(R),str(E/'scripts')]
    winner=importlib.import_module('winner267-phase18-r13')
    cfg=read(R/'configs/diagnostic150-five-model-r1.json')
    units=[x['replica']['unit']for x in winner.current_roles(cfg).values()]
    units+=['qwen35-accepted30-'+m['tag']+'-20261102-r4.service'for m in cfg['models']]
    units+=['qwen35-user-synthetic32-eval-m1e3-n1-20261102-r5.service']
    units+=['qwen35-accepted30-disk-recovery-new-m2-e1-20261102-r2.service']
    units+=['qwen35-accepted30-disk-recovery-new-m1-e3-20261102-r3.service','qwen35-accepted30-disk-recovery-new-m1-e5-20261102-r3.service']
    units+=['qwen35-env-preflight59-native18-20261102-r1.service','qwen35-env-preflight59-extract-elf-recheck-native18-20261103-r1.service','qwen35-native-boundary-remote-fixtures18-20261103-r2.service','qwen35-env-preflight59-torch271-recheck-native18-20261103-r1.service','qwen35-selected267-pipeline-cache-nop-native18-20261103-r1.service']
    before={}
    for unit in units:
        state=props(unit)
        if state['ActiveState']=='active':before[unit]=dict(identity=ident(int(state['MainPID'])),properties=state)
    save(B/'EXECUTION_RELEASE_R14.json',dict(at=time.time(),source_sha256=source,
        previous_release_sha256=sha(B/'EXECUTION_RELEASE_R13.json'),docker_policy_sha256=sha(policy),
        real_storage_gated_fixed_zero_model_continuations=True,nonblocking_unique_cpu_auditor=True,
        no_job_recreated_from_unit_gc=True,all_healthy_workers_and_services_preserved=True,
        original_tasks_protocol_wheel_resources_and_model_attempts_unchanged=True))
    dropin=Path.home()/'.config/systemd/user'/(new+'.d')/'50-rsi-native-persistence.conf'
    dropin.parent.mkdir(parents=True,exist_ok=True);assert not dropin.exists()
    dropin.write_text('[Unit]\nStartLimitIntervalSec=1200\nStartLimitBurst=3\n[Service]\nRestart=on-failure\nRestartSec=20s\n')
    subprocess.run(['systemctl','--user','daemon-reload'],check=True,timeout=20)
    for _ in range(60):
        p=Path('/proc')/str(owner['pid']);assert ident(owner['pid'])['start_ticks']==owner['start_ticks']
        if p.joinpath('wchan').read_text().strip() in ['hrtimer_nanosleep','do_nanosleep'] and not p.joinpath('task',str(owner['pid']),'children').read_text().strip():break
        time.sleep(1)
    else:raise RuntimeError('Previous controller never reached a native idle boundary')
    subprocess.run(['systemctl','--user','stop',old],check=True,timeout=30)
    assert props(old)['ActiveState']=='inactive'
    log=R/'logs/native-advance-r38.log'
    subprocess.run(['systemd-run','--user','--unit='+new,'--property=MemoryMax=16G',
        '--property=StandardOutput=append:'+str(log),'--property=StandardError=append:'+str(log),
        '--setenv=PYTHONPATH='+str(R)+':'+str(E/'scripts'),
        str(R/'env/harbor-native-eval-r1/bin/python'),str(R/'run-native772-advance-r38-env-repair.py')],
        check=True,capture_output=True,text=True,timeout=10)
    for _ in range(30):
        current=read(C/'NATIVE_ADVANCE_OWNER.json');state=props(new)
        if state['MainPID']!='0' and current['pid']==int(state['MainPID']) and current['deployment_revision']=='r38-real89-environment-and-native-execution-binding':break
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
    value=dict(unactivated_R35_preserved=True,actual_env59_worker_preserved=True,passed=True,at=time.time(),old_owner=owner,new_owner=current,
        previous_controller_inactive=True,same_shared_lock_held=True,
        healthy_native_workers_and_model_services=before,preservation_checks=preserved,
        source_sha256=sha(Path(__file__)),new_controller_sha256=sha(R/'run-native772-advance-r38-env-repair.py'),
        new_release_sha256=sha(B/'EXECUTION_RELEASE_R14.json'))
    save(R/'checks/NATIVE_ADVANCE_R38_HANDOFF_COMPLETED.json',value)
    print(json.dumps(dict(passed=True,new_owner=current,preserved=len(preserved),new_release_sha256=value['new_release_sha256'])))
if __name__=='__main__':main()
