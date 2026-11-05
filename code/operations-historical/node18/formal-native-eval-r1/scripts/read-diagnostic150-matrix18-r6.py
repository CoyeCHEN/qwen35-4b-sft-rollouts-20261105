"""Read the fixed logical150 via registered native Trial identities; never dispatch."""
import hashlib
import importlib
import json
from pathlib import Path
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1';B=R/'environment-preflight30'
prep=importlib.import_module('evaluation-preparation18-r1')
legacy=importlib.import_module('compare-epoch3-epoch5-readonly149-r6')
audit=importlib.import_module('audit-native-response-qualification-r1')
metric=importlib.import_module('compare-formal801-readonly-r8')
behavior=importlib.import_module('audit_trial_behavior_new772_r3')
host_transport=importlib.import_module('audit-native-host-docker-transport-r1')
DISK_RECOVERY_SCOPES={
 'new-m1-e3-diag':(15,'a1400c81324a6a2018c517c925c3bd7f201c9d7e57380a52718d88472e461b8a',3),
 'new-m2-e1-diag':(25,'a29c6e0d1cd0911ee18e97006e7b3f29b08f1c40144d39ff52134345e4104e3b',2),
 'new-m1-e5-diag':(23,'4c2cffd705bc2e4d3bfd8bcf96ad6403faf50bf8bf2f44918271d06fa3fb3806',3)}
DETACHED_SHA='9bce290779fedd585977a439eec00ddd43dd8148c6764593136ad09d1faf629b'

def validate_old_prejob_proof(plan):
    if 'old_prejob_failure_proof_path' not in plan:return
    path=Path(plan['old_prejob_failure_proof_path']);assert sha(path)==plan['old_prejob_failure_proof_sha256'];proof=read(path)
    assert proof['assertions_passed'] and proof['new_model_attempts']==0 and proof['actual_native_job_uuid'] is None
    assert proof['old_job_directory_exists'] is False and not Path(proof['old_job_directory']).exists()
    for field in ['old_admission_identity','old_log_identity']:
        item=proof[field];assert sha(Path(item['path']))==item['sha256']
    old_base=Path(proof['old_admission_identity']['path']).parent
    assert all(absent and not(old_base/name).exists() for name,absent in proof['old_actual_files_absent'].items())

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):
    tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(p)
def identity(item):return item['tag'],item['task_id'],item['repetition']
def source_identities():
    modules=[prep,legacy,audit,audit.base,importlib.import_module('eval_audit_new772'),metric,behavior,host_transport]
    return {module.__name__:sha(Path(module.__file__)) for module in modules}

def accepted_mapping(models):
    """Admission selects the Task before a Result exists; native order is irrelevant."""
    mapped={};proofs={}
    for tag,model in models.items():
        registration=B/('ACCEPTED_CONTINUATION_'+tag+'_R4.json')
        if not registration.exists():continue
        registered=read(registration)
        assert registered['tag']==tag and registered['model']['model_id']==model['model_id']
        declared={identity(x):x for x in registered['trials']}
        assert len(declared)==len(registered['trials']) and registered['zero_started_model_attempts_retried']
        actual_path=B/('CONTINUATION_ACTUAL_TRIALS_'+tag+'_R4.json')
        actuals=read(actual_path) if actual_path.exists() else None
        if actuals is None:
            for key in declared:mapped[key]=dict(directory=None,status='REGISTERED_NATIVE_JOB_NOT_CREATED',registration=str(registration))
        else:
            assert actuals['registration_sha256']==sha(registration)
            actual_by_task={Path(x['task']['path']).name:x for x in actuals['trials']}
            assert len(actual_by_task)==len(actuals['trials'])==len(declared)
            assert set(actual_by_task)=={key[1] for key in declared}
            for key in declared:
                cfg=actual_by_task[key[1]]
                assert cfg['agent']['kwargs']['config']['model']['id']==model['model_id']
                directory=Path(cfg['trials_dir'])/cfg['trial_name']
                assert directory.parent.parent==E/'jobs' and directory.name.startswith(key[1]+'__accepted30-')
                mapped[key]=dict(directory=directory,status='ACCEPTED_NATIVE_CONTINUATION',registration=str(registration),
                    registration_sha256=sha(registration),actual_mapping_sha256=sha(actual_path),native_job_id=actuals['native_job_id'])
        proofs[tag]=dict(registration_sha256=sha(registration),actual_mapping_sha256=sha(actual_path) if actuals else None,
            expected=len(declared))
    return mapped,proofs

