"""Freeze an operational/data-audit progress receipt without claiming completion."""
import datetime
import hashlib
import json
from pathlib import Path

from observe_collection import protocol_report_metadata

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)


def evidence(relative):
    path = R / relative
    raw = path.read_bytes()
    return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(), value=json.loads(raw))


def main():
    state_path = R / 'stream/collection-r4/deployment-r8/state.json'
    raw_state = state_path.read_bytes()
    state = json.loads(raw_state)
    authority = read(R / 'checks/CURRENT_DISPATCH_AUTHORITY_R8.json')
    process = Path('/proc') / str(authority['pid']) / 'cmdline'
    if authority['pid'] != state['pid'] or 'run_collection_stream_r8.py' not in process.read_text():
        raise ValueError('Actual dispatch authority changed')
    manifest = read(R / 'stream/collection-r4/deployment-r8/CAMPAIGN.json')
    if not all(sha(R / 'scripts' / name) == digest for name, digest in manifest['helper_sha256'].items()):
        raise ValueError('Frozen active source hashes changed')
    slot_path = next(p for p in sorted((R / 'checks').glob('actual-teacher-eight-and-backfill-r10-*.json'), reverse=True)
        if read(p)['all_eight_current_have_provider_events'])
    slots = read(slot_path)
    rollout_path = sorted((R / 'checks').glob('deployment17-rollout-acceptance-r8-*.json'))[-1]
    rollout = read(rollout_path)
    if rollout['remaining_owned149_containers'] or rollout['new_owned149_creates_after_fence']:
        raise ValueError('New149 activity must be investigated')
    q_path = R / 'checks/collection-qualification.json'
    qualification_raw = q_path.read_bytes()
    qualification = json.loads(qualification_raw)
    pool_keys = ['planned_unique_tasks', 'terminal_native_trials', 'independent_tasks_with_terminal_trials',
        'raw_reward_one', 'qualified_independent_tasks', 'primary_trajectories', 'classifications']
    monitor = evidence('checks/collection-monitor-last-hook-result-r28.json')
    if not monitor['value']['passed']:
        raise ValueError('The actual collection hook did not pass')
    protocol = protocol_report_metadata(R / 'checks/stream-collection-r4-live-protocol.json')
    refs = ['checks/private17-terminal-joint-acceptance-r3.json',
        'checks/protocol-cache-r23-contract-acceptance.json',
        'checks/protocol-cache-r23-full-scope-acceptance.json',
        'checks/protocol-cache-r23-activation.json',
        'checks/monitor-usage-cache-r27-acceptance.json',
        'checks/observer-r27-resource-acceptance.json',
        'checks/collection-monitor-hook-result-parser-r28.json',
        'checks/cf-source-and-prepared-verifier-integrity-r25.json',
        'checks/optimization-verifier-python-public-dependency-probe-r25.json',
        'checks/public-pipeline-boundary-review-r25.json',
        'checks/public-native-recheck-boundary-reviews-r30.json',
        'checks/exact-original-archive-recheck-r29-offline-acceptance.json']
    scope_states = {}
    for scope in ['direct17-native-source-r17', 'native-transport-recheck17-r20',
            'native-verifier-timeout-recheck17-r24', 'native-exact-archive-recheck17-r29']:
        scope_states[scope] = evidence('stream/' + scope + '/state.json')
    old_failure = R / 'stream/native-exact-archive-recheck17-r29/environment-outcomes/task_003872_36777bc0.json'
    newer = R / 'stream/direct17-native-source-r17/environment-outcomes/task_003872_36777bc0.json'
    rejection = read(old_failure)
    ready = read(newer)
    if 'Immutable image-size proof differs' not in rejection['reason'] or ready['status'] != 'ENV_READY':
        raise ValueError('Expected image identity conflict/recovery changed')
    for kind in ['install', 'nop']:
        if sha(Path(ready['native_' + kind + '_trial']) / 'result.json') != ready[kind + '_result_sha256']:
            raise ValueError('New original-context native acceptance changed')
    identity_resolution = dict(task_id='task_003872_36777bc0',
        status='VALIDATED_NEW_ORIGINAL_CONTEXT_IDENTITY_RETAINED',
        rejected_old_image_id=rejection['original_failure']['image_id'],
        ready_image_id=ready['admitted_task']['image_id'],
        old_failure=str(old_failure), old_failure_sha256=sha(old_failure),
        new_native_ready=str(newer), new_native_ready_sha256=sha(newer),
        resolution='A different exact image already had the immutable size receipt. The old-image recheck failed closed; '
        'the17 original-context build subsequently passed its own CLI/initial-state/official NOP checks and published a new Ready. '
        'The existing receipt, original archives and all failures were preserved; no resolver hash check was weakened.',
        model_calls_by_resolution=0, task_or_test_changes=0, old_trial_configuration_changes=0)
    freeze(R / 'checks/exact-original-archive-binding-review-r30.json', identity_resolution)
    value = dict(status='PARTIAL_COLLECTION_AND_TARGET_AUDIT_CONTINUING',
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        controller_state=state, controller_state_path=str(state_path),
        controller_state_sha256=hashlib.sha256(raw_state).hexdigest(),
        qualification_checked_at=qualification['checked_at'],
        qualification_source_sha256=hashlib.sha256(qualification_raw).hexdigest(),
        pools={pool:{key:item[key] for key in pool_keys} for pool,item in qualification['pools'].items()},
        actual_eight_evidence=str(slot_path), actual_eight_evidence_sha256=sha(slot_path),
        provider_events_all_eight=slots['all_eight_current_have_provider_events'],
        completed_backfill_cycles=slots['completed_backfill_cycles'],
        recent_backfill_gaps_seconds=[x['gap_seconds'] for x in slots['recent_cycles']],
        deployment_evidence=str(rollout_path), deployment_evidence_sha256=sha(rollout_path),
        new17_teacher_dispatches=rollout['new_teacher_dispatches'],
        remaining149_task_containers=rollout['remaining_owned149_containers'],
        new149_creates_after_fence=rollout['new_owned149_creates_after_fence'],
        actual_completed_collection_monitor_hook=monitor,
        protocol_report_metadata=protocol, bounded_preparation=scope_states,
        audit_evidence={relative:evidence(relative) for relative in refs},
        image_identity_conflict_resolution=identity_resolution,
        data_audit_worker=evidence('checks/stream-r4-data-audit-worker.json'),
        research_contract_changes=0, training_started=False,
        final_corpus_freeze='PENDING_ALL_TASKS_AND_ALL_TARGET_AUDITS')
    freeze(R / 'checks/collection-operational-summary-r13.json', value)
    counts = {pool:item['qualified_independent_tasks'] for pool,item in value['pools'].items()}
    gaps = value['recent_backfill_gaps_seconds']
    hook = monitor['value']
    lines = ['# 17 SSD采集进展 R13：partial', '', '快照时间：' + value['created_at'], '',
        '唯一新增派发控制器：R8/PID' + str(state['pid']) + '，冻结源码哈希均一致；前代只收尾已开始的原生Trial。研究合同、固定Task/split与尝试上限未变。', '',
        '真实8并发：' + slot_path.name + '。8个活动Trial均有Recorder和实际Provider事件，检查前后活动集合稳定；全历史最大并发8。',
        '累计' + str(slots['completed_backfill_cycles']) + '次完成后补位；最近10次耗时' + str(gaps) + '秒。历史长空档、交接空档和23:21新槽Recorder尚未创建的阴性快照均保留，不删去。', '',
        'R8新增' + str(value['new17_teacher_dispatches']) + '次教师派发全部指向17 SSD专用Engine59c8ba22-0aa4-4aed-bc43-4e1b5989fa22；149本轮容器0，交接后新增0。原17联验已通过Recorder、Agent闭合、工具语义、Qwen目标及Loader审计，未重跑canary。', '',
        '控制器现场：' + state['checked_at'] + '，实际教师' + str(state['actual_teacher_trials']) + '，就绪缓冲' + str(state['ready_buffer_by_pool']) + '，实际或保守预留尝试' + str(state['submitted_attempts']) + '，涉及' + str(state['teacher_independent_tasks']) + '个独立任务。环境准备/NOP不计教师并发。', '',
        '成功索引时间：' + qualification['checked_at'] + '。合格独立任务/主轨迹数：' + str(counts) + '；相对每池500的缺口为' + str({p:500-n for p,n in counts.items()}) + '。Raw reward1、终态Trial、多轮样本、分段及目标数分别统计。', '',
        'R20的10题真实基础设施复验全部完成并恢复Ready；R24继续按原Verifier时限复验16题，保留仍超时的记录。公开管线Dask导入及ringbuf/patool目标库的边界审计已分别确认官方外层测试实际完成，新增SHA绑定Ready；未代替教师修题或安装目标库。',
        'R29对已到17的11份精确原镜像执行有限零模型原生验收，其他题继续准备。旧镜像与新原上下文构建的身份冲突在task_003872上被正确拒绝；后者已通过独立原生验收并发布Ready，旧失败与两份身份均保留。未放宽哈希校验。', '',
        '500份CF源Task与270份已声明教师部署副本的1544项私有文件校验无不一致。optimization题实际是官方镜像Verifier虚拟环境缺NumPy及pip，仍保留环境失败；没有改官方test.sh或把它冒充公开目标缺失。', '',
        '协议审计缓存已完成292条原算法逐行等价校验；每次复用仍重哈希全部Recorder/Result。生产报告已实际复用，缓存损坏、同尺寸改写、ArtifactRef和策略变化均有拒绝测试。只优化审计读取，不改变成功标准或原轨迹。', '',
        '沿用既有20分钟Timer。实际CF监控后置钩子最近完成耗时' + str(hook['duration_seconds']) + '秒，退出' + str(hook['exit_code']) + '，距离自身90秒上限还有' + str(hook['deadline_margin_seconds']) + '秒。已单独记录该钩子的真实退出状态；共享服务退出0不再替代本轮钩子成功。专用rsync不限速入口及原归档进程保留。', '',
        '逐目标数据审计继续；257个主轨迹的既有不可变全Token标签与映射审计见checks/partial-primary-target-audit-r12/，该快照与最新成功索引分别统计。全量正式缓存Loader/Collator核验、两份最终DATA_MANIFEST及DATA_AUDIT尚未完成，语料未正式冻结、未训练。', '']
    with (R / 'DEPLOYMENT17_PROGRESS_R13.md').open('x') as stream:
        stream.write('\n'.join(lines))
    print(json.dumps(dict(actual=state['actual_teacher_trials'], qualified=counts,
        cycles=slots['completed_backfill_cycles'], hook_seconds=hook['duration_seconds'])))


if __name__ == '__main__':
    main()
