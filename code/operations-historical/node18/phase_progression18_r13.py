"""Fixed E3 diagnostics and formal801 handoff beside the native two-stage trainer."""
import importlib
import json
from pathlib import Path
import subprocess
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
serving=importlib.import_module('cold-native-serving18-r2')
snapshot=importlib.import_module('snapshot-epoch-hf18-r1')
old_behavior=importlib.import_module('old112-phase18-r1')
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


def continue_original_e3(owner,state,actual,release):
    """Continue only original never-started tasks after the documented native OOM."""
    mode='new-m1-epoch3-unstarted';item=actual['modes'][mode]
    snapshot_path=R/'checks/E3_NATIVE_CONTROLLER_OOM_SNAPSHOT_R1.json'
    failure=load(snapshot_path)
    assert failure['controller_properties']['Result']=='oom-kill'
    assert item['original_oom_snapshot_sha256']==serving.sha(snapshot_path)
    state['epoch3_original_controller_oom']=dict(original_started=4,original_missing_results=2,
        original_unstarted=5,primary_interrupted_classification='UNKNOWN_CONTROLLER_OOM_INTERRUPTED')
    closed=C/'EPOCH3_FIXED_SERVER_CLOSED_new-m1.json'
    orphans=item['original_orphans']
    both_closed=all(orphans[t]['terminal_evidence_exists']for t in ['regex-log','chess-best-move'])
    state['epoch3_original_orphan_closure']={t:orphans[t]['terminal_evidence_exists']for t in orphans}
    if item['complete']:
        if not(E/'checks/DIAGNOSTIC30_NATIVE_ALL_TERMINAL_new-m1-e3-diag.json').exists():
            state['epoch3_expanded21_keeps_original_model_service']=True;return False
        assert item['complete']['terminal']==5 and item['complete']['original_started_trials_rerun']==0
        if not both_closed:
            state['epoch3_continuation_terminal_waiting_original_orphan_closure']=True;return False
        if not closed.exists():
            serving.stop('new-m1-epoch3-fixed')
            save(closed,dict(at=time.time(),status='terminal_partial',native_results=7,
                original_controller_interrupted_unknown=2,denominator=9,
                continuation_terminal=item['complete'],original_orphans=orphans,
                original_oom_snapshot_sha256=serving.sha(snapshot_path),
                original_results_not_fabricated=True,original_started_trials_rerun=0))
        state['epoch3_new_m1_terminal_partial']=load(closed);return True
    if 'ActiveState=active'in item['systemd']:
        state['epoch3_original_five_native_continuation_running']=item;return False
    if (C/'native-phase-requests'/(mode+'.json')).exists():
        state['epoch3_original_five_requires_inspection']=item;return False
    info=serving.info('new-m1-epoch3-fixed')
    request(mode,dict(epoch=3,model_is_final_epoch5=False,model_path=info['model_path'],
        weight_version=info['weight_version'],model_manifest=info['model_manifest'],
        original_unstarted_tasks=failure['unstarted_tasks_in_original_preregistered_order'],
        original_oom_snapshot_sha256=serving.sha(snapshot_path),
        native_runner_sha256=release['sources']['run-e3-original-unstarted149-r1.py'],
        preserved_original_orphan_max_concurrency=1,new_native_concurrency=1,
        wheel_sha256='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18',
        original_started_trials_rerun=0,primary_interrupted_results_stay_unknown=True),owner)
    state['epoch3_original_five_native_continuation_submitted']=True;return False