def disk_recovery_mapping(models,accepted):
    """Only the two exact, model-specific zero-model disk recovery scopes redirect."""
    mapped={};proofs={}
    for tag,(expected,plan_sha,version) in DISK_RECOVERY_SCOPES.items():
        base=R/('disk-failure-recovery-r'+str(version))/tag;plan_path=base/('PLAN_R'+str(version)+'.json');admission_path=base/('ADMISSION_R'+str(version)+'.json')
        if not plan_path.exists():
            assert not admission_path.exists(),'Recovery admission exists without its frozen plan'
            continue
        assert sha(plan_path)==plan_sha;plan=read(plan_path);validate_old_prejob_proof(plan)
        assert plan['previous_actual_model_attempts']==0 and plan['maximum_new_model_attempts']==expected
        assert plan['recovery_attempts_per_task']==1 and plan['harbor_max_retries']==0 and len(plan['trials'])==expected
        registration=Path(plan['original_registration_path']);assert sha(registration)==plan['original_registration_sha256']
        original=read(registration);model=models[tag]
        assert original['tag']==tag and original['model']['model_id']==model['model_id']
        by_task={x['task_id']:x for x in plan['trials']};assert len(by_task)==expected
        assert not set(by_task).intersection(x['task_id'] for x in plan['excluded_real_attempts'])
        if tag=='new-m1-e3-diag':assert 'circuit-fibsqrt' not in by_task
        current={}
        for task,item in by_task.items():
            key=tag,task,1;assert key in accepted
            result=Path(item['result_identity']['path']);config=Path(item['config_identity']['path'])
            assert sha(result)==item['result_identity']['sha256'] and sha(config)==item['config_identity']['sha256']
            old=read(result);exception=old.get('exception_info')or{}
            assert old['id']==item['native_trial_uuid'] and old.get('agent_execution') is None and old.get('agent_result') is None
            assert exception['exception_type']=='RemoteDockerError' and 'No space left on device' in exception['exception_message']
            assert not list(result.parent.glob('ACTUAL_AGENT_START*.json'))
            assert old['config']['agent']['kwargs']['config']['model']['id']==model['model_id']
            assert accepted[key]['directory'].resolve()==result.parent.resolve()
            current[key]=dict(directory=None,status='DISK_RECOVERY_PLAN_REGISTERED_AWAIT_ADMISSION',registration=str(plan_path),
                original_identity=dict(trial_id=item['native_trial_uuid'],result_identity=item['result_identity'],config_identity=item['config_identity'],previous_actual_model_attempts=0))
        proof=dict(plan_path=str(plan_path),plan_sha256=sha(plan_path),expected=expected,original_failures=[x['original_identity'] for x in current.values()],actual_model_attempts_retried=0)
        if admission_path.exists():
            admission=read(admission_path)
            assert Path(admission['plan_path'])==plan_path and admission['plan_sha256']==sha(plan_path)
            assert admission['source_sha256']==sha(R/('run-accepted-common30-disk-recovery18-r'+str(version)+'.py'))
            assert admission['disk_repair_verified'] and Path(admission['output_directory'])==base
            assert sha(Path(admission['disk_repair_proof_path']))==admission['disk_repair_proof_sha256']
            proof.update(admission_path=str(admission_path),admission_sha256=sha(admission_path))
            actual_path=base/('ACTUAL_NATIVE_TRIALS_R'+str(version)+'.json')
            for value in current.values():value.update(status='DISK_RECOVERY_NATIVE_JOB_NOT_CREATED',registration=str(admission_path))
            if actual_path.exists():
                actual=read(actual_path)
                assert actual['tag']==tag and actual['expected']==expected and actual['plan_sha256']==sha(plan_path) and Path(actual['plan_path'])==plan_path
                assert actual['job_name']==plan['recovery_job_name']
                configs={Path(x['task']['path']).name:x for x in actual['trials']};previous={x['task_id']:x for x in actual['recovery_of_trials']}
                assert len(configs)==len(actual['trials'])==len(previous)==expected and set(configs)==set(previous)==set(by_task)
                for task,cfg in configs.items():
                    before=by_task[task];link=previous[task]
                    assert link['original_native_trial_uuid']==before['native_trial_uuid'] and link['original_result_identity']==before['result_identity'] and link['original_config_identity']==before['config_identity']
                    assert link['previous_actual_model_attempts']==0 and cfg['agent']['kwargs']['config']['model']['id']==model['model_id']
                    directory=Path(cfg['trials_dir'])/cfg['trial_name']
                    assert directory.parent==E/'jobs'/plan['recovery_job_name'] and directory.name==task+'__accepted30-disk-recovery-'+tag+'-r'+str(version)
                    current[(tag,task,1)].update(directory=directory,status='DISK_RECOVERY_NATIVE_TRIAL_PENDING',actual_mapping_sha256=sha(actual_path),native_job_id=actual['native_job_id'])
                proof.update(actual_mapping_path=str(actual_path),actual_mapping_sha256=sha(actual_path),native_job_id=actual['native_job_id'])
        mapped.update(current);proofs[tag]=proof
    return mapped,proofs

