"""Bounded native evidence observation; this command never dispatches work."""
import json
from pathlib import Path
import subprocess
import time
import os

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
W=R/'new-sft/workspace'


def command(args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=15)
    return dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr[-500:])


def load(path):
    return json.loads(path.read_text()) if path.exists() else None


def events(path):
    if not path.exists():return []
    with path.open('rb') as stream:
        size=path.stat().st_size
        start=max(0,size-512*1024)
        header=stream.read(min(128*1024,start)) if start else b''
        stream.seek(start)
        tail=stream.read().splitlines()
        if start:tail=tail[1:]
        # Keep the original real train_begin when a long native log outgrows the tail.
        lines=(header.splitlines()[:-1] if header else [])+tail
    rows=[]
    for line in lines:
        try:rows.append(json.loads(line))
        except json.JSONDecodeError:continue
    return rows


def observed_run(folder):
    rows=events(folder/'preflight-evidence-rank0.jsonl')
    begins=[x for x in rows if x.get('event')=='train_begin']
    updates=[x for x in rows if x.get('event')=='optimizer_step']
    metrics=[x for x in rows if x.get('event')=='metrics']
    last=updates[-1]if updates else {}
    return dict(real_cuda_train_begin=bool(begins or updates),
        actual_optimizer_step=last.get('global_step'),last_update_time=last.get('time'),
        last_update_age_seconds=time.time()-last['time']if last else None,
        finite_gradients=all(v['finite'] for v in last.get('gradients',{}).values())if last else None,
        parameter_update_observed=last.get('parameter_update_observed'),
        max_memory_allocated=last.get('peak_allocated_bytes'),max_memory_reserved=last.get('peak_reserved_bytes'),
        latest_metrics=metrics[-1].get('metrics')if metrics else None,
        actual_parallelism=begins[-1].get('parallelism')if begins else None,
        native_checkpoint_names=sorted(p.name for p in folder.glob('checkpoint-*')if(p/'CHECKPOINT_COMPLETE.json').exists()),
        trainer_state=load(folder/'trainer_state.json'),
        hf_export=load(folder/'HF_EXPORT_COMPLETE.json'))


