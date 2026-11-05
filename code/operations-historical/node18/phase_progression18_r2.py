"""Fixed E3 diagnostics and formal801 handoff beside the native two-stage trainer."""
import importlib
import json
from pathlib import Path
import subprocess
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
serving=importlib.import_module('cold-native-serving18-r1')
snapshot=importlib.import_module('snapshot-epoch-hf18-r1')
def load(p):return json.loads(p.read_text())
def save(p,value):
    temp=p.with_name(p.name+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.replace(p)


def remote(mode,payload=None):
    args=['ssh','-F',str(R/'control-ssh/native149.conf'),'qwen35-native-harbor149',mode]
    result=subprocess.run(args,input=json.dumps(payload)if payload is not None else '',
        capture_output=True,text=True,timeout=20)
    if result.returncode:raise RuntimeError('Native149 handoff '+mode+': '+result.stderr[-1000:])
    return json.loads(result.stdout)


def request(mode,payload,owner):
    folder=C/'native-phase-requests';folder.mkdir(exist_ok=True)
    path=folder/(mode+'.json')
    if path.exists():payload=load(path)
    else:
        payload['unique_controller_owner']=owner
        save(path,payload)
    result=remote(mode,payload)
    save(folder/(mode+'-ack.json'),result)
    return result


def diagnostics(owner,state):
    ready=[]
    for stage,run,step in [('new-m1','new-m1-cf416-128k-e5',120),('new-m2','new-m2-tmax356-128k-e5',75)]:
        target=R/'epoch-models'/(stage+'-epoch3')
        if (R/'runs'/run/('checkpoint-'+str(step))/'CHECKPOINT_COMPLETE.json').exists():
            if not target.exists():snapshot.snapshot(stage)
            ready.append(stage)
    state['epoch3_snapshots_ready']=ready
    if not ready:return
    actual=remote('status');save(C/'REMOTE_NATIVE_EVAL_STATUS.json',actual)
    release=load(R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R2.json')
    for stage in ready:
        mode=stage+'-epoch3';item=actual['modes'][mode]
        if item['complete']:
            if not(C/('EPOCH3_SERVER_CLOSED_'+stage+'.json')).exists():
                serving.stop(mode);save(C/('EPOCH3_SERVER_CLOSED_'+stage+'.json'),dict(at=time.time(),terminal=item['complete']))
            continue
        if 'ActiveState=active' in item['systemd']:
            state['epoch3_diagnostic_running']=stage;return
        other='new-m2'if stage=='new-m1'else'new-m1'
        other_mode=other+'-epoch3'
        if 'ActiveState=active' in actual['modes'][other_mode]['systemd']:
            state['epoch3_waiting_for_diagnostic_gpu']=stage;return
        if (C/'native-phase-requests'/(mode+'.json')).exists():
            # A received but failed/stopped native Job is preserved; never create a second attempt.
            state['epoch3_native_phase_requires_inspection']=item;return
        serving.start(mode)
        try:info=serving.info(mode)
        except OSError:
            state['epoch3_native_cold_server_starting']=stage;return
        payload=dict(epoch=3,model_is_final_epoch5=False,model_path=info['model_path'],
            weight_version=info['weight_version'],gpu_uuid=serving.start(mode)['gpu_uuid'],
            preregistration_sha256=release['epoch3_preregistration_sha256'],
            native_runner_sha256=release['sources']['run-epoch3-native-tb21149-r1.py'],
            model_manifest=info['model_manifest'],training_epoch4_and5_must_continue=True)
        request(mode,payload,owner)
        state['epoch3_native_phase_submitted']=stage;return


def formal(owner,state):
    actual=remote('status');save(C/'REMOTE_NATIVE_EVAL_STATUS.json',actual)
    item=actual['modes']['formal-n3']
    if item['complete'] or (item.get('progress')or{}).get('terminal')==801:
        marker=C/'FORMAL_MODEL_SERVERS_CLOSED.json'
        if not marker.exists():
            for tag in ['m0','new-m1-e5','new-m2-e5']:serving.stop(tag)
            save(marker,dict(at=time.time(),formal_terminal=item['complete']))
        if item['complete']:
            state.update(status='FORMAL_801_TERMINAL_OLD_STUDY_NATIVE_RESUME_REQUIRED',formal_result=item)
            advance_old_study(state)
        else:state.update(status='FORMAL_801_TERMINAL_READ_ONLY_COMPARISON_RUNNING',formal_result=item)
        return
    if 'ActiveState=active' in item['systemd']:
        state.update(status='FORMAL_801_NATIVE_HARBOR_RUNNING',formal_result=item);return
    if (C/'native-phase-requests/formal-n3.json').exists():
        state.update(status='FORMAL_NATIVE_JOB_REQUIRES_INSPECTION',formal_result=item);return
    models={}
    for tag in ['m0','new-m1-e5','new-m2-e5']:
        deployment=serving.start(tag)
        try:live=serving.info(tag)
        except OSError:
            state.update(status='FORMAL_COLD_SERVERS_STARTING',model=tag);return
        models[live['model_id']]=dict(model_path=live['model_path'],weight_version=live['weight_version'],
            gpu_uuid=deployment['gpu_uuid'],actual_model_info=live['actual_model_info'])
    release=load(R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R2.json')
    a=R/'runs/new-m1-cf416-128k-e5/FINAL_HF_ADMISSION.json'
    b=R/'runs/new-m2-tmax356-128k-e5/FINAL_HF_ADMISSION.json'
    assert load(a)['passed'] and load(b)['passed']
    request('formal-n3',dict(new_m1_epoch5_verified=True,new_m2_epoch5_verified=True,
        native_cold_servers_independently_started=True,old_four_still_deferred=True,models=models,
        environment_profiles_sha256=release['environment_profiles_sha256'],
        native_runner_sha256=release['sources']['run-formal-native-tb21149-r2.py'],
        m1_final_hf_admission_sha256=serving.sha(a),m2_final_hf_admission_sha256=serving.sha(b),
        formal_801_trial_plan_sha256=release['formal_801_trial_plan_sha256'],
        main_native_concurrency=8,independent_epoch3_diagnostic_concurrency=2,
        epoch3_and_formal_denominators_are_separate=True),owner)
    state['status']='FORMAL_801_NATIVE_HARBOR_SUBMITTED'


def advance_old_study(state):
    """Use the original native four-arm launcher, resuming only complete states."""
    completed=R/'old-four-arm/checks/FOUR_NATIVE_TRAINING_RUNS_COMPLETED'
    if completed.exists():
        state['status']='OLD_FOUR_NATIVE_TRAINING_COMPLETE_READOUT_PENDING'
        return
    unit='qwen35-old-four-native18-20261101-r2.service'
    props=dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,
        '-p','MainPID','-p','ActiveState','-p','LoadState','-p','Result'],text=True).splitlines())
    state['old_four_native_unit']=props
    if props['ActiveState']=='active':
        state['status']='OLD_FOUR_NATIVE_RESUMED_RESEARCH_TRAINING'
        return
    receipt=C/'OLD_FOUR_NATIVE_RESUME_REQUESTED_R2.json'
    if receipt.exists()or props['LoadState']!='not-found':
        state['status']='OLD_FOUR_NATIVE_WORKER_REQUIRES_INSPECTION'
        return
    guard=subprocess.run([str(R/'env/train-r1/bin/python'),str(R/'resume-old-four-native18-r2.py'),'--check-only'],
        capture_output=True,text=True,check=True,timeout=15)
    assert json.loads(guard.stdout)['admitted']
    save(receipt,dict(at=time.time(),formal801_completed=True,first_arm_resumes_latest_complete_native_checkpoint=True,
        worker_source_sha256=serving.sha(R/'resume-old-four-native18-r2.py'),
        cross_node_sequence_owner=str(C/'NATIVE_ADVANCE_OWNER.json')))
    command=['systemd-run','--user','--unit='+unit,'--property=MemoryMax=192G',
        '--property=StandardOutput=append:'+str(R/'logs/old-four-native-r2.log'),
        '--property=StandardError=append:'+str(R/'logs/old-four-native-r2.log'),
        str(R/'env/train-r1/bin/python'),str(R/'resume-old-four-native18-r2.py')]
    subprocess.run(command,check=True,capture_output=True,text=True)
    state['status']='OLD_FOUR_NATIVE_CHECKPOINT_RESUME_SUBMITTED'