def unknown_row(task,directory,reason,**evidence):
    return dict(row_kind='DERIVED_TERMINAL_UNKNOWN_NO_ORIGINAL_NATIVE_RESULT',task_id=task,
        trial_name=directory.name,trial_path=str(directory),trial_id=None,native_result_exists=False,
        result_sha256=None,reward=None,raw_official_score_valid=False,valid_score=False,
        protocol_issues=[reason],trajectory_complete=False,normal_close=False,exception_type='ControllerDriverInterrupted',
        tool_argument_invalid=0,infrastructure_errors=['original_controller_driver_interruption'],failure_phase='controller',
        diagnostic_exclusion_reason=reason,no_native_trial_uuid_or_reward_invented=True,**evidence)

def unresolved_pre_model_disk_failure(directory):
    raw=read(directory/'result.json');exception=raw.get('exception_info')or{}
    if raw.get('failure_phase')!='environment_setup' or raw.get('agent_execution') is not None or raw.get('agent_result') is not None:return False
    if exception.get('exception_type')!='RemoteDockerError' or 'No space left on device' not in exception.get('exception_message',''):return False
    if list(directory.glob('ACTUAL_AGENT_START*.json')):return False
    markers=['recorder','trajectory','events.jsonl','session','payload','open-harness.stdout','open-harness.complete','effective-config.json']
    return not any(p.is_file() and p.stat().st_size and any(m in str(p.relative_to(directory)).lower() for m in markers)
        for folder in ['agent','agent-logs'] for p in (directory/folder).rglob('*'))

