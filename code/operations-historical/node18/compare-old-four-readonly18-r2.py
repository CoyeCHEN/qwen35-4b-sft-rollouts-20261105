"""Read the frozen four-arm doses/NLL/behavior summaries; no new experiments."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
P=R/'old-four-arm'
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
TAGS=['old-M1','old-M2']+[a+'-epoch'+str(e)for a in 'ABCD'for e in (1,3,5)]
def read(p):return json.loads(p.read_text())if p.exists()else None
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):
    temp=p.with_name(p.name+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.replace(p)


def arm_state(arm,plan):
    folder=Path(plan['output_dir']);path=folder/'preflight-evidence-rank0.jsonl'
    raw=path.read_bytes()if path.exists()else b'';events=[]
    for i,line in enumerate(raw.splitlines()):
        try:events.append(json.loads(line))
        except json.JSONDecodeError:
            if raw.endswith(b'\n')or i!=len(raw.splitlines())-1:raise
    updates=[e for e in events if e['event']=='optimizer_step'];metrics=[e for e in events if e['event']=='metrics']
    # Recovery is shown explicitly; do not turn repeated updates into unique retained optimizer steps.
    counts=Counter(e['global_step']for e in updates)
    checkpoints={}
    for epoch,step in [(1,106),(3,318),(5,530)]:
        marker=folder/('checkpoint-'+str(step))/'CHECKPOINT_COMPLETE.json'
        if marker.exists():
            state=read(marker.parent/'trainer_state.json')
            if state['global_step']!=step or state['epoch']<epoch-.01:raise ValueError('Old dose identity differs')
            checkpoints[str(epoch)]=dict(step=step,marker_sha256=sha(marker),trainer_state=state,
                native_metric_at_dose=[m['metrics']for m in metrics if m['global_step']==step])
    return dict(output_dir=str(folder),config_sha256=plan['config_sha256'],
        highest_observed_optimizer_step=max(counts,default=0),actual_observed_update_events=len(updates),
        repeated_native_step_events={str(k):v for k,v in counts.items()if v>1},
        checkpoint_doses=checkpoints,full_five_epoch_checkpoint=bool('5'in checkpoints),
        native_rank0_snapshot_sha256=hashlib.sha256(raw).hexdigest(),latest_metrics=metrics[-1]['metrics']if metrics else None)


def main():
    manifest=P/'manifests/experiments.json';plan=read(manifest)
    if not plan['supersedes_all_prior_five_arm_plans']or set(plan['arms'])!=set('ABCD'):
        raise ValueError('Only the final four-arm plan is authorized')
    identity_note=read(P/'manifests/EVALUATION443_TASK_IDENTITY_NOTE_R1.json')
    if not identity_note or identity_note['raw_task_id_strings']!=100:raise ValueError('Old443 identity interpretation is not verified')
    arms={a:arm_state(a,plan['arms'][a])for a in 'ABCD'}
    remote=read(C/'OLD112_REMOTE_NATIVE_STATUS_R2.json')or{};modes=remote.get('modes',{})
    readouts={};nll_count=0;behavior_terminal=0;behavior_complete_models=0
    for tag in TAGS:
        complete=P/'readouts443'/tag/'OLD443_NLL_COMPLETE.json';nll=read(complete)
        if nll:
            if not nll['passed']or nll['unique_rows']!=443 or nll['tag']!=tag:raise ValueError('Old443 readout membership differs')
            assert sha(complete.parent/'UNIQUE_ROWS.jsonl')==nll['unique_rows_sha256']
            assert sha(complete.parent/'RAW_PAYLOAD_SHA256.json')==nll['raw_payload_manifest_sha256']
            nll_count+=1
        state=modes.get('old-'+tag,{})
        done=state.get('complete');progress=state.get('progress')
        if done:
            if done['actual_terminal']!=8:raise ValueError('Old behavior scope differs')
            assert done['completed']and len(done['raw_result_identities'])==8
            behavior_terminal+=8;behavior_complete_models+=1
        elif progress:behavior_terminal+=progress.get('actual_terminal',0)
        readouts[tag]=dict(unique443_nll=nll,nll_complete_sha256=sha(complete)if nll else None,
            behavior_complete=done,behavior_progress=progress)
    contrasts={}
    for other,label in [('B','仅前缀Bug：A修复、B原始，LR2e-6'),('C','仅峰值LR：A2e-6、C1e-5'),('D','仅峰值LR：A2e-6、D5e-7')]:
        deltas={}
        for epoch in (1,3,5):
            a=readouts['A-epoch'+str(epoch)]['unique443_nll'];b=readouts[other+'-epoch'+str(epoch)]['unique443_nll']
            if a and b:
                deltas[str(epoch)]={group:dict(other_minus_A_sample_nll=b['groups'][group]['sample_mean_nll']-v['sample_mean_nll'],
                    other_minus_A_token_nll=b['groups'][group]['token_mean_nll']-v['token_mean_nll'],unique_rows=v['unique_rows'])
                    for group,v in a['groups'].items()if group in b['groups']}
        contrasts['A_vs_'+other]=dict(registered_factor=label,epoch_nll_deltas=deltas)
    training_complete=P/'checks/FOUR_NATIVE_TRAINING_RUNS_COMPLETED'
    full=training_complete.exists()and all(a['full_five_epoch_checkpoint']for a in arms.values())and nll_count==14 and behavior_terminal==112 and behavior_complete_models==14
    result=dict(checked_at=time.time(),complete=full,four_arm_manifest_sha256=sha(manifest),arms=arms,readouts=readouts,
        preregistered_contrasts=contrasts,complete443_readout_models=nll_count,terminal_behavior_trials=behavior_terminal,behavior_complete_models=behavior_complete_models,
        nll_rows_per_model=443,nll_raw_task_id_strings_per_model=100,
        nll_source_task_identity_groups=identity_note['source_task_identity_groups'],
        nll_identity_interpretation=identity_note,behavior_tasks_per_model=8,
        new_trials_or_training_dispatched=0,main_new_recipe_unchanged=True,only_low_lr_arm='D',
        native_training_complete_marker=dict(path=str(training_complete),exists=training_complete.exists(),sha256=sha(training_complete)if training_complete.exists()else None),
        native_training_worker_sha256=sha(R/'resume-old-four-native18-r3.py'),
        actual_selected267_completion_required=True,formal801_required=False,
        historical_old_wheel_sha256='f84f810e8a61545d685fb6722593886a0c88cc829b2ab9ca7c3476fe11e1209e',
        old_wheel_overflow_reset_fix_present=False,not_comparable_to_new11_protocol=True,
        terminal_separated_overflow_exit_candidates=sum((v['behavior_progress']or{}).get('terminal_separated_overflow_exit_candidates',0)for v in readouts.values()),
        context_recovery_unclassifiable_trials=sum((v['behavior_progress']or{}).get('context_recovery_unclassifiable_trials',0)for v in readouts.values()),
        raw_original_or_checkpoint_modified=False,source_sha256=sha(Path(__file__)))
    target=P/'checks/OLD_FOUR_UNIFIED_COMPARISON_R2.json';save(target,result)
    lines=['# 旧M2四组因果对照','',f'实际状态：五轮完整Checkpoint {sum(v["full_five_epoch_checkpoint"]for v in arms.values())}/4组；443行NLL {nll_count}/14模型；行为Trial终态{behavior_terminal}/112。',
        '', '旧研究在用户按共同30题选定模型的全89题n=3、267次评测及审计完成后执行，与新M1/M2目录、权重、数据严格隔离。','',
        '| 组 | 前缀 | Peak LR | 已观察最高优化步/530 | E1/3/5完整Checkpoint |','|---|---|---:|---:|---|']
    for arm in 'ABCD':
        v=arms[arm];lr={'A':'2e-6','B':'2e-6','C':'1e-5','D':'5e-7'}[arm]
        lines.append(f"| {arm} | {'原始Bug'if arm=='B'else'修复'} | {lr} | {v['highest_observed_optimizer_step']}/530 | {','.join(v['checkpoint_doses'])or'暂无'} |")
    lines+=['', 'A/B只比较前缀；A/C、A/D分别比较高/低峰值LR。所有组从同一旧M1初始化，1693 Train/125 Validation，DP4/GA4/MB1、名义Batch16。五轮Scheduler从开始完整定义，E1/3/5为106/318/530步；不同Epoch累计Token、LR和步数不同，不能当作等计算预算。',
        '', 'evaluation443是443条编码评价行、100个原始Task ID字符串，其中8对别名已通过原始Task checksum核实相同。实际覆盖52个TB2.1内容身份及40个旧M1任务组，共92个来源身份组；未声称旧40组与TB52做过跨数据集指令去重。旧读出中的unique_tasks=100字段表示原始ID字符串数，不是100个独立任务。分组存在重叠，443不是题数。教师强制Tool片段概率不是自主完成概率；NLL与真实Verifier行为并列报告。旧历史M2基线使用原始106步Scheduler，与五轮组的Epoch1不构成完全同Scheduler复现。',
        '', '预登记8题基于旧同题适配问题，标记TB21_SAME_TASK_ADAPTATION，不能外推为新模型泛化成绩。每模型n1，UNKNOWN不替换成普通零分；原十工具、Finish关闭、原Task时限。',
        '', 'Thinking循环复用原四连续相同Token块定义；后台查询的静态观察与变化分列，不把重复本身当作语义上无进展的证明。重编码Token不冒充历史未保存的原始生成Token IDs。']
    lines+=['','所有Recorder派生行为数字均为已确认下界；behavior_audit_completed/errors覆盖与原始JSON并列，缺失或失败不解释为无重复。旧研究严格保留f84f旧Wheel、原十工具和Finish关闭；该Wheel未包含连续超限恢复资格重置修复。因此与新11工具修复版五组30题不能直接横比。旧研究内各组同一Harness；任何恢复成功后再次超限退出模式按独立候选计数，Recorder模式本身不冒充确定因果证明。候选与不可判定计数见统一JSON，不改原Reward。']
    if not full:lines+=['','目前证据不足以给出完整四组因果结论，不据准备状态或训练Loss作结论。']
    else:
        lines+=['','四组预登记终点与读出已齐。以下为固定8题n1和443编码行的描述性比较，不作统计显著性或唯一根因断言。']
        for other,label in [('B','前缀修复（A修复/B原始）'),('C','高LR（C1e-5/A2e-6）'),('D','低LR（D5e-7/A2e-6）')]:
            aa=readouts['A-epoch5'];bb=readouts[other+'-epoch5'];an=aa['unique443_nll']['groups'];bn=bb['unique443_nll']['groups']
            ap=aa['behavior_progress']or{};bp=bb['behavior_progress']or{}
            values=[]
            for key in ('m2_all_validation125','m1_all_validation191'):
                if key in an and key in bn:
                    values.append(f"{key}样本NLL：A={an[key]['sample_mean_nll']:.6f}，{other}={bn[key]['sample_mean_nll']:.6f}")
            lines+=['',label+'：'+'；'.join(values)+f"。E5已确认Reward成功A={ap.get('successes',0)}/8、{other}={bp.get('successes',0)}/8；有效评分A={ap.get('valid_scores',0)}/8、{other}={bp.get('valid_scores',0)}/8。"]
        for arm in 'ABCD':
            series=[]
            for epoch in (1,3,5):
                item=readouts[arm+'-epoch'+str(epoch)];bp=item['behavior_progress']or{};groups=item['unique443_nll']['groups']
                nll=groups.get('m2_all_validation125',{}).get('sample_mean_nll')
                series.append(f"E{epoch}：确认成功{bp.get('successes',0)}/8，正常闭合{bp.get('normal_close',0)}/8，Timeout{bp.get('agent_timeouts',0)}，已确认Thinking重复Trial{bp.get('thinking_repetition_trials',0)}，工具参数错误确认下界{bp.get('tool_argument_invalid',0)}，行为审计已完成{bp.get('behavior_audit_completed',0)}/8、失败{bp.get('behavior_audit_errors',0)}/8，M2留出NLL={nll}")
            lines+=['',arm+'剂量轨迹：'+'；'.join(series)+'。']
        lines+=['','教师NLL较低而确认Task成功数未升、或旧M1留出NLL上升的情形，应分别解释为拟合改善与能力保持风险，不能用Loss代替Agent能力。覆盖不足保留UNKNOWN及固定分母确认下界；不择优Attempt，不追加训练或改变新M1/M2配方。']
    lines+=['',f'统一比较JSON SHA：`{sha(target)}`；四组Manifest SHA：`{sha(manifest)}`。每个模型的原始NLL、逐行SHA、行为Result及Recorder由JSON引用保留。']
    report=R/'reports/OLD_M2_FOUR_ARM_COMPARISON.md';report.write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(complete=full,full_five_epoch_arms=sum(a['full_five_epoch_checkpoint']for a in arms.values()),nll_models=nll_count,behavior_terminal=behavior_terminal,new_dispatches=0)))


if __name__=='__main__':main()
