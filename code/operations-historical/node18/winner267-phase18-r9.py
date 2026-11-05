"""Unique advance leaf: logical150 selection, drained32, then native267 cold replicas."""
import hashlib
import importlib
import json
import os
import shlex
from pathlib import Path
import subprocess
import time

phase=importlib.import_module('diagnostic150-phase18-r1')
handoff=importlib.import_module('start-priority32-cold-replicas18-r1')
R=phase.R;E=phase.E;C=phase.C;B=R/'environment-preflight30';S=R/'synthetic32'
read=phase.read;sha=phase.sha;save=phase.save;props=phase.props
MATERIALIZER_R2_REMOTE='/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/scripts/materialize-public-verifier-cache149-r2.py'
MATERIALIZER_R2_SHA='61a98ac88681925cbbd45110f9cd13cc921aee436806fbd6cea40dc6428219a4'
DISK_RECOVERY_SCOPES={
 'new-m1-e3-diag':(15,'a1400c81324a6a2018c517c925c3bd7f201c9d7e57380a52718d88472e461b8a',3),
 'new-m2-e1-diag':(25,'a29c6e0d1cd0911ee18e97006e7b3f29b08f1c40144d39ff52134345e4104e3b',2),
 'new-m1-e5-diag':(23,'4c2cffd705bc2e4d3bfd8bcf96ad6403faf50bf8bf2f44918271d06fa3fb3806',3)}
DOCKER_GATE_R5=R/'formal-controller18-docker-admission-r5/bin/docker'
DOCKER_POLICY_R5=C/'ENV_PREFLIGHT30_DOCKER_ADMISSION_POLICY_R5.json'
DOCKER_GATE_R5_SHA='e49628bfe9a49d9a2c845fceee53f388bc5d45272ab6136a076bf3f735287a6c'
DOCKER_POLICY_R5_SHA='a92eab38738cff4245138c6d86087973f0f8e04cddc0297ef5c4113f729b3d35'

def validate_old_prejob_proof(plan):
    if 'old_prejob_failure_proof_path' not in plan:return
    path=Path(plan['old_prejob_failure_proof_path']);assert sha(path)==plan['old_prejob_failure_proof_sha256'];proof=read(path)
    assert proof['assertions_passed'] and proof['new_model_attempts']==0 and proof['actual_native_job_uuid'] is None
    assert proof['old_job_directory_exists'] is False and not Path(proof['old_job_directory']).exists()
    for field in ['old_admission_identity','old_log_identity']:
        item=proof[field];assert sha(Path(item['path']))==item['sha256']
    old_base=Path(proof['old_admission_identity']['path']).parent
    assert all(absent and not(old_base/name).exists() for name,absent in proof['old_actual_files_absent'].items())

def cached_matrix():
    reader=E/'scripts/read-diagnostic150-matrix18-r5.py'
    process=subprocess.run([str(R/'env/harbor-native-eval-r1/bin/python'),str(reader),'--cached-only'],
        check=True,capture_output=True,text=True,timeout=15)
    value=json.loads(process.stdout)
    assert value['source_sha256']==sha(reader) and value['read_only'] and value['derived_files_written']==0
    assert value['expected']==150 and value['logical_terminal']+len(value['pending'])==150
    assert value['synthetic32_excluded'] and value['formal801_excluded']
    return value