def detached_rows(models):
    """Independent recovered Verifier scores never replace missing native Results."""
    manifest=R/'checks/detached-three-agent/DETACHED_THREE_RECOVERY_TERMINALS_R2.json'
    if not manifest.exists():return {}
    assert sha(manifest)==DETACHED_SHA
    proof=read(manifest)
    assert proof['new_agent_runs']==proof['new_model_attempts']==proof['original_native_uuids_fabricated']==proof['original_native_results_rewritten']==0
    admission=R/'detached-native-recovery-r1/ADMISSION_R1.json';registered=read(admission)
    evidence_by_identity={x['original_identity']:x for x in proof['trials']};rows={}
    for item in registered['trials']:
        ev=evidence_by_identity[item['identity']]
        assert ev['task_id']==item['task_id'] and ev['original_cli_completion']['exit_code'] is not None
        assert ev['original_missing_result_remains_unknown'] and ev['original_trial_uuid'] is None
        assert ev['original_container_workspace_retained'] and ev['verifier_reward_is_not_a_reconstructed_original_result']
        directory=Path(item['original_trial_path']);source=Path(item['source_directory'])
        assert not(directory/'result.json').exists() and sha(source/'config.json')==item['config_sha256']
        cfg=read(source/'config.json');model_id=cfg['agent']['kwargs']['config']['model']['id']
        matches=[tag for tag,m in models.items() if m['model_id']==model_id];assert len(matches)==1
        key=matches[0],item['task_id'],1
        rows[key]=unknown_row(item['task_id'],directory,'UNKNOWN_CONTROLLER_DRIVER_CRASH_ORIGINAL_RESULT_MISSING',
            original_config_sha256=item['config_sha256'],original_remote_docker_identity=item['identity'],
            recovery_manifest_path=str(manifest),recovery_manifest_sha256=sha(manifest),
            original_cli_exit_code=ev['original_cli_completion']['exit_code'],
            independent_verifier_reward_auxiliary_only=ev['independent_official_verifier_reward'],
            recorder_complete_auxiliary_only=ev['native_recorder_complete'],
            original_result_missing=True,original_model_attempt_not_retried=True)
    assert len(rows)==3
    return rows

def load_cache(sources):
    cached={}
    def retain(path,manifest,origin):
        proof=read(manifest);assert proof['rows_sha256']==sha(path)
        for line in path.open():
            row=json.loads(line)
            value=row.get('trial_path') or (str(Path(row['result_path']).parent) if row.get('result_path') else None)
            if value and row.get('native_result_exists',True) and row.get('trial_id') is not None:
                row.update(reader_cache_origin=dict(kind=origin,rows_sha256=sha(path),audit_manifest_sha256=sha(manifest),
                    original_audit_dependency_sha_not_separately_recorded=origin!='RECORDED_MATCHING_QUALIFICATION_SOURCES'))
                cached[str(Path(value).resolve())]=row
    # The original per-job audits include Results written after the earlier matrix.
    for manifest in sorted((E/'checks').glob('DIAGNOSTIC30_AUDIT_COMPLETE_*.json')):
        tag=manifest.name.removeprefix('DIAGNOSTIC30_AUDIT_COMPLETE_').removesuffix('.json')
        path=E/'checks'/('DIAGNOSTIC30_ROWS_'+tag+'.jsonl')
        if path.exists():retain(path,manifest,'UNCHANGED_PRIOR_NATIVE_JOB_AUDIT')
    earlier=E/'checks/EPOCH3_VS_EPOCH5_COMPARISON_R6.json';earlier_rows=E/'checks/EPOCH3_VS_EPOCH5_ROWS_R6.jsonl'
    if earlier.exists() and earlier_rows.exists():
        recorded=read(earlier)['audit_sources']
        required=[audit,audit.base,importlib.import_module('eval_audit_new772'),behavior]
        if all(recorded.get(Path(m.__file__).name)==sha(Path(m.__file__)) for m in required):
            retain(earlier_rows,earlier,'RECORDED_MATCHING_QUALIFICATION_SOURCES')
    # R2 already audited the retained Results; verify its row and writer identities.
    # Preserve that provenance rather than claiming it newly reran every Recorder.
    old_path=E/'checks/DIAGNOSTIC150_MATRIX_ROWS_R2.jsonl';old_manifest=E/'checks/DIAGNOSTIC150_MATRIX_R2.json'
    writer=E/'scripts/read-diagnostic150-matrix18-r2.py'
    if old_path.exists() and old_manifest.exists():
        old=read(old_manifest)
        assert old['rows_sha256']==sha(old_path) and old['source_sha256']==sha(writer)
        for line in old_path.open():
            row=json.loads(line)
            if row.get('native_result_exists',True) and row.get('trial_id') is not None:
                row.update(reader_cache_origin=dict(kind='UNCHANGED_PRIOR_R2_AUDIT',rows_sha256=sha(old_path),
                    audit_manifest_sha256=sha(old_manifest),writer_source_sha256=sha(writer),
                    original_audit_dependency_sha_not_separately_recorded=True))
                cached[str(Path(row['trial_path']).resolve())]=row
    for version in ['R3','R4','R5','R6']:
        path=E/'checks'/('DIAGNOSTIC150_MATRIX_ROWS_'+version+'.jsonl')
        if path.exists():
            for line in path.open():
                row=json.loads(line)
                if (row.get('reader_audit_sources')==sources or row.get('reader_audit_sources')=={k:v for k,v in sources.items() if k!='audit-native-host-docker-transport-r1'}) and row.get('native_result_exists',True):
                    cached[str(Path(row['trial_path']).resolve())]=row
    return cached

