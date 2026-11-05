"""Bounded native evidence observation; this command never dispatches work."""
import json
from pathlib import Path
import subprocess
import time
import os
import importlib
import hashlib

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
W=R/'new-sft/workspace'
NEW_PROTOCOL_BINDING=R/'reliability-repair/FROZEN_RELIABILITY_SERVING_BINDINGS_R2.json'
NEW_PROTOCOL_BINDING_SHA='464aefe9e40e6ea1f210eea2a551b7ef387f122c25b6eac14e360edde0c1e529'
CURRENT_NODE17_PHASE_EXPECTED={'operation': 'NOP', 'status_key': 'ssd17_native_nop_r4', 'source_sha256': '1b356b441b48022c1d6daaa89bf0f9c9793e5395a843cf3b77cf078f307aa118', 'plan_sha256': '64e91ad917a6fb653caae12ed8c6db6ce20ddf83d202d31068206d65161cd49a', 'phase_source_sha256': '154992c1c0781d34ef9310de467dfb332e48f0de289efd701a8f8ccd069e189a'}
ACTIVITY_OBSERVER_SHA='9d8d70f1147b465ea7251459a9c1addb727d58986bf431c2f58a4b7edf336deb'


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


def observe_native_queues(activity):
    """Observe native artifacts; pending is not a prestarted environment buffer."""
    paths=list((R/'environment-preflight30').glob('CONTINUATION_ACTUAL_TRIALS_*_R4.json'))
    paths += [R/'synthetic32/eval-ACTUAL_NATIVE_TRIALS_R5.json']
    paths += [p for version in (2,3)for p in (R/('disk-failure-recovery-r'+str(version))).glob('*/ACTUAL_NATIVE_TRIALS_R*.json')]
    paths += [R/'formal-native-eval-r1/manifests/SELECTED267_ACTUAL_TRIALS_R1.json']
    paths += [R/'environment-preflight59-r1/ACTUAL_NATIVE_TRIALS_R1.json']
    # Existing frozen installed Harbor config defaults to4. If its identity changes,
    # omitted defaults are unknown rather than guessed from a historical YAML.
    native_config=R/'env/harbor-native-eval-r1/lib/python3.12/site-packages/harbor/models/job/config.py'
    default_verified=native_config.exists()and hashlib.sha256(native_config.read_bytes()).hexdigest()=='195cbc3491efa2bc9947b90d6d390370dd601ade658e13daeafaf2665eb8f638'
    active_ids={x['identity']for x in(activity or{}).get('active_cli_leases',[])}
    observed_at_node18=(activity or{}).get('observer_request_finished_at_node18')
    fresh=isinstance(observed_at_node18,(int,float))and 0<=time.time()-observed_at_node18<30
    queues=[];last=None
    for path in paths:
        if not path.exists():continue
        try:
            actual=load(path);trials=actual['trials'];folders={Path(x['trials_dir'])for x in trials}
            assert len(folders)==1;folder=folders.pop();cfg=load(folder/'config.json')or{}
            unit=folder.name+'.service'
            if path.name=='SELECTED267_ACTUAL_TRIALS_R1.json':unit=load(R/'checks/SELECTED267_MODEL_BINDING_R1.json')['job_unit']
            process=command(['systemctl','--user','show',unit,'-p','ActiveState','-p','MainPID','-p','Result'])
            if process['returncode']:raise RuntimeError('Native unit identity unknown: '+process['stderr'])
            properties=dict(x.split('=',1)for x in process['stdout'].splitlines())
            counts=dict(total=len(trials),terminal=0,live_cli=0,agent_started_without_result=0,environment_started_without_agent=0,uncreated_pending=0)
            pipeline_unknown=[];races=[]
            for trial in trials:
                target=Path(trial['trials_dir'])/trial['trial_name'];result=target/'result.json';markers=list(target.glob('ACTUAL_AGENT_START*.json'))
                identities={p.stem.removeprefix('remote-docker-')for p in target.glob('remote-docker-*.jsonl')}
                live=bool(identities&active_ids);counts['live_cli']+=int(live)
                if result.exists()and live:races.append(dict(trial_name=trial['trial_name'],reason='RESULT_APPEARED_AFTER_LIVE_CLI_PROBE'))
                if result.exists():counts['terminal']+=1
                elif markers:counts['agent_started_without_result']+=1
                elif target.exists():counts['environment_started_without_agent']+=1
                else:counts['uncreated_pending']+=1
                if target.exists()and not result.exists()and not live:
                    pipeline_unknown.append(dict(trial_name=trial['trial_name'],reason='NATIVE_PIPELINE_WITHOUT_OBSERVED_LIVE_CLI_SETUP_VERIFIER_CLEANUP_OR_UNKNOWN'))
                for marker in markers:
                    mark=load(marker);value=dict(at_node18=mark.get('at'),marker=str(marker),trial_name=trial['trial_name'])
                    if fresh and isinstance(value['at_node18'],(int,float))and value['at_node18']>observed_at_node18:
                        races.append(dict(trial_name=trial['trial_name'],reason='AGENT_STARTED_AFTER_LIVE_CLI_PROBE'))
                    if isinstance(value['at_node18'],(int,float))and(last is None or value['at_node18']>last['at_node18']):last=value
            cap=cfg.get('n_concurrent_trials',4 if default_verified else None)
            job=load(folder/'result.json')or{};stats=job.get('stats',{})
            active=properties.get('ActiveState')in['active','activating','deactivating']
            model_lane=path.parent!=R/'environment-preflight59-r1'
            queues.append(dict(actual_mapping=str(path),native_job_id=actual.get('native_job_id'),unit=unit,unit_state=properties,counts=counts,
                configured_native_slots=cap,active_native_worker=active,model_generation_expected=model_lane,native_progress={k:stats.get(k)for k in['n_running_trials','n_pending_trials','n_completed_trials','n_cancelled_trials']},
                model_slots_without_observed_cli=max(0,cap-counts['live_cli'])if model_lane and active and cap is not None and(activity or{}).get('complete')and fresh and not races else None,
                cli_and_artifact_observation_is_atomic=False,cli_probe_fresh_in_node18_clock=fresh,observation_races=races,
                pipeline_slots_requiring_lifecycle_inspection=pipeline_unknown,
                separate_prestarted_ready_buffer_count=None,separate_prestarted_ready_buffer_reason='Native queue prepares on admission; no independent ENV_READY buffer receipt exists',
                uncreated_pending_is_not_prepared_or_dispatched=True))
        except Exception as error:queues.append(dict(actual_mapping=str(path),status='UNKNOWN',error=repr(error)))
    return dict(queues=queues,last_actual_agent_start=last,last_native_dispatch_exact=None,
        last_native_dispatch_exact_reason='Existing workers persisted AgentStart and native START counts, not an independent timestamped dispatch ledger; do not relabel pending/config as dispatch',
        default_concurrency_identity_verified=default_verified,read_only=True)



