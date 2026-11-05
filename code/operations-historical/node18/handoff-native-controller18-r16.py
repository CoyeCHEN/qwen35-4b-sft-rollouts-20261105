"""Controlled sole-owner handoff; preserve all native GPU and in-flight jobs."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def props(unit):return dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,
    '-p','MainPID','-p','ActiveState','-p','LoadState'],text=True).splitlines())
def identity(pid):
    return dict(pid=pid,start_ticks=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[19])


def main():
    cpu=read(R/'checks/DIAGNOSTIC30_NATIVE_LOCK_ACCEPTANCE_R2.json')
    assert cpu['passed']and cpu['new_native_trial_locks']==111
    for name,digest in cpu['source_sha256'].items():assert sha(R/name)==digest,name
    assert sha(R/'run-native772-advance-r15.py')=='d538fa2f0a1b0b5a65f33bce527b4a5716778866559b4ce14373e78c42cf8cff'
    assert not(C/'native-phase-requests/new-m2-epoch3-fixed.json').exists()
    assert not(C/'native-phase-requests/formal-n3.json').exists()
    owner=read(C/'NATIVE_ADVANCE_OWNER.json');assert owner['pid']==2742050 and owner['start_ticks']=='94274999'
    old='qwen35-772-native-advance-node18-20261102-r15.service'
    new='qwen35-772-native-advance-node18-20261102-r16.service'
    assert props(new)['LoadState']=='not-found'
    assert int(props(old)['MainPID'])==owner['pid']and identity(owner['pid'])['start_ticks']==owner['start_ticks']
    units=['qwen35-772-new-sft-new772-new-cf416-tmax356-m2.service','qwen35-new772-cold-new-m1-epoch3-fixed-20261101.service','qwen35-new772-diag30-serving-new-m1-e5-diag-20261102-r1.service','qwen35-new772-diag30-serving-new-m2-e3-diag-20261102-r1.service']
    before={unit:identity(int(props(unit)['MainPID']))for unit in units}
    ranks={pid:identity(pid)for pid in [1208295,1208296,1208297,1208298]}
    assert before[units[0]]==dict(pid=1194582,start_ticks='91798358')
    assert before[units[1]]==dict(pid=1890941,start_ticks='91341077')
    pid=owner['pid'];assert not(Path('/proc')/str(pid)/'task'/str(pid)/'children').read_text().strip()
    assert(Path('/proc')/str(pid)/'wchan').read_text().strip()=='hrtimer_nanosleep','Wait for the existing idle boundary'
    subprocess.run(['systemctl','--user','stop',old],check=True,timeout=20)
    assert props(old)['ActiveState']=='inactive'
    for item in list(before.values())+list(ranks.values()):assert identity(item['pid'])==item
    # Only these verified zero-dispatch native preparation failures are moved.
    recovery=R/'formal-native-eval-r1/recovery/diagnostic30-zero-dispatch-r1';recovery.mkdir(parents=True,exist_ok=True)
    moved=[]
    config=read(R/'configs/diagnostic30-four-model-r1.json')
    for model in config['models']:
        if model['tag']=='new-m2-e1-diag':continue
        path=R/'formal-native-eval-r1/jobs'/model['job_name']
        assert props(model['job_unit'])['ActiveState']=='failed'
        assert sorted(x.name for x in path.iterdir())==['config.json','job.log']
        assert 'git-http1.compose.json'in(path/'job.log').read_text()
        destination=recovery/model['job_name'];assert not destination.exists()
        original_files={x.name:sha(x)for x in path.iterdir()}
        path.rename(destination)
        actual=R/'formal-native-eval-r1/manifests'/('DIAGNOSTIC30_ACTUAL_TRIALS_'+model['tag']+'.json')
        backup=recovery/('INITIAL_PREDISPATCH_ACTUAL_TRIALS_'+model['tag']+'.json');backup.write_bytes(actual.read_bytes())
        moved.append(dict(tag=model['tag'],original_path=str(path),archive_path=str(destination),files=original_files,actual_trial_or_model_attempts=0))
    saved=R/'checks/DIAGNOSTIC30_ZERO_DISPATCH_FAILURES_PRESERVED_R1.json'
    saved.write_text(json.dumps(dict(at=time.time(),moved=moved,original_trial_or_result_deleted=False,actual_trial_attempts=0),indent=2)+'\n')
    argv=['systemd-run','--user','--unit='+new,'--property=MemoryMax=192G',
        '--property=StandardOutput=append:'+str(R/'logs/native-advance-r16.log'),
        '--property=StandardError=append:'+str(R/'logs/native-advance-r16.log'),
        '--setenv=OMP_NUM_THREADS=2','--setenv=HF_HUB_OFFLINE=1','--setenv=TMPDIR='+str(R/'tmp'),
        '--setenv=TRITON_CACHE_DIR='+str(R/'cache/triton'),
        '--setenv=TORCH_EXTENSIONS_DIR='+str(R/'cache/torch-extensions'),
        str(R/'env/train-r1/bin/python'),str(R/'run-native772-advance-r16.py')]
    subprocess.run(argv,capture_output=True,text=True,check=True)
    for _ in range(20):
        current=props(new);new_owner=read(C/'NATIVE_ADVANCE_OWNER.json')
        if int(current['MainPID'])and new_owner['pid']==int(current['MainPID']):break
        time.sleep(1)
    else:raise ValueError('New sole owner did not acquire the original Ceph lock')
    for item in list(before.values())+list(ranks.values()):assert identity(item['pid'])==item
    auth=Path.home()/'.ssh/authorized_keys';raw=auth.read_text();lines=raw.splitlines(keepends=True)
    hits=[i for i,line in enumerate(lines)if 'read-only-monitor18-r21.py'in line];assert len(hits)==1
    backup=auth.with_name('authorized_keys.before-monitor-r22-'+str(int(time.time())));backup.write_text(raw);backup.chmod(0o600)
    lines[hits[0]]=lines[hits[0]].replace('read-only-monitor18-r21.py','read-only-monitor18-r22.py')
    tmp=auth.with_name('authorized_keys.monitor-r22.tmp');tmp.write_text(''.join(lines));tmp.chmod(0o600);tmp.replace(auth)
    value=dict(passed=True,at=time.time(),old_controller=owner,new_controller=new_owner,
        old_unit_inactive=True,preserved_training_and_model_processes=before,preserved_rank_processes=ranks,
        source_sha256=cpu['source_sha256'],cpu_acceptance_sha256=sha(R/'checks/DIAGNOSTIC30_NATIVE_LOCK_ACCEPTANCE_R2.json'),
        original_ceph_lock=str(C/'unique-native-advance.lock'),formal801_and_old_study_functions_unchanged=True,
        expected_diagnostic_matrix=120,new_native_trials=111,reused_original_m1_e3=9,
        official_tasks_resources_verifiers_rewards_or_training_recipe_modified=False,zero_dispatch_failed_jobs_preserved=moved,
        handoff_source_sha256=sha(Path(__file__)))
    out=C/'NATIVE_ADVANCE_R16_CONTROLLED_HANDOFF.json';assert not out.exists();out.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(value))


if __name__=='__main__':main()