def inspect(directory,item,wheel,cached,sources,allow_fresh_audit=True):
    result=directory/'result.json';cfg=read(directory/'config.json')
    assert cfg['agent']['kwargs']['wheel_sha256']==wheel
    assert cfg['agent']['kwargs']['config']['model']['id']==item['model_name'].removeprefix('openai/')
    old=cached.get(str(directory.resolve()))
    if old and old['result_sha256']==sha(result):
        assert old['task_id']==item['task_id']
        return dict(host_transport.qualify_cached_row(old,result),reader_audit_sources=sources)
    if not allow_fresh_audit:return None
    try:
        row=audit.inspect_trial(directory)
        try:row['behavior']=behavior.analyze_behavior(directory)
        except Exception as error:row['behavior_audit_error']=repr(error)
    except Exception as error:
        # A single failed audit is explicit UNKNOWN; other completed Trials survive.
        raw=read(result)
        row=unknown_row(item['task_id'],directory,'UNKNOWN_RESULT_AUDIT_FAILED',audit_error=repr(error))
        row.update(native_result_exists=True,result_sha256=sha(result),trial_id=raw['id'],
            reward=(raw.get('verifier_result')or{}).get('rewards'))
    assert row['task_id']==item['task_id']
    row=host_transport.qualify_cached_row(row,result)
    row.update(reader_audit_sources=sources,trial_path=str(directory),repetition=item['repetition'])
    cached[str(directory.resolve())]=dict(row)
    return row