def observe_new_serving_instances():
    """Read fixed cold facts and current unit/PID/argv; an idle service is leased."""
    binding=load(NEW_PROTOCOL_BINDING)
    if hashlib.sha256(NEW_PROTOCOL_BINDING.read_bytes()).hexdigest()!=NEW_PROTOCOL_BINDING_SHA:
        raise ValueError('Eight-service binding SHA differs')
    replicas=binding['bindings']
    assert sorted(row['gpu_index']for row in replicas)==list(range(8))
    source=Path(binding['sglang_source_manifest_path'])
    assert hashlib.sha256(source.read_bytes()).hexdigest()==binding['sglang_source_manifest_sha256']
    artifact=load(source);sg=next(row for row in artifact['rows']if row['kind']=='sglang')
    assert sg['sha256']==binding['sglang_wheel_sha256']
    for relative,expected in sg['modules'].items():
        actual=Path(binding['sglang_installed_root'])/relative.removeprefix('sglang/')
        assert hashlib.sha256(actual.read_bytes()).hexdigest()==expected,'Installed SG source differs: '+relative
    queried=command(['systemctl','--user','show',*[row['unit']for row in replicas],'-p','Id','-p','MainPID','-p','ActiveState'])
    if queried['returncode']:raise RuntimeError('Eight service unit query failed: '+queried['stderr'])
    units={}
    for block in queried['stdout'].strip().split('\n\n'):
        values=dict(line.split('=',1)for line in block.splitlines()if '='in line)
        if values.get('Id'):units[values['Id']]=values
    rows=[]
    for expected in replicas:
        row={k:expected[k]for k in ['gpu_index','gpu_uuid','model_id','model_path','weight_version','port','unit']}
        row.update(sglang_wheel_sha256=sg['sha256'],expected_process=expected['process_identity'])
        try:
            identity=expected['process_identity'];proc=Path('/proc')/str(identity['pid'])
            ticks=(proc/'stat').read_text().rsplit(')',1)[1].split()[19]
            argv=(proc/'cmdline').read_bytes()
            assert ticks==identity['start_ticks'] and hashlib.sha256(argv).hexdigest()==identity['argv_sha256']
            unit=units[expected['unit']]
            assert unit['ActiveState']=='active' and int(unit['MainPID'])==identity['pid']
            manifest=Path(expected['source_identity']['model_manifest_path'])
            assert hashlib.sha256(manifest.read_bytes()).hexdigest()==expected['weight_version']
            row.update(status='CURRENT_UNIT_PID_TICKS_ARGV_AND_HF_IDENTITY_VERIFIED',current_process=dict(pid=identity['pid'],start_ticks=ticks),unit_state=unit)
        except Exception as error:row.update(status='UNKNOWN',reason=repr(error))
        rows.append(row)
    return dict(bindings_path=str(NEW_PROTOCOL_BINDING),bindings_sha256=NEW_PROTOCOL_BINDING_SHA,
        services=rows,source_modules_verified=len(sg['modules']),model_generation_calls=0,
        current_identity_verified=sum(row['status']!='UNKNOWN'for row in rows),
        service_occupancy_does_not_prove_active_model_trial=True,idle_gpu_does_not_revoke_service_lease=True,
        loaded_weight_metadata_last_verified_by_cold_receipts=True,live_response_evidence_source='actual_model_activity R11 only')