def diagnostics(owner,state):
    actual=remote('status');save(C/'REMOTE_NATIVE_EVAL_STATUS.json',actual)
    release=load(R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R11.json')
    # The original R4 M1 diagnostic is historical. Preserve its native termination.
    legacy=actual['modes']['new-m1-epoch3']
    if legacy['complete'] and not(C/'EPOCH3_SERVER_CLOSED_new-m1.json').exists():
        serving.stop('new-m1-epoch3')
        save(C/'EPOCH3_SERVER_CLOSED_new-m1.json',dict(at=time.time(),terminal=legacy['complete']))
    prep=actual['modes']['new11-install-preflight']
    if prep['complete']is None and 'ActiveState=active'not in prep['systemd']:
        path=C/'native-phase-requests/new11-install-preflight.json'
        if not path.exists():
            request('new11-install-preflight',dict(actual_model_attempts_expected=0,
                native_runner_sha256=release['sources']['run-new11-install-preflight149-r1.py'],
                environment_profiles_sha256=release['environment_profiles_sha256']),owner)
            state['cli_install_preflight_submitted']=True
        else:state['cli_install_preflight_requires_inspection']=prep['systemd']
    progress=prep.get('progress')or{}
    state['cli_install_preflight']={k:progress.get(k)for k in ['expected','terminal','ready','failed','actual_model_attempts']}
    prereg=load(R/'checks/EPOCH3_DIAGNOSTIC_PREREGISTRATION.json')
    if not set(prereg['tasks'])<=set(progress.get('ready_task_ids',[])):
        state['fixed_epoch3_waiting_for_actual_cli_install']=True;return
    study=R/'checks/TOKEN_ESTIMATION_INVESTIGATION_R2.json'
    if not study.exists():
        state['fixed_epoch3_waiting_for_readonly_token_investigation']=True;return
    assert load(study)['completed'] and load(study)['runtime_estimation_code_or_budgets_changed']is False
    for stage,run,step in [('new-m1','new-m1-cf416-128k-e5',120),('new-m2','new-m2-tmax356-128k-e5',75)]:
        if stage=='new-m2'and(C/'USER_GPU78_M2E3_OWNERSHIP_R1.json').exists():
            state['new_m2_epoch3_owned_by_user_gpu78_native_phase']=True
            continue
        checkpoint=R/'runs'/run/('checkpoint-'+str(step))/'CHECKPOINT_COMPLETE.json'
        if not checkpoint.exists():continue
        target=R/'epoch-models'/(stage+'-epoch3')
        if not target.exists():snapshot.snapshot(stage)
        mode=stage+'-epoch3-fixed';item=actual['modes'][mode]
        closed=C/('EPOCH3_FIXED_SERVER_CLOSED_'+stage+'.json')
        if stage=='new-m1'and (R/'checks/E3_NATIVE_CONTROLLER_OOM_SNAPSHOT_R1.json').exists():
            if continue_original_e3(owner,state,actual,release):continue
            return
        if item['complete']:
            if not closed.exists():
                serving.stop(mode);save(closed,dict(at=time.time(),terminal=item['complete']))
            continue
        if 'ActiveState=active'in item['systemd']:
            state['epoch3_fixed_diagnostic_running']=stage;return
        if 'ActiveState=active'in legacy['systemd']:
            state['fixed_epoch3_waiting_for_original_native_cleanup']=True;return
        if (C/'native-phase-requests'/(mode+'.json')).exists():
            state['fixed_epoch3_native_phase_requires_inspection']=item['systemd'];return
        deployment=serving.start(mode)
        try:info=serving.info(mode)
        except OSError:
            state['fixed_epoch3_cold_server_starting']=stage;return
        request(mode,dict(epoch=3,model_is_final_epoch5=False,model_path=info['model_path'],
            weight_version=info['weight_version'],gpu_uuid=deployment['gpu_uuid'],model_manifest=info['model_manifest'],
            preregistration_sha256=release['epoch3_preregistration_sha256'],
            repaired_epoch3_plan_sha256=release['repaired_epoch3_plan_sha256'],
            native_runner_sha256=release['sources']['run-fixed-epoch3-native-tb21149-r1.py'],
            wheel_sha256='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18',
            training_epoch4_and5_must_continue=True,old_r4_diagnostics_excluded=True),owner)
        state['epoch3_fixed_native_phase_submitted']=stage;return


FORMAL_UNIT='qwen35-new772-formal801-node18-20261102-r1.service'
JOINT_UNIT='qwen35-formal-controller18-m0-native-joint-20261102-r1.service'
E=R/'formal-native-eval-r1'


def unit_state(name):
    return subprocess.check_output(['systemctl','--user','show',name,'-p','MainPID',
        '-p','ActiveState','-p','LoadState','-p','Result'],text=True)


def mirror_formal_terminal():
    """Byte-identical derived gate copies for existing149 old-study admission."""
    import hashlib,shlex
    names=['FORMAL_801_STATUS.json','TB21_N3_FULL_COMPARISON_R7.json','FORMAL_801_ALL_TERMINAL.json']
    payload={name:(E/'checks'/name).read_text()for name in names}
    gate_sha=hashlib.sha256(payload[names[-1]].encode()).hexdigest()
    receipt=C/'FORMAL_CONTROLLER18_TERMINAL_REPLICA_R1.json'
    if receipt.exists():
        assert load(receipt)['native_gate_sha256']==gate_sha;return
    script="""import pathlib,json,hashlib,sys
r=pathlib.Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/checks')
payload=json.load(sys.stdin);expected=['FORMAL_801_STATUS.json','TB21_N3_FULL_COMPARISON_R7.json','FORMAL_801_ALL_TERMINAL.json'];assert set(payload)==set(expected)
gate=json.loads(payload[expected[-1]]);comparison=json.loads(payload[expected[1]])
assert gate['completed']and gate['actual_terminal']==801 and gate['controller_execution_node']=='18'
assert comparison['complete']and comparison['terminal']==801
assert hashlib.sha256(payload[expected[1]].encode()).hexdigest()==gate['full_comparison_sha256']
for name in expected:
 p=r/name;value=payload[name]
 if p.exists():assert p.read_text()==value,'Preserve existing derived gate: '+name
 else:
  temp=p.with_name(p.name+'.node18.tmp');temp.write_text(value);temp.replace(p)
print(json.dumps(dict(passed=True,source_execution_node='18',native_job_id=gate['native_job_id'],actual_terminal=801,replicated_names=expected,no_native_result_or_job_invented_on149=True)))
"""
    command=['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1',
        'python3 -c '+shlex.quote(script)]
    result=subprocess.run(command,input=json.dumps(payload),capture_output=True,text=True,check=True,timeout=60)
    proof=json.loads(result.stdout);assert proof['passed'];proof['native_gate_sha256']=gate_sha
    save(receipt,proof)


def formal(owner,state):
    actual=remote('status');save(C/'REMOTE_NATIVE_EVAL_STATUS.json',actual)
    installation=actual['modes']['new11-install-preflight']
    if not installation['complete']or not installation['complete'].get('passed'):
        state.update(status='WAITING_ACTUAL_CLI89_READINESS',cli_install_status=installation.get('progress'));return
    complete=E/'checks/FORMAL_801_ALL_TERMINAL.json';progress=E/'checks/FORMAL_801_STATUS.json'
    item=dict(unit=FORMAL_UNIT,systemd=unit_state(FORMAL_UNIT),
        complete=load(complete)if complete.exists()else None,progress=load(progress)if progress.exists()else None,
        actual_controller_node='18',physical_jobs_root=str(E/'jobs'))
    if item['complete']or(item.get('progress')or{}).get('terminal')==801:
        marker=C/'FORMAL_MODEL_SERVERS_CLOSED.json'
        if not marker.exists():
            for tag in ['m0','new-m1-e5','new-m2-e5']:serving.stop(tag)
            save(marker,dict(at=time.time(),formal_terminal=item['complete']))
        if item['complete']:
            assert item['complete']['response_qualification_completed']
            mirror_formal_terminal()
            actual=remote('status');save(C/'REMOTE_NATIVE_EVAL_STATUS.json',actual)
            state.update(status='FORMAL_801_TERMINAL_OLD_STUDY_NATIVE_RESUME_REQUIRED',formal_result=item)
            advance_old_study(state);old_behavior.advance(owner,state,remote,request)
        else:state.update(status='FORMAL_801_TERMINAL_READ_ONLY_COMPARISON_RUNNING',formal_result=item)
        return
    if 'ActiveState=active'in item['systemd']:
        state.update(status='FORMAL_801_NATIVE_HARBOR_RUNNING',formal_result=item);return
    if (C/'native-phase-requests/formal-n3.json').exists():
        state.update(status='FORMAL_NATIVE_JOB_REQUIRES_INSPECTION',formal_result=item);return
    release=load(R/'checks/FORMAL_CONTROLLER18_DEPLOYMENT_RELEASE_R2.json')
    deployment=R/'configs/formal-controller18-deployment-r2.json'
    assert serving.sha(deployment)==release['deployment_sha256']
    for name,digest in release['sources'].items():assert serving.sha(R/name)==digest,name
    assert load(R/'checks/NATIVE_EIGHT_RECORDER_TRANSFER_ACCEPTANCE_R1.json')['passed']
    assert load(R/'checks/FORMAL_CONTROLLER18_ALL801_CONFIG_DELTA_ACCEPTANCE_R2.json')['passed']
    correction=load(R/'checks/ADMISSION_WORKSPACE_LAYOUT_RELEASE_R1.json')
    for name,digest in correction['source_sha256'].items():assert serving.sha(R/name)==digest,name
    models={}
    for tag in ['m0','new-m1-e5','new-m2-e5']:
        deployed=serving.start(tag)
        try:live=serving.info(tag)
        except OSError:
            state.update(status='FORMAL_COLD_SERVERS_STARTING',model=tag);return
        models[live['model_id']]=dict(model_path=live['model_path'],weight_version=live['weight_version'],
            gpu_uuid=deployed['gpu_uuid'],actual_model_info=live['actual_model_info'])
    a=R/'runs/new-m1-cf416-128k-e5/FINAL_HF_ADMISSION.json';b=R/'runs/new-m2-tmax356-128k-e5/FINAL_HF_ADMISSION.json'
    assert load(a)['passed']and load(b)['passed']
    protocol={}
    for tag in ['m0','new-m1-e5','new-m2-e5']:
        state.update(status='FORMAL_NATIVE_EXTENDED_PROTOCOL_ADMISSION',protocol_model=tag);save(C/'NATIVE_ADVANCE_STATUS.json',state)
        subprocess.run([str(R/'env/train-r1/bin/python'),str(R/'admit-formal-native-cli18-r2.py'),tag],check=True,timeout=900)
        proof=R/'formal-protocol'/tag/'FORMAL_PROTOCOL_ADMISSION.json';assert load(proof)['passed']
        protocol[tag]=dict(proof_sha256=serving.sha(proof),model_id=load(proof)['model_id'],
            weight_version=load(proof)['weight_version'],wheel_sha256=load(proof)['wheel_sha256'])
    joint=R/'checks/FORMAL_CONTROLLER18_M0_NATIVE_JOINT_ACCEPTANCE_R1.json'
    if not joint.exists():
        observed=unit_state(JOINT_UNIT)
        state.update(status='FORMAL_CONTROLLER18_M0_JOINT_ADMISSION',native_joint_unit=observed)
        if 'ActiveState=active'in observed:return
        assert 'LoadState=not-found'in observed,'Preserve the existing joint fixture outcome; inspect without redispatch'
        subprocess.run(['systemd-run','--user','--unit='+JOINT_UNIT,'--property=MemoryMax=16G',
            '--property=StandardOutput=append:'+str(R/'logs/formal-controller18-m0-native-joint-r1.log'),
            '--property=StandardError=append:'+str(R/'logs/formal-controller18-m0-native-joint-r1.log'),
            str(R/'env/harbor-native-eval-r1/bin/python'),str(R/'preflight-formal-controller18-m0-native-joint-r1.py')],check=True,capture_output=True,text=True)
        return
    assert load(joint)['passed']and load(joint)['actual_model']['weight_version']==models['qwen35-new772-m0']['weight_version']
    legacy=load(R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R11.json')
    value=dict(native_extended_protocol_admissions=protocol,new_m1_epoch5_verified=True,new_m2_epoch5_verified=True,
        native_cold_servers_independently_started=True,old_four_still_deferred=True,models=models,
        environment_profiles_sha256=legacy['environment_profiles_sha256'],
        native_runner_sha256=release['sources']['formal-native-eval-r1/scripts/run-formal-native-tb2118-r2.py'],
        m1_final_hf_admission_sha256=serving.sha(a),m2_final_hf_admission_sha256=serving.sha(b),
        formal_801_trial_plan_sha256=legacy['formal_801_trial_plan_sha256'],main_native_concurrency=8,
        independent_epoch3_diagnostic_concurrency=2,epoch3_and_formal_denominators_are_separate=True,
        unique_controller_owner=owner,controller_execution_node='18',deployment_sha256=serving.sha(deployment))
    validator=importlib.import_module('native-handoff149-r11').validate_formal_protocol;validator(value)
    activation=dict(unique_controller_owner=owner,deployment_sha256=serving.sha(deployment),
        native_runner_sha256=value['native_runner_sha256'],joint_acceptance_sha256=serving.sha(joint),
        native_eight_transfer_acceptance_sha256=serving.sha(R/'checks/NATIVE_EIGHT_RECORDER_TRANSFER_ACCEPTANCE_R1.json'),
        legacy149_formal_write_disabled=True,legacy149_release_sha256=serving.sha(R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R11.json'))
    save(C/'FORMAL_CONTROLLER18_ACTIVATION_R1.json',activation)
    request_path=C/'native-phase-requests/formal-n3.json';assert not request_path.exists();save(request_path,value)
    path=E/'manifests/THREE_MODEL_COLD_SERVING_ADMISSION.json';assert not path.exists();save(path,value)
    assert 'LoadState=not-found'in item['systemd'],'Preserve the original actual formal Job'
    subprocess.run(['systemd-run','--user','--unit='+FORMAL_UNIT,'--property=MemoryMax=32G',
        '--property=StandardOutput=append:'+str(R/'logs/formal801-native18-r2.log'),
        '--property=StandardError=append:'+str(R/'logs/formal801-native18-r2.log'),
        '--setenv=TMPDIR='+str(R/'tmp'),str(R/'env/harbor-native-eval-r1/bin/python'),
        str(E/'scripts/run-formal-native-tb2118-r2.py')],check=True,capture_output=True,text=True)
    state.update(status='FORMAL_801_NATIVE_HARBOR_SUBMITTED',actual_controller_node='18')


def advance_old_study(state):
    """Use the original native four-arm launcher, resuming only complete states."""
    state['old_four_gpu_dispatch_allowed']=True
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