def collect(on_row=None,allow_fresh_audit=True):
    config=read(R/'configs/diagnostic150-five-model-r1.json');models={x['tag']:x for x in config['models']}
    plan_path=E/'manifests/DIAGNOSTIC150_TRIAL_PLAN_R1.json';plan=read(plan_path)
    sampling=E/'manifests/DIAGNOSTIC30_SAMPLING_MANIFEST_R1.json'
    assert len(plan['trials'])==150 and len({identity(x) for x in plan['trials']})==150
    assert sha(sampling)==plan['sampling_manifest_sha256']==config['sampling_manifest_sha256']
    sources=source_identities();cached=load_cache(sources);accepted,registrations=accepted_mapping(models);disks,disk_proof=disk_recovery_mapping(models,accepted);detached=detached_rows(models)
    assert set(accepted)<=set(map(identity,plan['trials'])) and not(set(accepted)&set(detached))
    rows=[];first_pass=[];first_pass_audit_pending=[];pending=[];native_ids=set()
    for item in plan['trials']:
        key=identity(item);original=prep.resolve_original(item,models);directory=original;recovery=None
        if (original/'result.json').exists():
            first=inspect(original,item,config['wheel_sha256'],cached,sources,allow_fresh_audit)
            if first is None:first_pass_audit_pending.append(dict(tag=item['tag'],task_id=item['task_id'],trial_path=str(original)))
            else:first_pass.append(dict(first,diagnostic30_tag=item['tag']))
        source=disks.get(key) or accepted.get(key)
        if source:
            directory=source['directory']
            if directory is None:
                pending.append(dict(tag=item['tag'],task_id=item['task_id'],status=source['status']));continue
        else:
            rp=E/'manifests'/('PRE_MODEL_ENV_RECOVERY_PLAN_'+item['tag']+'_R1.json')
            if rp.exists():
                registered=read(rp);recovery=next((x for x in registered['trials'] if x['task_id']==item['task_id']),None)
                if recovery:
                    assert prep.pre_model_failure(original)['result_sha256']==recovery['result_sha256']
                    directory=E/'jobs'/registered['model']['job_name']/recovery['trial_name']
        if (directory/'result.json').exists():
            if unresolved_pre_model_disk_failure(directory):
                pending.append(dict(tag=item['tag'],task_id=item['task_id'],trial_path=str(directory),
                    status='RECOVERY_ENVIRONMENT_DISK_FAILURE_REQUIRES_REVIEW' if key in disks else 'UNREGISTERED_ZERO_MODEL_DISK_RECOVERY_REQUIRED',native_result_exists=True,
                    result_sha256=sha(directory/'result.json'),not_authorization_to_retry=True));continue
            row=inspect(directory,item,config['wheel_sha256'],cached,sources,allow_fresh_audit)
            if row is None:
                pending.append(dict(tag=item['tag'],task_id=item['task_id'],trial_path=str(directory),status='RECORDER_AUDIT_PENDING',
                    native_result_exists=True,result_sha256=sha(directory/'result.json')));continue
        elif key in detached:
            assert source is None and recovery is None;row=dict(detached[key]);directory=Path(row['trial_path'])
        else:
            row=legacy.interrupted_terminal('new-m1',item['task_id'],directory) if item['reuse_existing_trial'] and not source else None
            if row is None:
                pending.append(dict(tag=item['tag'],task_id=item['task_id'],trial_path=str(directory),
                    status=source['status'] if source else 'PRE_MODEL_ENV_CONTINUATION_PENDING' if recovery else 'ORIGINAL_NATIVE_RESULT_PENDING',
                    actual_agent_started=any(directory.glob('ACTUAL_AGENT_START*.json'))));continue
        if row['trial_id'] is not None:
            assert row['trial_id'] not in native_ids;native_ids.add(row['trial_id'])
        row.update(diagnostic30_tag=item['tag'],diagnostic30_task_id=item['task_id'],trial_path=str(directory),
            repetition=item['repetition'],reused_original_nine=item['reuse_existing_trial'],
            accepted_environment_continuation=source is not None,accepted_registration=source['registration'] if source else None,
            disk_failure_recovery=key in disks,disk_recovery_of=disks[key]['original_identity'] if key in disks else None,
            pre_model_environment_continuation=recovery is not None,original_preparation_trial_path=str(original))
        rows.append(row)
        if on_row:on_row(rows)
    stats={}
    for tag in models:
        group=[x for x in rows if x['diagnostic30_tag']==tag];stats[tag]=metric.aggregate(group,30)
        stats[tag].update(native_results=sum(x.get('native_result_exists',True) for x in group),
            explicit_missing_native_result_unknown=sum(not x.get('native_result_exists',True) for x in group),
            host_docker_transport_failures=sum(x.get('host_docker_transport_failure',False) for x in group))
    value=dict(checked_at=time.time(),complete=len(rows)==150,logical_terminal=len(rows),expected=150,
        models=stats,first_pass_models={tag:metric.aggregate([x for x in first_pass if x['diagnostic30_tag']==tag],30) for tag in models},
        pending=pending,first_pass_audit_pending=first_pass_audit_pending,accepted_registrations=registrations,disk_recovery_registration=disk_proof,
        cached_audits_only=not allow_fresh_audit,
        accepted_environment_continuations=sum(x['accepted_environment_continuation'] for x in rows),
        pre_model_continuations=sum(x['pre_model_environment_continuation'] for x in rows),
        plan_sha256=sha(plan_path),sampling_manifest_sha256=sha(sampling),wheel_sha256=config['wheel_sha256'],
        metric_source_sha256=sources[metric.__name__],audit_sources=sources,
        original_results_rewards_and_recorders_unmodified=True,formal801_excluded=True,synthetic32_excluded=True,
        no_model_attempt_retried_or_best_attempt_selected=True,actual_model_or_task_calls=0)
    return value,rows,first_pass

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--cached-only',action='store_true');args=parser.parse_args()
    if args.cached_only:
        value,rows,first_pass=collect(allow_fresh_audit=False)
        value.update(source_sha256=sha(Path(__file__)),read_only=True,derived_files_written=0)
        print(json.dumps(value));return
    path=E/'checks/DIAGNOSTIC150_MATRIX_ROWS_R6.jsonl'
    def checkpoint(rows):
        tmp=path.with_name(path.name+'.tmp');tmp.write_text(''.join(json.dumps(x)+'\n' for x in rows));tmp.replace(path)
    value,rows,first_pass=collect(on_row=checkpoint,allow_fresh_audit=not args.cached_only)
    for target,items in [(path,rows),(E/'checks/DIAGNOSTIC150_FIRST_PASS_ROWS_R6.jsonl',first_pass)]:
        tmp=target.with_name(target.name+'.tmp');tmp.write_text(''.join(json.dumps(x)+'\n' for x in items));tmp.replace(target)
    value.update(rows_sha256=sha(path),source_sha256=sha(Path(__file__)))
    save(E/'checks/DIAGNOSTIC150_MATRIX_R6.json',value)
    lines=['# 五组共同30题诊断（R6）','',
        '按冻结150项逻辑身份读取：原已开始模型尝试保留；已登记的三组15+25+23个NoSpace零模型恢复优先于accepted R4，按模型+Task联合身份，计划或admission存在但新Result未出现时保持PENDING，不用旧基础设施失败充数。新增32题完全独立，不参与本表或选模。','',
        '| 模型 | 已审计逻辑终态/30 | 原生Result | 确认Reward成功 | 评分及协议覆盖 | 缺Result UNKNOWN |',
        '|---|---:|---:|---:|---:|---:|']
    for tag,stats in value['models'].items():
        lines.append(f"| {tag} | {stats['terminal']}/30 | {stats['native_results']} | {stats['confirmed_reward_successes']} | {stats['coverage']:.2%} | {stats['explicit_missing_native_result_unknown']} |")
    lines+=['',f"尚未终态或待Recorder审计：{len(value['pending'])}项；原First-pass待审计：{len(value['first_pass_audit_pending'])}项。",
        '缺失原生Result的旧OOM两条及驱动崩溃三条仅记明确UNKNOWN，UUID及Reward均为null；独立恢复的Verifier Reward不回填原记录。已有SHA匹配的历史审计复用其原始来源，未声称重新审计；新审计逐行原子缓存。',
        '统一使用metric R8重新聚合；仅可信原生Raw异常头精确匹配Docker SSH dial-stdio255的派生资格为UNKNOWN，原Raw/数值Reward/旧审计SHA不改，旧raw_official_score_valid另留pre_host_transport_raw_official_score_valid。普通CLI非零不由本规则排除。正常完整成功和超时但Reward成功分列。选择规则为已确认正确数最大及冻结平局顺序；30题属于89题子集，后续89题×3不是未经选择的留出估计。',
        '',f"行SHA：`{value['rows_sha256']}`；源码SHA：`{value['source_sha256']}`；Wheel SHA：`{value['wheel_sha256']}`。"]
    (E/'reports/DIAGNOSTIC150_COMPARISON_R6.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(expected=150,logical_terminal=len(rows),pending=len(value['pending']),complete=value['complete'],actual_model_calls=0)))

if __name__=='__main__':main()