def observe_ssd17_controller_status(native):
    """Only the explicitly registered current NOP; no historical fallback."""
    native=native or{};current=native.get('node17_current_phase')
    unknown=dict(node='17',status='UNKNOWN',task_environment_validation='UNKNOWN',
        empty_model_slot_reason='EXPLICIT_CURRENT_NODE17_PHASE_MISSING_OR_UNVERIFIED',
        actual_model_trial_concurrency=None,confirmed_model_trial_lower_bound=0,
        separate_prestarted_ready_buffer_count=None,extra_remote_queries=0)
    if not isinstance(current,dict):return unknown
    if current.get('operation')=='MODEL_CANARY':
        return dict(unknown,reason='MODEL_CANARY_ACTIVITY_SCHEMA_NOT_YET_FROZEN')
    try:
        assert CURRENT_NODE17_PHASE_EXPECTED is not None,'Actual R4 hashes are not registered in this draft'
        assert all(current.get(key)==value for key,value in CURRENT_NODE17_PHASE_EXPECTED.items())
        assert current['operation']=='NOP'
        phase=native[current['status_key']];execution=phase['nop']
        for field in ['source_sha256','plan_sha256']:
            assert execution[field]==current[field]
        assert phase['phase_sha256']==current['phase_source_sha256']
        assert phase.get('model_generation_calls')==0,'Current NOP evidence does not prove zero generation'
        at=phase['at'];assert isinstance(at,(int,float))
        age=time.time()-at;assert 0<=age<180
    except Exception as error:return dict(unknown,reason=repr(error))
    receipt=execution.get('receipt')or{};value=receipt.get('value')or{};row=value.get('row')or{}
    metadata=execution.get('native_metadata')or{};marker=metadata.get('actual_nop_agent_start')or{}
    raw=(metadata.get('raw_result')or{}).get('value')or{}
    actual_engine=(row.get('cleanup')or{}).get('engine_id')
    expected_engine='59c8ba22-0aa4-4aed-bc43-4e1b5989fa22'
    environment='UNKNOWN'
    if actual_engine==expected_engine and receipt:
        environment='PASS'if value.get('passed')is True else'FAIL'
    return dict(node='17',status='CURRENT_REGISTERED_NOP_IDENTITY_VERIFIED',operation='NOP',
        status_key=current['status_key'],source_sha256=current['source_sha256'],plan_sha256=current['plan_sha256'],
        phase_source_sha256=current['phase_source_sha256'],controller_observed_at=at,age_seconds=age,
        native_worker_status=execution.get('status'),native_unit=execution.get('unit'),native_job_id=value.get('native_job_id'),
        last_verified_engine_id=actual_engine,expected_engine_id=expected_engine,
        expected_socket='/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/engine17-r1/socket/docker.sock',
        engine_identity_is_prior_native_evidence_not_a_new_live_query=True,
        task_environment_validation=environment,failures=row.get('failures',[]),
        native_exception_type=(raw.get('exception_info')or{}).get('exception_type'),
        receipt_path=receipt.get('path'),receipt_sha256=receipt.get('sha256'),
        model_service_connectivity_status=phase.get('model_service_connectivity_status'),
        runtime_and_image_preparation=native.get('ssd17_image_preparation'),
        actual_nop_agent_start=bool(marker.get('value')),nop_agent_start_is_not_model_call=True,
        this_registered_lane_model_generation_calls=phase.get('model_generation_calls'),
        actual_model_trial_concurrency=0,confirmed_model_trial_lower_bound=0,model_generation_expected=False,
        separate_prestarted_ready_buffer_count=None,separate_prestarted_ready_buffer_reason='Image/runtime and NOP are not distinct prestarted ENV_READY buffers',
        empty_model_slot_reason='NOP_ENVIRONMENT_FAILED_NOT_MODEL_ZERO'if environment=='FAIL'else'CURRENT_LANE_IS_NO_MODEL_PREFLIGHT',
        extra_remote_queries=0,scope_note='Only explicit current NOP lane; model canary remains UNKNOWN until separately frozen')



