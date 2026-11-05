"""Immutable operational receipt; this is not a corpus release."""
import datetime
import hashlib
import json
from pathlib import Path

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    authority_path = R / 'checks/CURRENT_DISPATCH_AUTHORITY_R9.json'
    authority = read(authority_path)
    command = (Path('/proc') / str(authority['pid']) / 'cmdline').read_bytes().split(b'\0')
    if str(R / 'scripts/run_collection_stream_r9.py').encode() not in command:
        raise ValueError('Actual dispatch authority differs')
    manifest_path = Path(authority['manifest'])
    if sha(manifest_path) != authority['manifest_sha256']:
        raise ValueError('Campaign identity differs')
    manifest = read(manifest_path)
    if not all(sha(R / 'scripts' / name) == digest for name, digest in manifest['helper_sha256'].items()):
        raise ValueError('Frozen controller sources differ')
    state_path = Path(authority['state_path'])
    state_raw = state_path.read_bytes()
    state = json.loads(state_raw)
    if state['pid'] != authority['pid'] or state['actual_teacher_trials'] > 8:
        raise ValueError('Actual teacher authority/cap differs')
    slots_path = next(path for path in sorted((R / 'checks').glob('actual-teacher-eight-and-backfill-r13-*.json'), reverse=True)
        if read(path)['all_eight_current_have_provider_events'] and read(path)['stable_actual_active_trial_names_through_all_probes'])
    slots = read(slots_path)
    rollout_path = sorted((R / 'checks').glob('deployment17-rollout-acceptance-r9-*.json'))[-1]
    rollout = read(rollout_path)
    if rollout['remaining_owned149_containers'] or rollout['new_owned149_creates_after_fence']:
        raise ValueError('Unexpected149 Task runtime activity')
    qualification_path = R / 'checks/collection-qualification.json'
    qualification_raw = qualification_path.read_bytes()
    qualification = json.loads(qualification_raw)
    keys = ['planned_unique_tasks', 'terminal_native_trials', 'independent_tasks_with_terminal_trials',
        'raw_reward_one', 'qualified_independent_tasks', 'primary_trajectories', 'classifications']
    references = ['checks/private17-terminal-joint-acceptance-r3.json',
        'checks/controller-r9-native-handoff-progress.json', 'checks/controller-r8-admission-fence-r9.json',
        'checks/controller-r9-offline-acceptance-r1.json', 'checks/controller-r9-image-identity-acceptance-r1.json',
        'checks/exact-cold-resolver17-acceptance-r9.json',
        'checks/collection-monitor-last-hook-result-r28.json',
        'checks/monitor-usage-aggregate-r42-resource-rejection-and-revert.json',
        'checks/public-cg-build-goal-source-proof-r39.json',
        'manifests/CF_PUBLIC_VERIFIER_DEPENDENCY_APPROVALS_R39.json',
        'manifests/CF_PUBLIC_VERIFIER_DEPENDENCY_NODE_BINDINGS_R39.json',
        'stream/collection-r4/deployment-r8/DRAINED.json',
        'stream/direct17-native-source-r17/state.json',
        'stream/native-exact-archive-recheck17-r34/TERMINAL.json',
        'stream/native-exact-archive-recheck17-r43/state.json',
        'stream/historical-attempted-archive-delta-r35/TERMINAL.json']
    evidence = {name: dict(path=str(R / name), sha256=sha(R / name), value=read(R / name))
        for name in references if (R / name).exists()}
    hook = evidence['checks/collection-monitor-last-hook-result-r28.json']['value']
    archive_path = R / 'checks/native-tmax-resident-archive-r1.json'
    archive = read(archive_path)
    evidence['checks/native-tmax-resident-archive-r1.json'] = dict(path=str(archive_path), sha256=sha(archive_path),
        value={key:value for key,value in archive.items() if key != 'records'})
    worker = read(R / 'checks/stream-r4-data-audit-worker.json')
    value = dict(status='PARTIAL_COLLECTION_AND_TARGET_AUDIT_CONTINUING',
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), controller_state=state,
        controller_state_sha256=hashlib.sha256(state_raw).hexdigest(),
        qualification_checked_at=qualification['checked_at'],
        qualification_source_sha256=hashlib.sha256(qualification_raw).hexdigest(),
        pools={pool:{key:item[key] for key in keys} for pool,item in qualification['pools'].items()},
        actual_eight_evidence=str(slots_path), actual_eight_evidence_sha256=sha(slots_path),
        provider_events_all_eight=True, completed_backfill_cycles=slots['completed_backfill_cycles'],
        recent_backfill_cycles=slots['recent_cycles'],
        handoff_startup_gap_seconds=[47.152383, 69.7742, 46.486873],
        deployment_evidence=str(rollout_path), deployment_evidence_sha256=sha(rollout_path),
        new_r9_teacher_dispatches=rollout['new_teacher_dispatches'],
        new_r9_teacher_dispatches_by_pool=rollout['new_teacher_dispatches_by_pool'],
        audit_evidence=evidence,
        data_worker={key:worker[key] for key in ['pid','checked_at','stage','status']},
        original_resource_test_reward_changes=0, research_model_tool_budget_changes=0,
        final_corpus_freeze='PENDING_ALL_TASKS_AND_ALL_TARGET_AUDITS', training_started=False)
    with (R / 'checks/collection-operational-summary-r14.json').open('x') as stream:
        json.dump(value, stream, indent=2)
    counts = {pool:item['qualified_independent_tasks'] for pool,item in value['pools'].items()}
    gaps = [item['gap_seconds'] for item in slots['recent_cycles']]
    text = f'''# 17 SSD采集进展 R14：partial

快照时间：{value['created_at']}。

R9/PID{state['pid']}是唯一新增教师派发控制器；源码哈希全部一致。R8已于01:22:51 UTC按原生生命周期收尾完成，没有取消或重跑旧Trial。控制器留在149，后续准备、镜像、工作区、执行、Verifier和主日志使用17私有SSD Engine59c8ba22-0aa4-4aed-bc43-4e1b5989fa22。

真实8并发证据：checks/{slots_path.name}。8个活动教师均有Recorder和实际Provider事件，探测前后活动集合稳定，累计完成后补位{slots['completed_backfill_cycles']}次。最近10次补位间隔为{gaps}秒。R9交接启动时47.15、69.77、46.49秒的空槽和更早历史长空档均保留；后续稳态补位单独验收。

R9新增教师派发{rollout['new_teacher_dispatches']}次，分池{rollout['new_teacher_dispatches_by_pool']}；所有配置和实测Engine均为17。149本轮任务容器0，旧节点禁派时间后新增任务容器0。17原正式canary已通过Recorder、正常闭合、工具语义、Qwen目标及正式Loader联验，没有重跑canary。

最新控制器状态：{state['checked_at']}，实际教师{state['actual_teacher_trials']}，就绪缓冲{state['ready_buffer_by_pool']}；实际或保守预留尝试{state['submitted_attempts']}，独立任务{state['teacher_independent_tasks']}。环境准备、安装、NOP和配置预留与真实教师分开计数，仍遵守1000题/2000尝试/每题2次。

成功索引时间：{qualification['checked_at']}。合格独立任务/主轨迹数：{counts}；每池500缺口：{ {pool:500-count for pool,count in counts.items()} }。Raw reward1、终态Trial、样本、分段及目标数没有混报。

两题CF原镜像缺公开Verifier依赖已通过独立派生镜像修正：NumPy仅安装到原Verifier虚拟环境，另一题补公开CA证书。原镜像、原Task、官方测试、Reward、资源与时限保留；派生镜像身份及公开包SHA显式登记。CG题已获得真实reward1、无异常，但在Recorder/协议/Qwen审计完成前仍不计合格成功。没有预编译教师应完成的cg_solver_c模块。

原348题历史镜像归档及2题漏列保留归档均自然完成并核验；专用rsync不限速入口未改变。新到的原镜像按R43有限零模型原生验收继续准备，R17尚未检查的任务继续原队列，不设全1000就绪门禁，也不按教师成败换题。

既有20分钟监控的实际本轮钩子最近退出{hook['exit_code']}，耗时{hook['duration_seconds']}秒，距90秒上限{hook['deadline_margin_seconds']}秒。R42账本汇总候选虽通过全量功能等价测试，但未通过相同资源下的时限验收，已保留失败证据并回退45c076ad版本；尚未宣称监控性能优化完成。

逐目标CPU数据审计持续运行。既有257条主轨迹完整Token/标签/映射核验为独立不可变中间快照，不能冒充当前全部成功语料。全量最终Loader/Collator、两份最终DATA_MANIFEST与DATA_AUDIT仍待完成；语料未正式冻结，未启动训练。
'''
    with (R / 'DEPLOYMENT17_PROGRESS_R14.md').open('x') as stream:
        stream.write(text)
    print(json.dumps(dict(actual_teachers=state['actual_teacher_trials'], qualified=counts,
        new17_dispatches=rollout['new_teacher_dispatches'], monitor_seconds=hook['duration_seconds'])))


if __name__ == '__main__':
    main()
