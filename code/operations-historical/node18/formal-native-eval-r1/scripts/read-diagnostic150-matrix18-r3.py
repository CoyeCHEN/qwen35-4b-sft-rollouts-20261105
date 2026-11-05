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
DETACHED_SHA='9bce290779fedd585977a439eec00ddd43dd8148c6764593136ad09d1faf629b'

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):
    tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(p)
def identity(item):return item['tag'],item['task_id'],item['repetition']
def source_identities():
    modules=[prep,legacy,audit,audit.base,importlib.import_module('eval_audit_new772'),metric,behavior]
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

def unknown_row(task,directory,reason,**evidence):
    return dict(row_kind='DERIVED_TERMINAL_UNKNOWN_NO_ORIGINAL_NATIVE_RESULT',task_id=task,
        trial_name=directory.name,trial_path=str(directory),trial_id=None,native_result_exists=False,
        result_sha256=None,reward=None,raw_official_score_valid=False,valid_score=False,
        protocol_issues=[reason],trajectory_complete=False,normal_close=False,exception_type='ControllerDriverInterrupted',
        tool_argument_invalid=0,infrastructure_errors=['original_controller_driver_interruption'],failure_phase='controller',
        diagnostic_exclusion_reason=reason,no_native_trial_uuid_or_reward_invented=True,**evidence)

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
    path=E/'checks/DIAGNOSTIC150_MATRIX_ROWS_R3.jsonl'
    if path.exists():
        for line in path.open():
            row=json.loads(line)
            if row.get('reader_audit_sources')==sources and row.get('native_result_exists',True):
                cached[str(Path(row['trial_path']).resolve())]=row
    return cached

def inspect(directory,item,wheel,cached,sources,allow_fresh_audit=True):
    result=directory/'result.json';cfg=read(directory/'config.json')
    assert cfg['agent']['kwargs']['wheel_sha256']==wheel
    assert cfg['agent']['kwargs']['config']['model']['id']==item['model_name'].removeprefix('openai/')
    old=cached.get(str(directory.resolve()))
    if old and old['result_sha256']==sha(result):
        assert old['task_id']==item['task_id']
        return dict(old,reader_audit_sources=sources)
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
    row.update(reader_audit_sources=sources,trial_path=str(directory),repetition=item['repetition'])
    cached[str(directory.resolve())]=dict(row)
    return row

def collect(on_row=None,allow_fresh_audit=True):
    config=read(R/'configs/diagnostic150-five-model-r1.json');models={x['tag']:x for x in config['models']}
    plan_path=E/'manifests/DIAGNOSTIC150_TRIAL_PLAN_R1.json';plan=read(plan_path)
    sampling=E/'manifests/DIAGNOSTIC30_SAMPLING_MANIFEST_R1.json'
    assert len(plan['trials'])==150 and len({identity(x) for x in plan['trials']})==150
    assert sha(sampling)==plan['sampling_manifest_sha256']==config['sampling_manifest_sha256']
    sources=source_identities();cached=load_cache(sources);accepted,registrations=accepted_mapping(models);detached=detached_rows(models)
    assert set(accepted)<=set(map(identity,plan['trials'])) and not(set(accepted)&set(detached))
    rows=[];first_pass=[];first_pass_audit_pending=[];pending=[];native_ids=set()
    for item in plan['trials']:
        key=identity(item);original=prep.resolve_original(item,models);directory=original;recovery=None
        if (original/'result.json').exists():
            first=inspect(original,item,config['wheel_sha256'],cached,sources,allow_fresh_audit)
            if first is None:first_pass_audit_pending.append(dict(tag=item['tag'],task_id=item['task_id'],trial_path=str(original)))
            else:first_pass.append(dict(first,diagnostic30_tag=item['tag']))
        source=accepted.get(key)
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
            pre_model_environment_continuation=recovery is not None,original_preparation_trial_path=str(original))
        rows.append(row)
        if on_row:on_row(rows)
    stats={}
    for tag in models:
        group=[x for x in rows if x['diagnostic30_tag']==tag];stats[tag]=metric.aggregate(group,30)
        stats[tag].update(native_results=sum(x.get('native_result_exists',True) for x in group),
            explicit_missing_native_result_unknown=sum(not x.get('native_result_exists',True) for x in group))
    value=dict(checked_at=time.time(),complete=len(rows)==150,logical_terminal=len(rows),expected=150,
        models=stats,first_pass_models={tag:metric.aggregate([x for x in first_pass if x['diagnostic30_tag']==tag],30) for tag in models},
        pending=pending,first_pass_audit_pending=first_pass_audit_pending,accepted_registrations=registrations,
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
    path=E/'checks/DIAGNOSTIC150_MATRIX_ROWS_R3.jsonl'
    def checkpoint(rows):
        tmp=path.with_name(path.name+'.tmp');tmp.write_text(''.join(json.dumps(x)+'\n' for x in rows));tmp.replace(path)
    value,rows,first_pass=collect(on_row=checkpoint,allow_fresh_audit=not args.cached_only)
    for target,items in [(path,rows),(E/'checks/DIAGNOSTIC150_FIRST_PASS_ROWS_R3.jsonl',first_pass)]:
        tmp=target.with_name(target.name+'.tmp');tmp.write_text(''.join(json.dumps(x)+'\n' for x in items));tmp.replace(target)
    value.update(rows_sha256=sha(path),source_sha256=sha(Path(__file__)))
    save(E/'checks/DIAGNOSTIC150_MATRIX_R3.json',value)
    lines=['# 五组共同30题诊断（R3）','',
        '按冻结150项逻辑身份读取：原已开始模型尝试保留；仅已注册且原模型未开始的Task指向accepted R4原生映射。新增32题完全独立，不参与本表或选模。','',
        '| 模型 | 已审计逻辑终态/30 | 原生Result | 确认Reward成功 | 评分及协议覆盖 | 缺Result UNKNOWN |',
        '|---|---:|---:|---:|---:|---:|']
    for tag,stats in value['models'].items():
        lines.append(f"| {tag} | {stats['terminal']}/30 | {stats['native_results']} | {stats['confirmed_reward_successes']} | {stats['coverage']:.2%} | {stats['explicit_missing_native_result_unknown']} |")
    lines+=['',f"尚未终态或待Recorder审计：{len(value['pending'])}项；原First-pass待审计：{len(value['first_pass_audit_pending'])}项。",
        '缺失原生Result的旧OOM两条及驱动崩溃三条仅记明确UNKNOWN，UUID及Reward均为null；独立恢复的Verifier Reward不回填原记录。已有SHA匹配的历史审计复用其原始来源，未声称重新审计；新审计逐行原子缓存。',
        '统一使用metric R8重新聚合，正常完整成功和超时但Reward成功分列。选择规则为已确认正确数最大及冻结平局顺序；30题属于89题子集，后续89题×3不是未经选择的留出估计。',
        '',f"行SHA：`{value['rows_sha256']}`；源码SHA：`{value['source_sha256']}`；Wheel SHA：`{value['wheel_sha256']}`。"]
    (E/'reports/DIAGNOSTIC150_COMPARISON_R3.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(expected=150,logical_terminal=len(rows),pending=len(value['pending']),complete=value['complete'],actual_model_calls=0)))

if __name__=='__main__':main()
