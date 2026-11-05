"""Activate the latest explicit scope through the original single Ceph owner."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1'
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def props(u):return dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',u,'-p','LoadState','-p','MainPID','-p','ActiveState'],text=True).splitlines())
def identity(pid):return dict(pid=pid,start_ticks=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[19])
def save(p,v):
    assert not p.exists(),p
    p.write_text(json.dumps(v,indent=2)+'\n')

CPU=r'''
import asyncio,importlib,json,sys,time,os
from pathlib import Path
from collections import Counter
from harbor.job import Job
from harbor.models.job.config import JobConfig
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1'
sys.path.insert(0,str(E/'scripts'))
m=importlib.import_module('run-user-evaluation-native18-r1');native=m.native
os.environ['OPENAI_API_KEY']='node18-local'
async def run():
 counts={}
 for tag in ['new-m2-e1-diag','new-m2-e5-diag','selected267']:
  _,model,cfg,plan=m.configuration('new-m2-e5-diag'if tag=='selected267'else tag)
  if tag=='selected267':
   original=JobConfig.model_validate_json(native.selected_config(m.read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')).read_text());cfg.tasks=original.tasks;cfg.n_attempts=3
   cfg.agents[0].model_name='openai/qwen35-new772-selected30-winner';cfg.agents[0].kwargs['config']['model']['id']='qwen35-new772-selected30-winner'
   plan['trials']=[dict(x,model_name=cfg.agents[0].model_name,trial_name=x['task_id']+'__selected30-winner-n3-r'+str(x['repetition']))for x in m.read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')['trials']if x['model_name']=='openai/qwen35-new772-m0']
  cfg.job_name='cpu-user-scope-'+tag+'-'+str(time.time_ns());cfg.jobs_dir=E/'diagnostics'
  job=await Job.create(cfg);byid={(x['task_id'],x['repetition']):x for x in plan['trials']};seen=Counter();ordered=[]
  for trial in job._trial_configs:
   task=trial.task.path.name;seen[task]+=1;ordered.append(byid[(task,seen[task])])
  effective=native.apply_trial_overrides(job._trial_configs,dict(trials=ordered),m.read(E/'configs/environment-profiles-agent-deps-r2.json'),namespace='q35userscopepreflight')
  assert len(effective)==(267 if tag=='selected267'else 30)
  assert all(x['agent']['kwargs']['wheel_sha256']=='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'for x in effective)
  assert cfg.retry.max_retries==0
  counts[tag]=dict(native_trial_configs=len(effective),native_job_lock=str(job._job_lock_path),actual_model_or_task_calls=0)
 print(json.dumps(dict(passed=True,cases=counts,new_unstarted_diagnostic_configs=60,selected_n3_configs=267,actual_model_or_task_calls=0)))
asyncio.run(run())
'''


def main():
    owner=read(C/'NATIVE_ADVANCE_OWNER.json');assert owner['pid']==2590050 and owner['start_ticks']=='94968491'
    old='qwen35-772-native-advance-node18-20261102-r19.service';new='qwen35-772-native-advance-node18-20261102-r20.service'
    assert props(old)['ActiveState']=='active'and props(new)['LoadState']=='not-found'
    assert not(C/'native-phase-requests/formal-n3.json').exists()
    cfg=read(R/'configs/diagnostic150-five-model-r1.json');assert cfg['expected_trials']==150
    for model in cfg['models']:
        if not model.get('legacy_running'):
            p=R/'checks'/('DIAGNOSTIC150_MODEL_BINDING_'+model['tag']+'.json');assert not p.exists();save(p,model)
    result=subprocess.run([str(R/'env/harbor-native-eval-r1/bin/python'),'-'],input=CPU,capture_output=True,text=True,timeout=120)
    if result.returncode:raise RuntimeError(result.stderr[-5000:])
    cpu=json.loads(result.stdout);assert cpu['passed'];save(R/'checks/USER_DIAG150_NATIVE_LOCK_ACCEPTANCE_R1.json',cpu)
    probe="import os,json;from pathlib import Path;m={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines()};print(json.dumps(dict(cpus=os.cpu_count(),memory_available=m['MemAvailable'],root_available=os.statvfs('/').f_bavail*os.statvfs('/').f_frsize)))"
    remote=subprocess.run(['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1','python3 -c '+shlex.quote(probe)],capture_output=True,text=True,check=True,timeout=20)
    available=json.loads(remote.stdout);sample=read(E/'manifests/DIAGNOSTIC30_SAMPLING_MANIFEST_R1.json')['selected_task_identities']
    cpus=sorted([x['original_environment']['cpus']for x in sample]*5,reverse=True)
    memories=sorted([x['original_environment']['memory_mb']for x in sample]*5,reverse=True)
    assert sum(cpus[:17])<=available['cpus']and sum(memories[:17])*1024**2<available['memory_available']*.8
    save(R/'checks/USER_DIAG150_RESOURCE_BOUND_R1.json',dict(at=time.time(),engine149=available,max_native_pipelines=17,
        upper_cpu_requested=sum(cpus[:17]),upper_task_memory_mib=sum(memories[:17]),
        official_resources_unchanged=True,model_gpus=8,legacy_job_concurrency_unchanged=True))
    auth=Path.home()/'.ssh/authorized_keys';raw=auth.read_text();lines=raw.splitlines(keepends=True)
    hits=[i for i,line in enumerate(lines)if 'permitopen="127.0.0.1:18306"'in line and'permitopen="127.0.0.1:18307"'in line];assert len(hits)==1
    backup=auth.with_name('authorized_keys.before-diag150-'+str(int(time.time())));backup.write_text(raw);backup.chmod(0o600)
    assert 'permitopen="127.0.0.1:18308"'not in lines[hits[0]]
    lines[hits[0]]=lines[hits[0]].replace('permitopen="127.0.0.1:18307"','permitopen="127.0.0.1:18307",permitopen="127.0.0.1:18308",permitopen="127.0.0.1:18309"')
    temp=auth.with_name('authorized_keys.diag150.tmp');temp.write_text(''.join(lines));temp.chmod(0o600);temp.replace(auth)
    names=['run-native772-advance-r20.py','diagnostic150-phase18-r1.py','winner267-phase18-r1.py',
        'run-user-evaluation-native18-r1.py','read-diagnostic150-matrix18-r1.py',
        'formal-native-eval-r1/scripts/run-user-evaluation-native18-r1.py',
        'formal-native-eval-r1/scripts/read-diagnostic150-matrix18-r1.py','configs/diagnostic150-five-model-r1.json']
    save(R/'checks/USER_DIAG150_EXECUTION_RELEASE_R1.json',dict(at=time.time(),source_sha256={name:sha(R/name)for name in names},
        explicit_user_scope_override_sha256=sha(C/'USER_EVALUATION_SCOPE_OVERRIDE_R1.json'),native_cpu_acceptance_sha256=sha(R/'checks/USER_DIAG150_NATIVE_LOCK_ACCEPTANCE_R1.json'),
        actual_runtime_validation='M0 native20calls/all11tools/reward1/Verifier0/completeRecorder; all candidate HF manifests; M2E5 normal8call/finish/prefix admission.',
        m2_extended_model_smoke_failure_kept_not_relabeled_success=True,old801_auto_dispatch_disabled=True,
        new_unstarted_jobs_reuse_native_harbor=True,eight_gpu_roles_explicit_before_ready=True))
    units=['qwen35-new772-cold-new-m1-epoch3-fixed-20261101.service','qwen35-new772-cold-new-m2-e5-20261101.service',
        'qwen35-new772-diag30-serving-new-m1-e5-diag-20261102-r1.service','qwen35-new772-diag30-serving-new-m2-e3-diag-20261102-r1.service']
    units+=['qwen35-new772-diag30-native-'+tag+'-20261102-r2.service'for tag in ['new-m1-e3-diag','new-m1-e5-diag','new-m2-e3-diag']]
    before={unit:identity(int(props(unit)['MainPID']))for unit in units}
    for _ in range(60):
        base=Path('/proc')/str(owner['pid'])
        if base.joinpath('wchan').read_text().strip()in ['hrtimer_nanosleep','do_nanosleep']and not base.joinpath('task',str(owner['pid']),'children').read_text().strip():break
        time.sleep(1)
    else:raise RuntimeError('Wait for native idle boundary')
    subprocess.run(['systemctl','--user','stop',old],check=True,timeout=60);assert props(old)['ActiveState']=='inactive'
    argv=['systemd-run','--user','--unit='+new,'--property=MemoryMax=192G',
        '--property=StandardOutput=append:'+str(R/'logs/native-advance-r20.log'),
        '--property=StandardError=append:'+str(R/'logs/native-advance-r20.log'),
        '--setenv=OMP_NUM_THREADS=2','--setenv=HF_HUB_OFFLINE=1','--setenv=TMPDIR='+str(R/'tmp'),
        '--setenv=TRITON_CACHE_DIR='+str(R/'cache/triton'),'--setenv=TORCH_EXTENSIONS_DIR='+str(R/'cache/torch-extensions'),
        str(R/'env/train-r1/bin/python'),str(R/'run-native772-advance-r20.py')]
    subprocess.run(argv,check=True,capture_output=True,text=True)
    for _ in range(30):
        new_owner=read(C/'NATIVE_ADVANCE_OWNER.json');current=props(new)
        if int(current['MainPID'])and new_owner['pid']==int(current['MainPID']):break
        time.sleep(1)
    else:raise RuntimeError('R20 did not acquire original Ceph lock')
    assert all(identity(value['pid'])==value for value in before.values())
    value=dict(passed=True,at=time.time(),old_owner=owner,new_owner=new_owner,
        healthy_original_model_and_native_jobs_preserved=before,old_controller_inactive=True,
        all_task_trials_rewards_and_training_unchanged=True,old_801_never_dispatched=True,
        explicit_user_update_applied=True,planned_common30_model_tasks=150,selected_full_n3_trials=267,
        source_sha256=sha(Path(__file__)))
    save(C/'NATIVE_ADVANCE_R20_CONTROLLED_HANDOFF.json',value);print(json.dumps(value))


if __name__=='__main__':main()