def reader_writers(reader):
    """Observe the real default-reader process, including the earlier manual CPU unit."""
    expected_sources={reader.name:sha(reader),'read-diagnostic150-matrix18-r3.py':'e016a51783eb1afa57be21ebd807f29b045d0c1733458be8001d271f747f82d7','read-diagnostic150-matrix18-r4.py':'151e921ca03442be4a77d4cf1ed93bda1beb5d10b1dcd2f3b3ed888453c0c38b'}
    found=[];proc=Path('/proc');boot=int(next(line.split()[1] for line in (proc/'stat').read_text().splitlines() if line.startswith('btime ')))
    for path in proc.iterdir():
        if not path.name.isdigit():continue
        try:
            if path.stat().st_uid!=os.getuid():continue
            argv=[x.decode(errors='replace') for x in (path/'cmdline').read_bytes().split(b'\0') if x]
            scripts=[Path(x) for x in argv if Path(x).name in expected_sources]
            if not scripts or '--cached-only' in argv:continue
            assert len(scripts)==1
            script=scripts[0];stat=(path/'stat').read_text().rsplit(')',1)[1].split()
            started=boot+int(stat[19])/os.sysconf('SC_CLK_TCK')
            source_sha=sha(script) if script.is_absolute() and script.exists() else None
            verified=(script.is_absolute() and script.resolve().parent in [R.resolve(),(E/'scripts').resolve()]
                and source_sha==expected_sources[script.name] and script.stat().st_mtime<=started
                and argv[0]==str(R/'env/harbor-native-eval-r1/bin/python'))
            found.append(dict(pid=int(path.name),start_ticks=stat[19],argv=argv,source_sha256=source_sha,verified=verified))
        except (FileNotFoundError,ProcessLookupError):continue
        except Exception as error:found.append(dict(pid=int(path.name),verified=False,error=repr(error)))
    return found

def active_audit_units():
    process=subprocess.run(['systemctl','--user','list-units','--all','--plain','--no-legend','--no-pager',
        'qwen35-common150-recorder-audit-*.service'],check=True,capture_output=True,text=True,timeout=5)
    units=[]
    for line in process.stdout.splitlines():
        unit=line.split()[0];actual=props(unit)
        if actual['ActiveState'] in ['active','activating','deactivating']:units.append(dict(unit_name=unit,properties=actual))
    return units

def ensure_cpu_audit(owner,snapshot,launch_cpu):
    """Request one CPU-only audit through the existing controller's launch function."""
    reader=E/'scripts/read-diagnostic150-matrix18-r5.py';writers=reader_writers(reader)
    if writers:
        status='CPU_AUDIT_RUNNING_OBSERVED' if len(writers)==1 and writers[0]['verified'] else 'UNKNOWN_OR_MULTIPLE_AUDIT_WRITERS'
        return dict(status=status,writers=writers,new_unit_requested=False)
    try:registered=active_audit_units()
    except Exception as error:return dict(status='UNKNOWN_AUDIT_UNIT_INVENTORY',writers=[],new_unit_requested=False,error=repr(error))
    if registered:
        return dict(status='CPU_AUDIT_UNIT_REGISTERED_WITHOUT_VERIFIED_PROCESS',writers=[],new_unit_requested=False,registered_units=registered)
    pending=[x for x in snapshot['pending'] if x['status']=='RECORDER_AUDIT_PENDING']
    if not pending:
        return dict(status='AUDIT_CACHE_COMPLETE' if snapshot['complete'] else 'NO_PENDING_RECORDER_AUDIT',writers=[],new_unit_requested=False)
    # A new digest is a later set of newly completed Results, never a transient-unit GC retry.
    key=dict(reader_sha256=sha(reader),audit_sources=snapshot['audit_sources'],
        results=sorted((x['tag'],x['task_id'],x['result_sha256']) for x in pending))
    digest=hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest()
    unit='qwen35-common150-recorder-audit-'+digest[:12]+'.service'
    admission=E/'checks'/('COMMON150_CPU_AUDIT_'+digest+'_ADMISSION.json');actual=props(unit)
    if admission.exists():
        proof=read(admission);assert proof['source_sha256']==sha(reader) and proof['audit_snapshot_sha256']==digest
        return dict(status='CPU_AUDIT_REGISTERED_NO_VERIFIED_PROCESS',writers=[],new_unit_requested=False,
            unit=actual,admission_path=str(admission),admission_sha256=sha(admission),
            no_redispatch_from_unit_gc=True,reason='Check recorded unit exit/logs; no live reader process was observed')
    if actual['LoadState']!='not-found':
        return dict(status='CPU_AUDIT_UNIT_PRESENT_WITHOUT_VERIFIED_WRITER',writers=[],new_unit_requested=False,unit=actual)
    # launch_cpu is the unique controller's existing admission/systemd function.
    result=launch_cpu(unit,str(reader.relative_to(R)),[],admission,owner,
        dict(kind='CPU_ONLY_COMMON150_RECORDER_AUDIT',audit_snapshot_sha256=digest,
            expected_unaudited_native_results=len(pending),native_model_or_verifier_dispatches=0))
    observed=reader_writers(reader)
    status='CPU_AUDIT_REQUESTED_NOT_YET_OBSERVED' if not observed else 'CPU_AUDIT_RUNNING_OBSERVED' if len(observed)==1 and observed[0]['verified'] else 'UNKNOWN_OR_MULTIPLE_AUDIT_WRITERS'
    return dict(status=status,
        writers=observed,new_unit_requested=True,unit_name=unit,registered=result,
        admission_path=str(admission),admission_sha256=sha(admission) if admission.exists() else None)