def main():
    start=time.monotonic()
    state=dict(kind='READ_ONLY_NODE18_TRAINING_OBSERVATION_V28_REAL_MODEL_ACTIVITY',checked_at=time.time(),
        automatic_dispatch=False,execution_node='18',collection_closed=True,
        data_release=load(R/'frozen-data-772-r3/DATA_RELEASE.json'),
        stage_order=['NEW-M1','NEW-M2','five checkpoints common30 (150 logical tasks)','selected winner full89 n3 (267 trials)','old four deferred'],
        native_advance=load(C/'NATIVE_ADVANCE_STATUS.json'),gpu_allocation=load(C/'FORMAL_GPU_ALLOCATION.json'))
    state['units']=command(['systemctl','--user','show',
        state['native_advance']['owner']['controller_unit'],
        'qwen35-capacity772-128k-dp4-20261101-r7.service',
        'qwen35-772-new-sft-new772-new-cf416-m1.service',
        'qwen35-772-new-sft-new772-new-cf416-tmax356-m2.service',
        '-p','Id','-p','ActiveState','-p','SubState','-p','MainPID','-p','Result'])
    state['gpu']=command(['nvidia-smi','--query-gpu=index,uuid,memory.total,memory.used,utilization.gpu','--format=csv,noheader,nounits'])
    state['gpu_processes']=command(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader,nounits'])
    state['capacity']={p.name:observed_run(p)for p in (R/'runs').glob('verify-capacity772-*')}
    state['formal_runs']={name:observed_run(R/'runs'/name)for name in ['new-m1-cf416-128k-e5','new-m2-tmax356-128k-e5']}
    state['formal_native_jobs']={p.parent.name:load(p)for p in (W/'jobs').glob('new772-*/job.json')}
    state['formal_new_m1_m2_started']=any(x['real_cuda_train_begin']for x in state['formal_runs'].values())
    state['current_stage']=(state['native_advance'] or {}).get('status') or ('NEW_M1_M2_NATIVE_TRAINING'if state['formal_new_m1_m2_started']else'REAL_CAPACITY_ACCEPTANCE')
    state['remote_native_evaluation']=load(C/'REMOTE_NATIVE_EVAL_STATUS.json')
    state['epoch3_auxiliary_blocker']=load(C/'EPOCH3_AUXILIARY_BLOCKER.json')
    state['user_diagnostic30']=load(C/'DIAGNOSTIC30_DIAGNOSTIC_STATUS_R1.json')
    state['user_diagnostic30_workers']=command(['systemctl','--user','show',
        'qwen35-new772-diag30-native-new-m1-e3-diag-20261102-r2.service',
        'qwen35-new772-diag30-native-new-m1-e5-diag-20261102-r2.service',
        'qwen35-new772-diag30-native-new-m2-e3-diag-20261102-r2.service',
        'qwen35-new772-diag150-native-new-m2-e1-diag-20261102-r1.service',
        'qwen35-new772-diag150-native-new-m2-e5-diag-20261102-r1.service',
        '-p','Id','-p','MainPID','-p','ActiveState','-p','Result'])
    state['user_diagnostic30_raw_progress']={path.stem:load(path)for path in
        (R/'formal-native-eval-r1/checks').glob('DIAGNOSTIC30_STATUS_*.json')}
    state['user_diagnostic30_comparison']=load(R/'formal-native-eval-r1/checks/DIAGNOSTIC30_MATRIX_R1.json')
    state['user_evaluation_scope']=load(C/'USER_EVALUATION_SCOPE_OVERRIDE_R1.json')
    state['common30_deployment']=load(R/'configs/diagnostic150-five-model-r1.json')
    state['pre_model_continuations']={p.stem:load(p)for p in (R/'formal-native-eval-r1/checks').glob('PRE_MODEL_ENV_RECOVERY_*_STATUS_R1.json')}
    state['selected267_progress']=load(R/'formal-native-eval-r1/checks/SELECTED267_STATUS_R1.json')
    state['selected267_complete']=load(R/'formal-native-eval-r1/checks/SELECTED267_COMPARISON_R1.json')
    try:
        observed=subprocess.run(['/usr/bin/python3',str(R/'read-active-diagnostic-trials18-r3.py')],capture_output=True,text=True,timeout=35)
        state['actual_trial_observation_returncode']=observed.returncode
        state['actual_trial_observation_error']=observed.stderr[-500:]if observed.returncode else None
    except subprocess.TimeoutExpired:state['actual_trial_observation_error']='bounded observer exceeded35s; previous proof age reported'
    state['actual_trial_concurrency']=load(R/'checks/ACTUAL_DIAGNOSTIC_CONCURRENCY_LATEST_R3.json')
    if state['actual_trial_concurrency']:
        state['actual_trial_observation_age_seconds']=time.time()-state['actual_trial_concurrency']['at']
    state['final_hf_admission_failure_history']={path.name:load(path)for path in C.glob('HF_ADMISSION_BLOCKER_*.json')}
    state['final_hf_admission_blockers']={name:value for name,value in state['final_hf_admission_failure_history'].items()
        if not(Path(value['model'])/'FINAL_HF_ADMISSION.json').exists()}
    native_readout=R/'checks/NATIVE_TRAINING_READOUT_R1.json'
    if not native_readout.exists()or time.time()-native_readout.stat().st_mtime>=1200:
        state['native_training_evidence_refresh']=command([str(R/'env/train-r1/bin/python'),str(R/'read-native-training-evidence18-r1.py')])
    state['native_training_readout']=load(native_readout)
    state['unique_validation_readouts']=load(C/'NATIVE_UNIQUE_VALIDATION_READOUT_STATUS.json')
    state['old112_terminal']=load(C/'OLD112_NATIVE_ALL_TERMINAL.json')
    state['old443_readouts']=load(C/'OLD443_NATIVE_READOUT_STATUS.json')
    state['old_four_deferred']=load(C/'OLD_FOUR_SAFE_DEFERRAL.json')
    curve_manifest=R/'reports/training-curves/CURVE_MANIFEST.json'
    if not curve_manifest.exists() or time.time()-curve_manifest.stat().st_mtime>=1200:
        state['curve_render']=command([str(R/'env/train-r1/bin/python'),str(R/'render-training-curves18-r1.py')])
    state['training_curves']=load(curve_manifest)
    state['common30_environment']=load(R/'environment-preflight30/ENV_PREFLIGHT_30_MANIFEST.json')
    state['priority_synthetic32_environment']=load(R/'synthetic32/ENV_PREFLIGHT_32_MANIFEST.json')
    state['priority_synthetic32_eval']=load(R/'synthetic32/eval-NATIVE_PROGRESS_R5.json')
    state['accepted_common30_native_progress']={p.name:load(p) for p in (R/'environment-preflight30').glob('CONTINUATION_PROGRESS_*_R4.json')}
    state['detached_trial_recovery']=load(R/'checks/DETACHED_THREE_RECOVERY_VERIFIER_AND_RECORDER_R2.json')
    state['empty_evaluation_slot_reason']='COMMON30_ENVIRONMENT_NOT_FROZEN' if not (state['common30_environment'] or {}).get('frozen') else 'See actual AgentStart/Recorder and native queue per-slot state'
    state['actual_model_activity_observer']=command([str(R/'formal-controller18-client-bin-r1/ssh'),'127.0.0.1','python3 /home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/checks/read-priority32-gpu-leases149-r2.py'])
    if state['actual_model_activity_observer']['returncode']==0:
        state['actual_model_activity']=json.loads(state['actual_model_activity_observer']['stdout'])
    state['actual_native_agent_start_files']={d.name:dict(agent_start_markers=len(list(d.glob('*/ACTUAL_AGENT_START*.json'))),native_terminal_results=len(list(d.glob('*/result.json')))) for d in list((R/'formal-native-eval-r1/jobs').glob('qwen35-accepted30-*-20261102-r4'))+[R/'synthetic32/jobs/qwen35-user-synthetic32-eval-m1e3-n1-20261102-r5']}
    state['monitor_timeout_seconds']=90
    state['observation_seconds']=time.monotonic()-start
    path=C/'CURRENT_EXECUTION_STATUS.json';temp=path.with_name(path.name+'.tmp-'+str(os.getpid()))
    temp.write_text(json.dumps(state));temp.replace(path)
    print(json.dumps(state))


if __name__=='__main__':main()
