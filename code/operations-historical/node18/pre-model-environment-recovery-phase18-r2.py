"""One bounded continuation of proven pre-model setup failures per fixed checkpoint."""
import importlib,json,subprocess,time
from pathlib import Path
phase=importlib.import_module('diagnostic150-phase18-r1');prep=importlib.import_module('evaluation-preparation18-r1')
R=phase.R;E=phase.E;C=phase.C;read=phase.read;sha=phase.sha;save=phase.save;props=phase.props

def launch(model,owner,recovery=False):
    tag=model['tag'];prefix='PRE_MODEL_ENV_RECOVERY_'+tag if recovery else 'SELECTED267'
    admission=E/'manifests'/(prefix+'_ADMISSION_R1.json');status=props(model['job_unit'])
    if admission.exists():return dict(tag=tag,status='NATIVE_JOB_EXISTING',unit=status)
    live=phase.ready(model)
    if live is None:return dict(tag=tag,status='SERVING_NOT_READY')
    assert status['LoadState']=='not-found'and not(E/'jobs'/model['job_name']).exists()
    source=E/'scripts/run-user-evaluation-native18-r2.py'
    save(admission,dict(unique_controller_owner=owner,at=time.time(),model=model,replicas=live,source_sha256=sha(source),pre_model_continuation=recovery))
    argv=['systemd-run','--user','--unit='+model['job_unit'],'--property=MemoryMax=32G',
        '--property=StandardOutput=append:'+str(R/'logs'/('native-'+prefix+'.log')),
        '--property=StandardError=append:'+str(R/'logs'/('native-'+prefix+'.log')),
        str(R/'env/harbor-native-eval-r1/bin/python'),str(source),tag]
    if recovery:argv+=['--recovery']
    subprocess.run(argv,check=True,capture_output=True,text=True)
    return dict(tag=tag,status='NATIVE_JOB_STARTED',unit=props(model['job_unit']))


def advance(owner,state):
    assert read(C/'NATIVE_ADVANCE_OWNER.json')==owner
    cfg=read(R/'configs/diagnostic150-five-model-r1.json');models={m['tag']:m for m in cfg['models']}
    plan=read(E/'manifests/DIAGNOSTIC150_TRIAL_PLAN_R1.json');rows=[]
    for tag,original in models.items():
        prefix='PRE_MODEL_ENV_RECOVERY_'+tag;path=E/'manifests'/('PRE_MODEL_ENV_RECOVERY_PLAN_'+tag+'_R1.json')
        done=E/'checks'/(prefix+'_AUDIT_COMPLETE_R1.json')
        if done.exists():rows.append(dict(tag=tag,status='COMPLETE',proof_sha256=sha(done)));continue
        base_terminal=E/'checks'/('DIAGNOSTIC30_NATIVE_ALL_TERMINAL_'+tag+'.json')
        if not base_terminal.exists():rows.append(dict(tag=tag,status='WAIT_ORIGINAL_NATIVE_JOB',no_duplicate_pending_dispatch=True));continue
        if tag=='new-m1-e3-diag'and not(C/'EPOCH3_ORIGINAL_NINE_LIFECYCLE_COMPLETE_R1.json').exists():
            rows.append(dict(tag=tag,status='WAIT_ORIGINAL_NINE_LIFECYCLE',no_duplicate_pending_dispatch=True));continue
        if tag=='new-m1-e3-diag'and not path.exists():
            subprocess.run([str(R/'env/harbor-native-eval-r1/bin/python'),str(R/'sync-closed-e3-evidence18-r1.py')],check=True,timeout=14400)
        if not path.exists():
            eligible=[]
            for item in plan['trials']:
                if item['tag']!=tag:continue
                directory=prep.resolve_original(item,models);evidence=prep.pre_model_failure(directory)
                if evidence:
                    row=dict(item,**evidence,trial_name=item['trial_name']+'__env-recovery1',reuse_existing_trial=False);eligible.append(row)
            model=dict(original)
            if not model.get('replicas'):model['replicas']=[dict(port=model['port'],unit=model['serving_unit'],gpu_index=model['gpu_index'],gpu_uuid=model['gpu_uuid'])]
            model.update(new_trials=len(eligible),concurrency=original.get('concurrency',2),
                job_name='qwen35-new772-'+tag+'-premodel-env-recovery-20261102-r1',
                job_unit='qwen35-new772-premodel-env-'+tag+'-20261102-r1.service')
            value=dict(at=time.time(),tag=tag,model=model,trials=eligible,expected=len(eligible),
                original_model_attempts_retried=0,max_continuations_per_logical_identity=1,
                original_first_pass_results_kept=True,official_task_identity_unchanged=True,
                source_sha256=sha(Path(__file__)),ipam_manifest_sha256=sha(E/'manifests/EVALUATION417_EXPLICIT_IPAM_R1.json'))
            save(path,value)
        registered=read(path)
        if not registered['trials']:
            save(done,dict(at=time.time(),terminal=0,no_eligible_pre_model_setup_failures=True,plan_sha256=sha(path)))
            rows.append(dict(tag=tag,status='COMPLETE',proof_sha256=sha(done)));continue
        proof=read(R/'checks/EVALUATION_IPAM_AND_PUBLIC_BINDS_RUNTIME_ACCEPTANCE_R1.json');assert proof['passed']
        row=launch(registered['model'],owner,recovery=True)
        progress=E/'checks'/(prefix+'_STATUS_R1.json')
        if progress.exists():row['progress']=read(progress)
        rows.append(row)
    state['pre_model_environment_continuations']=dict(models=rows,complete=all(x['status']=='COMPLETE'for x in rows),original_model_attempts_retried=0)