def completion_gate(cfg):
    """Native Results and inactive workers, never GPU-utilization as a lease proxy."""
    pending=[];proofs=[]
    for model in cfg['models']:
        tag=model['tag'];path=B/('CONTINUATION_ACTUAL_TRIALS_'+tag+'_R4.json')
        if not path.exists():pending.append(dict(tag=tag,reason='ACTUAL_NATIVE_MAPPING_MISSING'));continue
        actual=read(path);trials=actual['trials'];missing=[x['trial_name'] for x in trials if not(Path(x['trials_dir'])/x['trial_name']/'result.json').exists()]
        unit='qwen35-accepted30-'+tag+'-20261102-r4.service';unit_state=props(unit)
        if missing or unit_state['ActiveState'] in ['active','activating','deactivating']:
            pending.append(dict(tag=tag,reason='ACCEPTED_NATIVE_TRIALS_OR_WORKER_IN_FLIGHT',missing=missing,unit=unit_state))
        proofs.append(dict(tag=tag,actual_mapping_sha256=sha(path),native_job_id=actual['native_job_id'],results=len(trials)-len(missing),expected=len(trials),unit=unit_state))
    actual_path=S/'eval-ACTUAL_NATIVE_TRIALS_R5.json';done=S/'eval-NATIVE_ALL_TERMINAL_R5.json'
    if not actual_path.exists() or not done.exists():pending.append(dict(tag='synthetic32',reason='PRIORITY32_NATIVE_COMPLETION_PENDING'))
    else:
        actual=read(actual_path);terminal=read(done);trials=actual['trials']
        assert len(trials)==32 and len({Path(x['task']['path']).name for x in trials})==32
        assert terminal['terminal']==32 and terminal['native_job_id']==actual['native_job_id']
        missing=[x['trial_name'] for x in trials if not(Path(x['trials_dir'])/x['trial_name']/'result.json').exists()]
        unit=props('qwen35-user-synthetic32-eval-m1e3-n1-20261102-r5.service')
        if missing or unit['ActiveState'] in ['active','activating','deactivating']:
            pending.append(dict(tag='synthetic32',reason='PRIORITY32_NATIVE_TRIALS_OR_WORKER_IN_FLIGHT',missing=missing,unit=unit))
        proofs.append(dict(tag='synthetic32',actual_mapping_sha256=sha(actual_path),terminal_marker_sha256=sha(done),results=32-len(missing),unit=unit))
    # Original NoSpace Results cannot satisfy either newly registered model-specific scope.
    for tag,(expected,plan_sha,version) in DISK_RECOVERY_SCOPES.items():
        base=R/('disk-failure-recovery-r'+str(version))/tag;plan_path=base/('PLAN_R'+str(version)+'.json');admission=base/('ADMISSION_R'+str(version)+'.json')
        actual_path=base/('ACTUAL_NATIVE_TRIALS_R'+str(version)+'.json');done=base/('ALL_TERMINAL_R'+str(version)+'.json')
        if not all(p.exists() for p in [plan_path,admission,actual_path,done]):
            pending.append(dict(tag=tag+'-disk-recovery',reason='EXPLICIT_DISK_RECOVERY_NOT_TERMINAL',expected=expected,
                missing_paths=[str(p) for p in [plan_path,admission,actual_path,done] if not p.exists()]))
            continue
        assert sha(plan_path)==plan_sha;plan=read(plan_path);validate_old_prejob_proof(plan);admitted=read(admission);actual=read(actual_path);terminal=read(done)
        assert admitted['plan_sha256']==actual['plan_sha256']==terminal['plan_sha256']==sha(plan_path)
        assert actual['native_job_id']==terminal['native_job_id'] and actual['expected']==terminal['expected']==terminal['terminal']==expected
        assert actual['tag']==tag and actual['job_name']==terminal['job_name']==plan['recovery_job_name']
        assert len(actual['trials'])==expected and {Path(x['task']['path']).name for x in actual['trials']}=={x['task_id'] for x in plan['trials']}
        paths=[Path(x['trials_dir'])/x['trial_name']/'result.json' for x in actual['trials']]
        recorded={x['path']:x['sha256'] for x in terminal['results']};assert set(recorded)==set(map(str,paths))
        missing=[str(p) for p in paths if not p.exists()]
        if not missing:assert all(sha(p)==recorded[str(p)] for p in paths)
        unit=props(plan['recovery_job_name']+'.service')
        if missing or unit['ActiveState'] in ['active','activating','deactivating']:
            pending.append(dict(tag=tag+'-disk-recovery',reason='RECOVERY_NATIVE_TRIALS_OR_WORKER_IN_FLIGHT',missing=missing,unit=unit))
        proofs.append(dict(tag=tag+'-disk-recovery',expected=expected,results=expected-len(missing),
            actual_mapping_sha256=sha(actual_path),terminal_marker_sha256=sha(done),unit=unit))
    return dict(ready=not pending,pending=pending,proofs=proofs,synthetic32_excluded_from_model_selection=True)

