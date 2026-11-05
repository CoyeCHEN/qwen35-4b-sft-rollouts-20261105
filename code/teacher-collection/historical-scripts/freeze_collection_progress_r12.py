"""Freeze a small partial operational receipt; never declares corpus completion."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)


def main():
    ids = ['task_001025_8d13ffe8', 'task_004900_ebeb969a', 'task_005562_00c4dfae',
        'software-engineering_20260419_182351_009', 'software-engineering_20260419_112101_020',
        'software-engineering_20260414_091921_009', 'software-engineering_20260413_174325_009',
        'software-engineering_20260413_173854_019', 'machine-learning_20260607_104421_001']
    promotions = []
    for ident in ids:
        path = R / 'checks/native-environment-reviews-r10' / (ident + '.json')
        review = read(path)
        assert review['status'] == 'ENV_READY' and review['model_calls'] == 0
        assert review['task_or_test_modifications'] == 0
        assert sha(Path(review['prior_outcome'])) == review['prior_outcome_sha256']
        receipts = []
        for p in (R / 'stream/collection-r4/deployment-r7b/ready-revisions' / ident).glob('*.json'):
            value = read(p)
            if value.get('raw_outcome') != str(path):
                continue
            assert value['raw_outcome_sha256'] == sha(path)
            assert value['engine_id'] == '59c8ba22-0aa4-4aed-bc43-4e1b5989fa22'
            for kind in ['install', 'nop']:
                assert sha(Path(value['native_' + kind + '_trial']) / 'result.json') == value[kind + '_result_sha256']
            receipts.append(dict(path=str(p), sha256=sha(p)))
        assert len(receipts) == 1
        promotions.append(dict(task_id=ident, review=str(path), review_sha256=sha(path),
            current17_ready=receipts[0], original_failure=review['prior_outcome'],
            original_failure_sha256=review['prior_outcome_sha256']))
    freeze(R / 'checks/readiness-public-boundary-promotion-r22.json', dict(
        status='NINE_PUBLIC_BOUNDARIES_REVIEWED_WITHOUT_NEW_MODEL_CALLS', tasks=promotions,
        model_calls=0, original_failures_preserved=True, task_or_test_modifications=0,
        location_correction='R21 completed qsim then stopped at an R8 failure path. Its source and accepted review remain immutable. R22 validated all four remaining records and their actual R8/R7b paths before publication.'))
    state_path = R / 'stream/collection-r4/deployment-r8/state.json'
    state = read(state_path)
    qualification = read(R / 'checks/collection-qualification.json')
    manifest = read(R / 'stream/collection-r4/deployment-r8/CAMPAIGN.json')
    assert all(sha(R / 'scripts' / name) == digest for name, digest in manifest['helper_sha256'].items())
    slots = sorted((R / 'checks').glob('actual-teacher-eight-and-backfill-r10-*.json'))[-1]
    slot_proof = read(slots)
    rollout = sorted((R / 'checks').glob('deployment17-rollout-acceptance-r8-*.json'))[-1]
    deployment = read(rollout)
    unit = subprocess.run(['systemctl', '--user', 'show', 'qwen35-tb21-monitor.service',
        '-p', 'Result', '-p', 'ExecMainStatus', '-p', 'ExecMainStartTimestamp',
        '-p', 'ExecMainExitTimestamp', '-p', 'TimeoutStartUSec'], capture_output=True, text=True, check=True).stdout
    pool_keys = ['planned_unique_tasks', 'terminal_native_trials', 'independent_tasks_with_terminal_trials',
        'raw_reward_one', 'qualified_independent_tasks', 'primary_trajectories', 'classifications']
    value = dict(status='PARTIAL_COLLECTION_AND_TARGET_AUDIT_CONTINUING',
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), controller_state=state,
        controller_state_path=str(state_path), controller_state_sha256=sha(state_path),
        qualification_checked_at=qualification['checked_at'],
        pools={pool:{key:item[key] for key in pool_keys} for pool,item in qualification['pools'].items()},
        actual_eight_evidence=str(slots), actual_eight_evidence_sha256=sha(slots),
        provider_events_all_eight=slot_proof['all_eight_current_have_provider_events'],
        completed_backfill_cycles=slot_proof['completed_backfill_cycles'],
        recent_backfill_gaps_seconds=[x['gap_seconds'] for x in slot_proof['recent_cycles']],
        deployment_evidence=str(rollout), deployment_evidence_sha256=sha(rollout),
        new17_teacher_dispatches=deployment['new_teacher_dispatches'],
        remaining149_task_containers=deployment['remaining_owned149_containers'],
        new149_creates_after_fence=deployment['new_owned149_creates_after_fence'],
        original_context_preparation=read(R / 'stream/direct17-native-source-r17/state.json'),
        finite_zero_model_environment_recheck=read(R / 'stream/native-transport-recheck17-r20/state.json'),
        data_audit_worker=read(R / 'checks/stream-r4-data-audit-worker.json'),
        existing_monitor_service=unit, research_contract_changes=0, training_started=False,
        corpus_freeze='PENDING_ALL_TASKS_AND_ALL_TARGET_AUDITS')
    freeze(R / 'checks/collection-operational-summary-r12.json', value)
    counts = {pool:x['qualified_independent_tasks'] for pool,x in value['pools'].items()}
    lines = ['# 17 SSD采集进展 R12：partial', '', '记录时间：' + value['created_at'], '',
        '唯一新增派发控制器仍为R8/PID4077727；前代仅收尾已开始的原生Trial。源码哈希全部匹配，研究合同未变。', '',
        '实际8并发证据：' + str(slots) + '。8个Trial均有Provider事件与Recorder，检查期间活动Trial集合稳定，最大并发8。',
        '已记录' + str(value['completed_backfill_cycles']) + '次完成后补位，最近10次间隔为' + str(value['recent_backfill_gaps_seconds']) + '秒。历史较长间隔及40.102秒交接空档均保留。', '',
        'R8新增' + str(value['new17_teacher_dispatches']) + '个教师Trial均使用17专用SSD Engine59c8ba22-0aa4-4aed-bc43-4e1b5989fa22；149本轮任务容器0，交接后新增0。镜像构建/运行层/工作区/Verifier/主日志均使用17 SSD。', '',
        '当前状态时间：' + state['checked_at'] + '；实际教师' + str(state['actual_teacher_trials']) + '，缓冲' + str(state['ready_buffer_by_pool']) + '，实际或保守预留尝试' + str(state['submitted_attempts']) + '，涉及' + str(state['teacher_independent_tasks']) + '个独立Task。上限仍为1000题/2000尝试/每题2次。', '',
        '成功索引时间：' + qualification['checked_at'] + '；合格独立Task为' + str(counts) + '，分别距离500还有' + str({p:500-n for p,n in counts.items()}) + '。Raw Reward1、终态Trial和独立Task计数及所有失败分类见机器清单，均未混报。', '',
        '9题经公开题目边界与已完成Native17 Result复核恢复Ready；缺失命令/依赖属于明确的初始任务状态。未修改Task、测试、镜像或Reward，未重跑教师。旧ENV_FAILED与新的SHA绑定Ready并存。',
        '另外10题明确的预检基础设施失败使用一个准备槽各复检一次，目前计数' + str(value['finite_zero_model_environment_recheck']['counts']) + '；其余继续准备，不计教师并发或成功。', '',
        '逐目标审计继续。257个主轨迹的不可变全Token标签、目标一次监督、映射SHA及256K/128K覆盖见DATA_FREEZE_PROGRESS.md和checks/partial-primary-target-audit-r12/，该快照与最新成功索引分别统计。最终两份DATA_MANIFEST及DATA_AUDIT待全量收尾；未启动正式训练。', '',
        '20分钟监控沿用原Timer，已加入有限环境复检状态。最近服务结果：', '', unit.rstrip(), '']
    with (R / 'DEPLOYMENT17_PROGRESS_R12.md').open('x') as stream:
        stream.write('\n'.join(lines))
    print(json.dumps(dict(actual=state['actual_teacher_trials'], qualified=counts,
        promoted_public_boundaries=len(promotions), recheck=value['finite_zero_model_environment_recheck']['counts'])))


if __name__ == '__main__':
    main()