def observe_serving_auxiliary_readout():
    path=R/'reliability-repair/serving-offline-readout-r1/OFFLINE_EIGHTEEN_NATIVE_EVIDENCE_REASSESSMENT_R1.json'
    if not path.exists():return dict(status='NOT_PUBLISHED',scope='SERVING_ONLY',formal_ready=False)
    expected='9682b171f9d5b045df192f41cdbe762c2bd3106c71f501a55bfb6374b51f1a1d'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==expected,'Auxiliary offline readout SHA differs'
    proof=load(path)
    assert proof['completed']==proof['reliability_passed']==18 and proof['semantic_passed']==13
    assert proof['additional_model_requests']==proof['additional_count_requests']==0 and proof['formal_ready']is False
    return dict(status='PUBLISHED_INDEPENDENT_OFFLINE_READOUT',scope='SERVING_ONLY',path=str(path),sha256=expected,
        reliability_passed=18,expected=18,semantic_passed=13,additional_model_requests=0,
        post_mm_ids_independently_observed=False,original_false_results_preserved=True,formal_ready=False)


def main():
    start=time.monotonic()
    state=dict(kind='READ_ONLY_NODE18_TRAINING_OBSERVATION_V36_EXPLICIT_CURRENT_SSD17_PHASE',checked_at=time.time(),
        automatic_dispatch=False,execution_node='18',collection_closed=True,
        data_release=load(R/'frozen-data-772-r3/DATA_RELEASE.json'),
        stage_order=['NEW-M1/M2 completed history','new protocol reliability acceptance','bounded native long A/B canary','six models common30 (180 new Trials)','independent M1 E3 synthetic32 (32 new Trials)','full89 n3 requires later reliability gate','old four deferred'],
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
    state['actual_trial_concurrency_previous_snapshot']=load(R/'checks/ACTUAL_DIAGNOSTIC_CONCURRENCY_LATEST_R3.json')
    state['final_hf_admission_failure_history']={path.name:load(path)for path in C.glob('HF_ADMISSION_BLOCKER_*.json')}
    state['final_hf_admission_blockers']={name:value for name,value in state['final_hf_admission_failure_history'].items()
        if not(Path(value['model'])/'FINAL_HF_ADMISSION.json').exists()}
    native_readout=R/'checks/NATIVE_TRAINING_READOUT_R1.json'
    if not native_readout.exists()or time.time()-native_readout.stat().st_mtime>=1200:
        state['native_training_evidence_refresh']=command([str(R/'env/train-r1/bin/python'),str(R/'read-native-training-evidence18-r1.py')])
    state['native_training_readout']=load(native_readout)
    state['unique_validation_readouts']=load(C/'NATIVE_UNIQUE_VALIDATION_READOUT_STATUS.json')
    state['old112_terminal']=load(C/'OLD112_NATIVE_ALL_TERMINAL_R2.json')
    state['old112_remote_native_status']=load(C/'OLD112_REMOTE_NATIVE_STATUS_R2.json')
    state['old_four_runs']={arm:observed_run(R/'runs/old-four-arm'/arm)for arm in 'ABCD'}
    state['old_four_unified_comparison']=load(R/'old-four-arm/checks/OLD_FOUR_UNIFIED_COMPARISON_R2.json')
    state['old112_environment']=load(R/'old-four-arm/checks/OLD112_ENV_PREFLIGHT8_MANIFEST_R1.json')
    state['old443_readouts']=load(C/'OLD443_NATIVE_READOUT_STATUS.json')
    state['old_four_deferred']=load(C/'OLD_FOUR_SAFE_DEFERRAL.json')
    curve_manifest=R/'reports/training-curves/CURVE_MANIFEST.json'
    if not curve_manifest.exists() or time.time()-curve_manifest.stat().st_mtime>=1200:
        state['curve_render']=command([str(R/'env/train-r1/bin/python'),str(R/'render-training-curves18-r1.py')])
    state['training_curves']=load(curve_manifest)
    state['common30_environment']=load(R/'environment-preflight30/ENV_PREFLIGHT_30_MANIFEST.json')
    state['remaining59_environment']=load(R/'environment-preflight59-r1/ENV_PREFLIGHT_59_MANIFEST.json')
    state['combined89_environment']=load(R/'environment-preflight59-r1/ENV_PREFLIGHT_89_MANIFEST_R1.json')
    state['priority_synthetic32_environment']=load(R/'synthetic32/ENV_PREFLIGHT_32_MANIFEST.json')
    state['priority_synthetic32_eval']=load(R/'synthetic32/eval-NATIVE_PROGRESS_R5.json')
    state['accepted_common30_native_progress']={p.name:load(p) for p in (R/'environment-preflight30').glob('CONTINUATION_PROGRESS_*_R4.json')}
    state['detached_trial_recovery']=load(R/'checks/DETACHED_THREE_RECOVERY_VERIFIER_AND_RECORDER_R2.json')
    state['empty_evaluation_slot_reason']='COMMON30_ENVIRONMENT_NOT_FROZEN' if not (state['common30_environment'] or {}).get('frozen') else 'See actual AgentStart/Recorder and native queue per-slot state'
    try:
        observer_started=time.time()
        observer=importlib.import_module('read-priority32-gpu-leases149-r11')
        if hashlib.sha256(Path(observer.__file__).read_bytes()).hexdigest()!=ACTIVITY_OBSERVER_SHA:
            raise RuntimeError('Frozen new protocol observer source identity differs')
        raw=observer.observe_from_node18(campaign_binding_manifest=NEW_PROTOCOL_BINDING,campaign_binding_manifest_sha256=NEW_PROTOCOL_BINDING_SHA)
        raw.update(observer_request_started_at_node18=observer_started,observer_request_finished_at_node18=time.time())
        state['actual_model_activity']={k:raw.get(k)for k in ['source_sha256','campaign_bindings_sha256','protocol_counts','new_campaign_binding','started_at_engine149','finished_at_engine149','seconds','actual_active_cli_count','active_cli_with_observed_response','gpu_indices_with_active_cli_and_real_response','ports_with_recent_response','all_eight_ports_active_with_real_response','unknown_project_containers','unknown_model_identity_leases','complete','eight_gpu_overlap','recorder_head_window_bytes','recorder_tail_window_bytes','no_recent_delta_is_not_an_empty_slot']}
        state['actual_model_activity']['observer_request_started_at_node18']=raw['observer_request_started_at_node18']
        state['actual_model_activity']['observer_request_finished_at_node18']=raw['observer_request_finished_at_node18']
        state['actual_model_activity']['start_events_do_not_count_as_generation']=True
        state['actual_model_activity']['observer_model_calls']=0
        state['actual_model_activity']['leases']=[{k:x.get(k)for k in ['container_id','identity','project','protocol','pid','start_ticks','model_id','port','gpu_index','gpu_uuid','activity_status','recent_generation_status','last_response_age_seconds']}for x in raw['active_cli_leases']]
    except Exception as error:state['actual_model_activity_unknown']=repr(error);raw=None
    try:state['new_serving_instances']=observe_new_serving_instances()
    except Exception as error:state['new_serving_instances']=dict(status='UNKNOWN',reason=repr(error),model_generation_calls=0)
    state['ssd17_observation']=observe_ssd17_controller_status(state['native_advance'])
    try:state['serving_auxiliary_readout']=observe_serving_auxiliary_readout()
    except Exception as error:state['serving_auxiliary_readout']=dict(status='UNKNOWN',scope='SERVING_ONLY',reason=repr(error),formal_ready=False)
    state['native_queue_observation']=observe_native_queues(raw)
    state['native_queue_observation']['scope_note']='Legacy registered native mappings; new protocol canary/pending lifecycle remains in native_advance, not inferred from absent CLI.'
    state['legacy_results_engineering_diagnosis_only']=True
    state['new_protocol_activity_is_not_task_admission']=True
    state['engine149_storage']=(state['native_advance']or{}).get('engine149_storage')
    state['storage_blocked_continuations']=(state['native_advance']or{}).get('bounded_disk_failure_continuations')
    state['common150_cpu_audit']=(state['native_advance']or{}).get('common150_cpu_audit')
    state['empty_evaluation_slot_reason']='ENGINE149_STORAGE_UNWRITABLE' if (state['engine149_storage']or{}).get('available_bytes')==0 else 'See actual AgentStart/Recorder and native queue phase'
    state['model_slot_blockers']=dict(new_protocol_admission=(state['native_advance']or{}).get('new_common30_model_admission'),
        formal_ready=(state['native_advance']or{}).get('formal_ready'),node17=state['ssd17_observation']['empty_model_slot_reason'],
        engine149_storage_is_backend_specific=state['engine149_storage'],nop_and_installation_are_not_model_trials=True)
    state['empty_evaluation_slot_reason']='See model_slot_blockers and actual CLI leases; no GPU-idle or NOP inference'
    state['actual_native_agent_start_files']={d.name:dict(agent_start_markers=len(list(d.glob('*/ACTUAL_AGENT_START*.json'))),native_terminal_results=len(list(d.glob('*/result.json')))) for d in list((R/'formal-native-eval-r1/jobs').glob('qwen35-accepted30-*'))+[R/'synthetic32/jobs/qwen35-user-synthetic32-eval-m1e3-n1-20261102-r5']}
    state['bounded_recovery_progress']={str(p.relative_to(R)):load(p)for folder in ['disk-failure-recovery-r2','disk-failure-recovery-r3'] for p in (R/folder).glob('*/PROGRESS_*.json')}
    state['actual_progress_semantics']='AgentStart markers and nonempty Recorder generation are authoritative; cached native progress may update only at Trial end.'
    state['monitor_timeout_seconds']=90
    state['observation_seconds']=time.monotonic()-start
    path=C/'CURRENT_EXECUTION_STATUS.json';temp=path.with_name(path.name+'.tmp-'+str(os.getpid()))
    temp.write_text(json.dumps(state));temp.replace(path)
    print(json.dumps(state))


if __name__=='__main__':main()