def current_roles(cfg):
    roles={}
    for model in cfg['models']:
        replicas=model.get('replicas') or [dict(gpu_index=model['gpu_index'],gpu_uuid=model['gpu_uuid'],port=model['port'],unit=model['serving_unit'])]
        for replica in replicas:
            assert replica['gpu_index'] not in roles
            roles[replica['gpu_index']]=dict(model=model,replica=replica)
    # GPU0/5 were explicitly cold-reassigned to priority32; original config is historical.
    proof_path=S/'priority-gpu-replicas-r1/COLD_REPLICAS_LAUNCHED.json';proof=read(proof_path)
    target=next(m for m in cfg['models'] if m['tag']=='new-m1-e3-diag')
    assert {x['gpu_index'] for x in proof['replicas']}=={0,5}
    for item in proof['replicas']:
        replica=item['new_replica'];assert replica['weight_version']==target['weight_version'] and replica['model_path']==target['model_path']
        roles[item['gpu_index']]=dict(model=target,replica=replica,priority_handoff_sha256=sha(proof_path))
    assert set(roles)==set(range(8)) and len({x['replica']['port'] for x in roles.values()})==8
    return roles

def release_idle_owned_services(cfg,selection):
    target=R/'checks/DIAG150_AND_SYNTH32_SERVICES_RELEASED_R2.json'
    if target.exists():return read(target)
    gate=completion_gate(cfg);assert gate['ready'],'Preserve all healthy accepted/synthetic Trials'
    leases=handoff.leases();assert leases['complete'] and not leases['active_cli_leases'],'Active or unknown CLI lease: preserve services'
    roles=current_roles(cfg);directory=R/'checks/selected267-cold-release-r2';directory.mkdir(exist_ok=True)
    rows=[];authorized=read(R/'new-sft/workspace/configs/runtime.json')['authorized_gpu_uuids']
    for index,role in sorted(roles.items()):
        replica=role['replica'];model=role['model'];unit=replica['unit'];marker=directory/('gpu'+str(index)+'-released.json')
        if marker.exists():
            row=read(marker);assert row['unit']==unit and row['gpu_uuid']==replica['gpu_uuid']
            assert props(unit)['ActiveState'] not in ['active','activating','deactivating'];rows.append(row);continue
        state=props(unit);assert state['ActiveState']=='active';pid=int(state['MainPID']);stat=Path('/proc')/str(pid)/'stat';ticks=stat.read_text().rsplit(')',1)[1].split()[19]
        uuid=subprocess.check_output(['nvidia-smi','-i',str(index),'--query-gpu=uuid','--format=csv,noheader'],text=True).strip()
        pids=[int(x) for x in subprocess.check_output(['nvidia-smi','-i',str(index),'--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).split()]
        assert uuid==replica['gpu_uuid'] and uuid in authorized and pids and all(pid in handoff.ancestors(x) for x in pids),'Other GPU owner: preserve service'
        info=handoff.get(replica['port'],'/model_info');assert info['model_path']==model['model_path'] and info['weight_version']==model['weight_version']
        load=handoff.get(replica['port'],'/get_load');assert load and all(x['num_reqs']==0 and x['num_waiting_reqs']==0 for x in load)
        observed=handoff.leases();assert observed['complete'] and not observed['active_cli_leases']
        assert completion_gate(cfg)['ready'] and props(unit)['MainPID']==str(pid) and stat.read_text().rsplit(')',1)[1].split()[19]==ticks
        row=dict(at=time.time(),gpu_index=index,gpu_uuid=uuid,unit=unit,main_pid=pid,start_ticks=ticks,actual_gpu_pids=pids,
            model_info=info,load=load,cli_lease_proof=observed,selection_sha256=sha(selection),native_completion_gate=gate)
        save(directory/('gpu'+str(index)+'-before.json'),row)
        subprocess.run(['systemctl','--user','stop',unit],check=True,timeout=60)
        row['graceful_owned_idle_service_stop_completed_at']=time.time();save(marker,row);rows.append(row)
    value=dict(at=time.time(),services=rows,all150_logical_terminal=True,synthetic32_native_terminal=32,
        all_cli_leases_closed=True,no_healthy_trial_interrupted=True,selection_sha256=sha(selection))
    save(target,value);return value

def prepare_cache_binding(full,live):
    source=B/'PUBLIC_VERIFIER_CACHE_BINDING_R1.json';binding=read(source)
    original_spec=Path(binding['runtime_spec_path']);assert sha(original_spec)==binding['runtime_spec_sha256']
    directory=R/'checks/selected267-public-cache-r2';directory.mkdir(exist_ok=True)
    spec=read(original_spec);spec['model_endpoints']=[dict(url='http://172.17.0.1:'+str(x['port'])+'/model_info',model_path=full['model_path'],weight_version=full['weight_version']) for x in full['replicas']]
    spec_path=directory/'torch-tensor-parallelism.json'
    if spec_path.exists():assert read(spec_path)==spec
    else:save(spec_path,spec)
    role_path=directory/'COLD_SERVING_ROLES.json';role=dict(model_id=full['model_id'],weight_version=full['weight_version'],replicas=live)
    if role_path.exists():assert read(role_path)==role
    else:save(role_path,role)
    observed=subprocess.run(['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1',shlex.join(['sha256sum',MATERIALIZER_R2_REMOTE])],check=True,capture_output=True,text=True,timeout=20)
    assert observed.stdout.split()[0]==MATERIALIZER_R2_SHA,'Selected267 R2 materializer not installed with frozen SHA'
    updated=dict(binding,remote_materializer_path=MATERIALIZER_R2_REMOTE,materializer_sha256=MATERIALIZER_R2_SHA,
        runtime_spec_path=str(spec_path),runtime_spec_sha256=sha(spec_path),
        parent_cache_binding_sha256=sha(source),selected267_serving_roles_sha256=sha(role_path))
    path=directory/'PUBLIC_VERIFIER_CACHE_BINDING.json'
    if path.exists():assert read(path)==updated
    else:save(path,updated)
    return path,updated,role_path

def launch(full,owner):
    admission=E/'manifests/SELECTED267_ADMISSION_R1.json';dispatch=E/'manifests/SELECTED267_DISPATCH_R2.json';state=props(full['job_unit'])
    if admission.exists() or dispatch.exists():return dict(status='NATIVE_JOB_ALREADY_REGISTERED_NEVER_REDISPATCHED',unit=state)
    live=phase.ready(full)
    if live is None:return dict(status='SELECTED267_COLD_SERVERS_STARTING')
    assert state['LoadState']=='not-found' and not(E/'jobs'/full['job_name']).exists()
    source=E/'scripts/run-user-evaluation-native18-r5.py';cache_path,binding,roles=prepare_cache_binding(full,live)
    assert sha(DOCKER_GATE_R5)==DOCKER_GATE_R5_SHA and sha(DOCKER_POLICY_R5)==DOCKER_POLICY_R5_SHA
    value=dict(at=time.time(),unique_controller_owner=owner,model=full,replicas=live,source_sha256=sha(source),
        docker_wrapper_path=str(DOCKER_GATE_R5),docker_wrapper_sha256=DOCKER_GATE_R5_SHA,
        docker_policy_path=str(DOCKER_POLICY_R5),docker_policy_sha256=DOCKER_POLICY_R5_SHA,
        storage_probe_worker_sha256='a554a4c6c95f0411c11e393c81548a493a1f42f9f24ad6a7a700952c1ca36649',
        storage_probe_code_sha256='df9643fa3167d751be597f71e9860c37974230b20da29767110704cfb41ad9f9',
        pre_model_continuation=False,public_verifier_cache_binding_path=str(cache_path),public_verifier_cache_binding=binding,
        public_verifier_cache_binding_sha256=sha(cache_path),selected_serving_roles_sha256=sha(roles),
        environment_profiles_sha256=sha(B/'environment-profiles-recheck-r2.json'))
    save(admission,value);save(dispatch,dict(at=time.time(),unit=full['job_unit'],admission_sha256=sha(admission),registered_once_before_dispatch=True))
    log=R/'logs/native-SELECTED267.log'
    subprocess.run(['systemd-run','--user','--unit='+full['job_unit'],'--property=MemoryMax=32G',
        '--property=StandardOutput=append:'+str(log),'--property=StandardError=append:'+str(log),
        '--setenv=PYTHONPATH='+str(R)+':'+str(E/'scripts'),str(R/'env/harbor-native-eval-r1/bin/python'),str(source),'selected267'],check=True,capture_output=True,text=True,timeout=15)
    return dict(status='NATIVE_JOB_STARTED',unit=props(full['job_unit']))

def advance(owner,state,launch_cpu):
    assert read(C/'NATIVE_ADVANCE_OWNER.json')==owner
    cfg=read(R/'configs/diagnostic150-five-model-r1.json');selection=R/'checks/WINNER_FROM_COMMON30_SELECTION_R1.json'
    snapshot=cached_matrix();audit_state=ensure_cpu_audit(owner,snapshot,launch_cpu)
    state['common150_cpu_audit']=audit_state
    gate=completion_gate(cfg);state['selected267_completion_gate']=gate
    if not gate['ready']:
        state['selected267']=dict(status='WAIT_COMMON150_AND_PRIORITY32_NATIVE_TERMINAL',pending=gate['pending']);return
    if not selection.exists():
        if audit_state['writers'] or audit_state['status'] not in ['NO_PENDING_RECORDER_AUDIT','AUDIT_CACHE_COMPLETE']:
            state['selected267']=dict(status='WAIT_COMMON150_RECORDER_AUDIT',audit_status=audit_state['status']);return
        reader=E/'scripts/read-diagnostic150-matrix18-r5.py'
        path=E/'checks/DIAGNOSTIC150_WINNER_GATE_SNAPSHOT_R3.json';matrix=snapshot
        if not matrix['complete'] or matrix['logical_terminal']!=150:
            state['selected267']=dict(status='WAIT_ALL150_LOGICAL_TERMINAL',pending=matrix['pending']);return
        assert not audit_state['writers'],'Do not freeze selection while the audit cache is being written'
        matrix=dict(matrix,audit_cache_rows_sha256=sha(E/'checks/DIAGNOSTIC150_MATRIX_ROWS_R5.jsonl'))
        if path.exists():assert read(path)['audit_cache_rows_sha256']==matrix['audit_cache_rows_sha256']
        else:save(path,matrix)
        assert matrix['synthetic32_excluded'] and matrix['formal801_excluded']
        order=cfg['selection']['tie_order'];winner=min(order,key=lambda tag:(-matrix['models'][tag]['confirmed_reward_successes'],order.index(tag)))
        model=next(x for x in cfg['models'] if x['tag']==winner)
        save(selection,dict(at=time.time(),winner=winner,model=model,common30_matrix_sha256=sha(path),
            common30_matrix_reader_sha256=sha(reader),common30_matrix_version='R5',candidates=matrix['models'],criterion=cfg['selection'],
            largest_confirmed_correct_count=matrix['models'][winner]['confirmed_reward_successes'],unknowns_not_reward_zero=True,
            selection_may_be_uncertain_with_unknowns=True,selected_on_subset_of_full89=True,not_unselected_holdout=True,
            synthetic32_excluded_from_selection=True,user_scope_override_sha256=sha(C/'USER_EVALUATION_SCOPE_OVERRIDE_R1.json')))
    chosen=read(selection);assert chosen['common30_matrix_version']=='R5';model=chosen['model']
    release_idle_owned_services(cfg,selection)
    binding=R/'checks/SELECTED267_MODEL_BINDING_R1.json'
    if not binding.exists():
        runtime=read(R/'new-sft/workspace/configs/runtime.json');ports=[18300,18301,18302,18308,18303,18309,18306,18307]
        full=dict(model,tag='selected267',model_id='qwen35-new772-selected30-winner',source_agent_index=2,
            display_name='Qwen3.5-4B selected by common30',new_trials=267,concurrency=16,
            job_name='qwen35-user-selected30-winner-tb21-n3-267-20261102-r1',job_unit='qwen35-user-selected267-native18-20261102-r1.service',
            replicas=[dict(gpu_index=i,gpu_uuid=runtime['authorized_gpu_uuids'][i],port=ports[i],unit='qwen35-user-selected267-gpu'+str(i)+'-20261102-r1.service') for i in range(8)])
        source=read(E/'manifests/FORMAL_801_TRIAL_PLAN.json');trials=[]
        for row in source['trials']:
            if row['model_name']=='openai/qwen35-new772-m0':
                trials.append(dict(row,tag='selected267',model_name='openai/'+full['model_id'],trial_name=row['task_id']+'__selected30-winner-n3-r'+str(row['repetition']),reuse_existing_trial=False))
        assert len(trials)==267 and len({x['trial_name'] for x in trials})==267 and len({x['task_id'] for x in trials})==89
        save(E/'manifests/SELECTED267_BOUND_TRIAL_PLAN_R1.json',dict(expected=267,trials=trials,
            sampling_manifest_sha256=cfg['sampling_manifest_sha256'],selection_sha256=sha(selection),selected_model_manifest_sha256=model['weight_version'],no_old801_trials_reused=True))
        save(binding,full)
    done=E/'checks/SELECTED267_COMPARISON_R1.json'
    if done.exists():
        result=read(done);assert result['complete'] and result['terminal']==267
        state['selected267_result_sha256']=sha(done)
        importlib.import_module('old-four-complete-readouts-phase18-r1').advance(owner,state);return
    full=read(binding)
    for replica in full['replicas']:phase.start_replica(full,replica)
    state['selected267']=launch(full,owner);state['status']='SELECTED_MODEL_FULL89_N3_RUNNING_OR_COLD_STARTING'
    path=E/'checks/SELECTED267_STATUS_R1.json'
    if path.exists():state['selected267']['progress']=read(path)

if __name__=='__main__':raise SystemExit('Only the existing unique controller may call advance')
