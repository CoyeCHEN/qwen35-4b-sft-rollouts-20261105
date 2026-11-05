"""Record current deployment evidence and audit boundaries without stopping work."""
from collections import Counter
import csv
import datetime
import hashlib
import json
from pathlib import Path

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
read=lambda path:json.loads(path.read_bytes())
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    authority=read(R/'checks/CURRENT_DISPATCH_AUTHORITY_R15.json')
    manifest_file=Path(authority['manifest']);manifest=read(manifest_file)
    if sha(manifest_file)!=authority['manifest_sha256']:raise ValueError('Campaign changed')
    if str(R/'scripts/run_collection_stream_r15.py').encode() not in (Path('/proc')/str(authority['pid'])/'cmdline').read_bytes().split(b'\0'):
        raise ValueError('Controller PID identity changed')
    if any(sha(R/'scripts'/name)!=digest for name,digest in manifest['helper_sha256'].items()):raise ValueError('Frozen source changed')
    state=read(Path(authority['state_path']))
    strict=next(path for path in sorted((R/'checks').glob('actual-teacher-eight-and-backfill-r130-*.json'),reverse=True)
        if read(path)['all_eight_current_have_provider_events'])
    slots=read(strict)
    rollout_path=sorted((R/'checks').glob('deployment17-rollout-acceptance-r15-*.json'))[-1]
    rollout=read(rollout_path)
    if rollout['remaining_owned149_containers'] or rollout['new_owned149_creates_after_fence']:raise ValueError('Unexpected149 runtime')
    counts={};indexes={}
    for pool in ['CALIBFORGE','TMAX']:
        for suffix in ['SUCCESS_INDEX.jsonl','FAILURE_OR_PENDING_INDEX.jsonl']:
            path=R/'indexes'/(pool+'_'+suffix);blob=path.read_bytes();rows=[json.loads(line) for line in blob.splitlines()]
            indexes[str(path)]=dict(sha256=hashlib.sha256(blob).hexdigest(),rows=len(rows))
            if suffix=='SUCCESS_INDEX.jsonl':
                if any(not x['is_primary_trajectory'] or not x['qualified_success'] for x in rows):raise ValueError('Unqualified primary')
                counts[pool.lower()]=len(rows)
    env=list(csv.DictReader((R/'ENVIRONMENT_1000_STATUS.csv').open()))
    partial=R/'checks/partial-primary-target-audit-r136/PARTIAL_DATA_TARGET_AUDIT_R136.json'
    partial_doc=read(partial)
    hook=read(R/'checks/collection-monitor-last-hook-result-r28.json')
    stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    value=dict(status='PARTIAL_COLLECTION_AND_DATA_AUDIT_CONTINUING',checked_at=stamp,
        authority=authority,controller_state=state,indexes=indexes,qualified_primary_tasks=counts,
        historical_environment_counts={pool:dict(Counter(x['status'] for x in env if x['pool']==pool)) for pool in ['calibforge','tmax']},
        runtime17_environment_counts={pool:dict(Counter(x['runtime17_current_deployment_status'] for x in env if x['pool']==pool)) for pool in ['calibforge','tmax']},
        strict_eight_evidence=str(strict),strict_eight_sha256=sha(strict),strict_eight_observed_at=slots['checked_at'],
        completed_backfill_cycles=slots['completed_backfill_cycles'],recent_backfill_gaps_seconds=[x['gap_seconds'] for x in slots['recent_cycles']],
        delayed_backfill_cycles_preserved=len(slots['delayed_cycles']),rollout_evidence=str(rollout_path),rollout_sha256=sha(rollout_path),
        partial_cache_audit=str(partial),partial_cache_audit_sha256=sha(partial),
        partial_cache_independent_tasks={pool:x['qualified_independent_tasks'] for pool,x in partial_doc['pools'].items()},
        monitor_latest_completed_own_hook=hook,monitor_resource_acceptance=read(R/'checks/monitor-health-io-r134-resource/result.json'),
        collection_limits=dict(unique_tasks=1000,attempts=2000,per_task=2,global_native_agent_permits=8),
        teacher_research_contract_changes=0,official_task_test_reward_changes=0,formal_corpus_release=False,formal_training_started=False)
    target=R/'checks/collection-operational-progress-r16.json'
    with target.open('x') as stream:json.dump(value,stream,indent=2)
    lines=['# 当前采集与数据交接 R16：partial','',f'更新时间：{stamp}。Goal继续运行；未冻结正式语料，未训练。',
        '',f'唯一新增派发总控：R15 / PID {authority["pid"]}，位于149。Manifest SHA `{authority["manifest_sha256"]}`。',
        f'运行配置 `configs/campaign-deployment17-r15.json` SHA `{manifest["deployment_config_sha256"]}`；控制器SHA `{sha(R/"scripts/run_collection_stream_r15.py")}`。禁止原地改冻结源码。',
        'R14→R15已按原生setup入队/终态、两次不同drain观察和唯一权限交接完成；旧控制器只继续既有生命周期。没有取消或重跑健康Trial。',
        '',f'当前原生Agent阶段={state["actual_teacher_trials"]}，Ready缓冲={state.get("ready_buffer_by_pool")}，安装/等槽={state["teacher_setup_or_gate_waiting"]}。原生Agent阶段包含CLI启动，不能单凭此数字声称已有8个模型调用。',
        f'严格8并发证据：`{strict.relative_to(R)}`，采样时间{slots["checked_at"]}；全部8个活动Trial有Recorder/Provider事件且活动集合稳定。已累计{slots["completed_backfill_cycles"]}次补位；最近10次间隔{value["recent_backfill_gaps_seconds"]}秒。所有{len(slots["delayed_cycles"])}次>15秒长等待及此前负采样保留，其中包含本次交接85.728592秒。',
        '',f'17运行验收：`{rollout_path.relative_to(R)}`。R15新增派发{rollout["new_teacher_dispatches"]}，分池{rollout["new_teacher_dispatches_by_pool"]}；逐Trial配置、实际Engine和SSD挂载均核验。149本轮任务容器0，禁派后新建本轮容器0。原正式canary7040完整联验有效，不重复运行。',
        '所有新环境/镜像检查、构建/加载、Ready、staging、教师、Verifier、工作区、主日志及清理绑定17私有SSD Engine `59c8ba22-0aa4-4aed-bc43-4e1b5989fa22`，socket `/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/engine17-r1/socket/docker.sock`。控制器位置不决定运行节点。149只保留历史工件及Harbor收集副本，17另存全文件SHA归档；共享17默认Docker未改。',
        '',f'当前合格独立主轨迹：{counts}；各池500缺口：{ {p:500-n for p,n in counts.items()} }。实际AgentStart和旧配置保守预留合计{state["submitted_attempts"]}次、涉及{state["teacher_independent_tasks"]}题，不能把预留全称作真实模型调用。逐题2次/全轮2000次上限保持。首次合格成功即停；模型失败不换题。',
        f'1000题历史环境结果：{value["historical_environment_counts"]}。17物理部署结果另列：{value["runtime17_environment_counts"]}；旧149已运行题不为迁移重跑。',
        '',f'R136不可变缓存逐Token/标签/Task-Trial-Call映射审计：{value["partial_cache_independent_tasks"]}，证据 `{partial.relative_to(R)}`。固定256K/128K长度均包含Qwen input+target、processor和padding；各类监督量、末目标、长目标隔离及逐题Token贡献完整保存。现有正式Loader/Collator/Serving/数值参考逐Trial证明保持。最终组合缓存的全量正式Loader/Collator及两份独立DATA_MANIFEST/DATA_AUDIT仍须在全部有界任务结束后完成。',
        '',f'R15的Ready扫描已改为纯扫描在线程执行、主事件循环应用；753个Ready结果与R14完全一致，新setup失败块及placement变化均会重查拒绝。R128实测最大事件循环停顿2.269秒→0.021秒。没有删除身份/哈希核验。',
        '当前监控R138 SHA `'+sha(R/'scripts/observe_collection.py')+'`，renderer138 SHA `'+sha(R/'scripts/collection_reports_r138.py')+'`，sampler130 SHA `'+sha(R/'scripts/capture_teacher_slots149_r130.py')+'`；沿用同一20分钟Timer。R134在原10%CPU/256MiB/90秒下实测56.2秒退出0；R132/R134带剖析器运行的超时负证据保留。R138只更换R15报告及452题缓存证据绑定；最近真正Timer钩子结果另见checks/collection-monitor-last-hook-result-r28.json，不能把候选测试当成Timer已执行新版本。',
        '', '继续项：全部剩余Task最多2次真实尝试；逐Result/Recorder/Qwen目标审计及完整费用Token账本；两池独立最终语料冻结。脚本check_final_data_readiness_r131.py先验证所有任务与目标终态，不能将NOT_READY改称通过。',
        '仍冻结：最终11工具、授权DeepSeek V4.1 Flash Max/Thinking max/262144/65536及既定Compaction/Recorder/HTTP/研究时限；原Task/资源/测试/Verifier/Reward、seed42/固定split/候补规则；同Task第一条合格成功主轨迹、真实试错及所有失败原件。',
        '数据writer PID502085，exporter8/qualifier9；R113三项原reward0仅细化失败标签，原结果不改。Task7206旧合同不符的付费尝试仍计1次，仅剩一次原生尝试已入队，禁止清零或第三次尝试。',
        '16条原生OpenSSH固定连接池r119保留，不重复启动或杀会话。client-bin-v2/rsync不限速SHA `8f9b3942d5be0d89e5d5822d94027e5ed8273c39e96a759abfacefbe8bd38c21`，系统rsync未改；原348+2归档均自然终态，不重启。',
        '禁止在本地构建环境、下载镜像/原始教师轨迹；最终缓存及大工件写17SSD。17系统盘空间紧张，不使用共享默认Docker，不清理其他窗口资源。', '']
    text='\n'.join(lines)
    (R/'DEPLOYMENT17_PROGRESS_R16.md').write_text(text)
    backup=R/'CURRENT_HANDOFF_before_r15_activation.md'
    if not backup.exists():backup.write_bytes((R/'CURRENT_HANDOFF.md').read_bytes())
    (R/'CURRENT_HANDOFF.md').write_text(text)
    print(json.dumps(dict(proof=str(target),qualified_primary_tasks=counts,native_agent_phases=state['actual_teacher_trials'],strict_eight=str(strict))))


if __name__=='__main__':main()
