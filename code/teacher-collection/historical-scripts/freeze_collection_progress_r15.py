"""Immutable current operational evidence; never a final corpus release."""
import csv
import datetime
import hashlib
import json
from collections import Counter
from pathlib import Path

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    authority=read(R/'checks/CURRENT_DISPATCH_AUTHORITY_R12.json');manifest=read(Path(authority['manifest']))
    if sha(Path(authority['manifest']))!=authority['manifest_sha256']:raise ValueError('Actual Campaign changed')
    if str(R/'scripts/run_collection_stream_r12.py').encode() not in (Path('/proc')/str(authority['pid'])/'cmdline').read_bytes().split(b'\0'):raise ValueError('Actual controller PID differs')
    if any(sha(R/'scripts'/name)!=digest for name,digest in manifest['helper_sha256'].items()):raise ValueError('Frozen sources changed')
    state=read(Path(authority['state_path']))
    if state['actual_teacher_trials']>8:raise ValueError('Global teacher cap exceeded')
    slots_path=next(p for p in sorted((R/'checks').glob('actual-teacher-eight-and-backfill-r92-*.json'),reverse=True) if read(p)['all_eight_current_have_provider_events'])
    slots=read(slots_path);rollout_path=sorted((R/'checks').glob('deployment17-rollout-acceptance-r12-*.json'))[-1];rollout=read(rollout_path)
    if rollout['remaining_owned149_containers'] or rollout['new_owned149_creates_after_fence']:raise ValueError('Unexpected149 runtime activity')
    qualification=read(R/'checks/collection-qualification.json')
    indexes={};counts={}
    for pool in ['CALIBFORGE','TMAX']:
        for suffix in ['SUCCESS_INDEX.jsonl','FAILURE_OR_PENDING_INDEX.jsonl']:
            name='indexes/'+pool+'_'+suffix;p=R/name;blob=p.read_bytes();rows=[json.loads(line) for line in blob.splitlines() if line]
            indexes[name]=dict(sha256=hashlib.sha256(blob).hexdigest(),rows=len(rows))
            if suffix=='SUCCESS_INDEX.jsonl':counts[pool.lower()]=len(rows)
    env=list(csv.DictReader((R/'ENVIRONMENT_1000_STATUS.csv').open()))
    hook=read(R/'checks/collection-monitor-last-hook-result-r28.json')
    references=['checks/private17-terminal-joint-acceptance-r3.json','checks/controller-r11-admission-fence-r12.json',
        'checks/controller-r12-native-handoff-progress.json','checks/controller-r12-offline-acceptance-r82.json',
        'checks/controller-r12-public-dependency-acceptance-r83.json','checks/deployment-r12-candidate-input-freeze-r81.json',
        'checks/original-verifier-failure-cleanup-review-r86.json','checks/monitor-final-env-r98-activation.json',
        'manifests/PUBLIC_DEPENDENCY_IMAGE_APPROVALS_R76.json','manifests/PRIVATE17_PUBLIC_IMAGE_BINDINGS_R76.json',
        'stream/existing-original-archive-variant17-r94/TERMINAL.json','stream/existing-original-archive-variant17-r94/PRIOR_ATTEMPT_GUARD.json',
        'stream/original-startup-nohup17-r97/TERMINAL.json','checks/current-primary-qwen-length-inventory-r51.json']
    value=dict(status='PARTIAL_COLLECTION_AND_TARGET_AUDIT_CONTINUING',created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        authority=authority,controller_state=state,index_metadata=indexes,qualified_primary_tasks=counts,
        qualification_checked_at=qualification['checked_at'],qualification=qualification['pools'],
        actual_eight_evidence=str(slots_path),actual_eight_evidence_sha256=sha(slots_path),
        stable_eight_with_real_provider_events=True,completed_backfill_cycles=slots['completed_backfill_cycles'],recent_backfills=slots['recent_cycles'],
        all_historical_delayed_backfills_preserved=slots['delayed_cycles'],
        rollout_evidence=str(rollout_path),rollout_evidence_sha256=sha(rollout_path),new_r12_dispatches=rollout['new_teacher_dispatches'],new_r12_dispatches_by_pool=rollout['new_teacher_dispatches_by_pool'],
        historical_environment_counts={pool:dict(Counter(x['status'] for x in env if x['pool']==pool)) for pool in ['calibforge','tmax']},
        actual17_environment_counts={pool:dict(Counter(x['runtime17_current_deployment_status'] for x in env if x['pool']==pool)) for pool in ['calibforge','tmax']},
        environment_csv_sha256=sha(R/'ENVIRONMENT_1000_STATUS.csv'),monitor_hook=hook,
        references={name:dict(sha256=sha(R/name)) for name in references if (R/name).is_file()},
        original_task_test_resource_verifier_changes=0,research_teacher_contract_changes=0,
        task7206_prior_attempts_preserved=1,task7206_remaining_teacher_attempts=1,
        final_corpus_freeze='PENDING_ALL_TASKS_AND_ALL_TARGET_AUDITS',formal_training_started=False)
    with (R/'checks/collection-operational-summary-r15.json').open('x') as f:json.dump(value,f,indent=2)
    text=f'''# 17 SSD采集与数据审计 R15：partial

快照：{value['created_at']}。唯一新增派发控制器为R12/PID{authority['pid']}；旧控制器仅完成原生生命周期，无旧Trial被取消、重跑或改写。控制器仍在149；新镜像检查、加载、工作层、工作区、教师、Verifier、清理和主日志使用17私有SSD Engine59c8ba22-0aa4-4aed-bc43-4e1b5989fa22。部署配置SHA为{manifest['deployment_config_sha256']}。

严格真实8并发证据：checks/{slots_path.name}。8个活动Trial均有Recorder和实际Provider事件，活动集合稳定，全程重叠上限8。已记录完成到补位{slots['completed_backfill_cycles']}次，最近10次间隔为{[x['gap_seconds'] for x in slots['recent_cycles']]}秒。全部历史长空槽、交接启动间隔及未通过的观察快照保留。

R12已新增{rollout['new_teacher_dispatches']}个教师Trial，分池{rollout['new_teacher_dispatches_by_pool']}，配置均使用17。149本轮任务容器0，原禁派时间后新建本轮容器0；各Trial原始配置、真实Engine和SSD挂载证据在checks/{rollout_path.name}。原17正式canary的Recorder/正常闭合/工具/Qwen/Loader联验仍有效，没有重复运行canary。

控制器时间{state['checked_at']}：实际教师{state['actual_teacher_trials']}，就绪缓冲{state['ready_buffer_by_pool']}；实际或保守预留尝试{state['submitted_attempts']}，独立任务{state['teacher_independent_tasks']}。安装、镜像、NOP和仅写配置不冒充教师并发；1000题/2000完整尝试/每题2次上限保持。

当前成功索引的合格独立主轨迹：{counts}；每池500缺口为{ {pool:500-count for pool,count in counts.items()} }。原始reward1、终态Trial、独立任务、主轨迹、样本、分段和目标采用独立分母。旧task_000575_08a41bf3已由真实审计进入合格索引；不是仅凭旧reward1判定。

新批准部署含两项TMax公开依赖修复与两项原生后台进程初始化：原Python3.10的公开pytest缓存、公开字体及原定义的输入图片生成/权限；另外按原container.def启动已声明的后台服务。原镜像与原失败均保留，派生镜像和配置版本另行冻结。两个原CF公开依赖镜像批准保持字节身份，CF Verifier专用代理和Cargo专用代理保持原范围，教师模型HTTP链路不变。

ENV_READY包含单列的原始NOP限制：未解目标死锁，以及原SMTP测试失败路径未清理非daemon线程。这些旧NOP仍为超时、无Reward，不能称为完整Verifier通过或正常零分；合格教师成功仍须官方Verifier实际完成reward1、无评分基础设施异常、正常Agent闭合和全部Recorder/Qwen核验。参见checks/original-verifier-failure-cleanup-review-r86.json。

task_007206_2ea22c7f旧reward1因Thinking和原环境合同被排除，真实旧尝试1次仍保留。17既有原始归档已经精确复用并通过原始初始/CLI/NOP，未重建归档、未清零计数；仅允许本题剩余1次教师尝试。task_004361_0d2c270d继续排查原始后台进程的生命周期，仍无教师调用、未批准、未替换；原程序字节身份及各次初始测试/基础设施失败均留档。

原始选定1000题的环境状态：{value['historical_environment_counts']}。17物理部署状态另列为{value['actual17_environment_counts']}；历史149已运行任务不会为迁移重跑。不得将历史Ready等同于17全部Ready。源修复与候补均不按模型成败选择，原固定分层/家族split与7个既有候补绑定保留。

监控沿用同一20分钟Timer，最近真实自身钩子退出{hook['exit_code']}、耗时{hook['duration_seconds']}秒，距90秒上限{hook['deadline_margin_seconds']}秒。新R98是否已经实跑以原生Timer回执时间为准，不拿主service成功代替本轮钩子成功。专用client-bin-v2/rsync不限速入口保持，系统rsync未修改；348+2项历史镜像归档均已自然完成，不重启旧归档进程。

逐目标CPU审计、Recorder和Token费用账本持续进行。既有257条全Token/标签/映射核验、359条长度聚合均是独立历史中间快照，不冒充当前全部成功缓存的最终审计。两份独立最终DATA_MANIFEST、全量正式Loader/Collator及DATA_AUDIT仍待全部任务和目标终态；不静默截断，不丢收尾，不剥离依赖图片的目标，不混入旧TB21、167未知Reward或TMax既有SFT轨迹。语料尚未正式冻结，未启动正式训练。
'''
    with (R/'DEPLOYMENT17_PROGRESS_R15.md').open('x') as f:f.write(text)
    print(json.dumps(dict(actual_teachers=state['actual_teacher_trials'],qualified_primary_tasks=counts,attempts=state['submitted_attempts'],independent_tasks=state['teacher_independent_tasks'],strict_eight_proof=slots_path.name)))


if __name__=='__main__':main()
