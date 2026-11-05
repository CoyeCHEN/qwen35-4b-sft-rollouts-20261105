"""Read the common 30-task checkpoint matrix; retain old native/OOM evidence."""
import hashlib
import importlib
import json
from pathlib import Path
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1'
legacy=importlib.import_module('compare-epoch3-epoch5-readonly149-r6')
inspect_trial=importlib.import_module('audit-native-response-qualification-r1').inspect_trial
prep=importlib.import_module('evaluation-preparation18-r1')
aggregate=importlib.import_module('compare-formal801-readonly-r8').aggregate
def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    temp=path.with_name(path.name+'.tmp');temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(path)


def main():
    config=read(R/'configs/diagnostic150-five-model-r1.json')
    plan_path=E/'manifests/DIAGNOSTIC150_TRIAL_PLAN_R1.json';plan=read(plan_path)
    sampling=E/'manifests/DIAGNOSTIC30_SAMPLING_MANIFEST_R1.json'
    assert sha(sampling)==plan['sampling_manifest_sha256']and len(plan['trials'])==150
    models={m['tag']:m for m in config['models']}
    cache_path=E/'checks/DIAGNOSTIC150_MATRIX_ROWS_R2.jsonl'
    cached={}
    for path in [E/'checks/EPOCH3_VS_EPOCH5_ROWS_R6.jsonl',E/'checks/DIAGNOSTIC30_MATRIX_ROWS_R1.jsonl',cache_path]+sorted((E/'checks').glob('DIAGNOSTIC30_ROWS_*.jsonl'))+sorted((E/'checks').glob('PRE_MODEL_ENV_RECOVERY_*_ROWS_R1.jsonl')):
        if path.exists():
            for line in path.open():
                row=json.loads(line)
                path_value=row.get('trial_path')or(str(Path(row['result_path']).parent)if row.get('result_path')else None)
                if path_value:cached[str(Path(path_value).resolve())]=row
    rows=[];first_pass=[];pending=[];identities=set()
    for item in plan['trials']:
        model=models[item['tag']]
        directory=E/'jobs'/model['job_name']/item['trial_name']
        if item['reuse_existing_trial']:
            original=E/'jobs/qwen35-new772-new-m1-epoch3-fixed-diagnostic'/item['trial_name']
            directory=legacy.e3_directory('new-m1',item['task_id'],original)
        original_directory=directory
        first_result=original_directory/'result.json'
        if first_result.exists():
            old=cached.get(str(original_directory.resolve()))
            if old is not None:assert old['result_sha256']==sha(first_result);first_row=dict(old)
            else:first_row=inspect_trial(original_directory)
            first_pass.append(dict(first_row,diagnostic30_tag=item['tag']))
        recovery_path=E/'manifests'/('PRE_MODEL_ENV_RECOVERY_PLAN_'+item['tag']+'_R1.json')
        recovery=None
        if recovery_path.exists():
            rp=read(recovery_path);recovery=next((x for x in rp['trials']if x['task_id']==item['task_id']),None)
            if recovery is not None:
                assert prep.pre_model_failure(original_directory)['result_sha256']==recovery['result_sha256']
                directory=E/'jobs'/rp['model']['job_name']/recovery['trial_name']
                if not(directory/'result.json').exists():
                    pending.append(dict(tag=item['tag'],task_id=item['task_id'],status='PRE_MODEL_ENV_CONTINUATION_PENDING'));continue
        result=directory/'result.json'
        if not result.exists():
            row=legacy.interrupted_terminal('new-m1',item['task_id'],directory)if item['reuse_existing_trial']else None
            if row is None:
                pending.append(dict(tag=item['tag'],task_id=item['task_id'],trial_name=item['trial_name']));continue
        else:
            cfg=read(directory/'config.json')
            assert cfg['agent']['kwargs']['wheel_sha256']==config['wheel_sha256']
            key=str(directory.resolve());old=cached.get(key)
            if old is not None:
                assert old['result_sha256']==sha(result)
                row=dict(old)
            else:row=inspect_trial(directory)
            assert row['task_id']==item['task_id']
            ident=row['trial_id'];assert ident not in identities;identities.add(ident)
        row=dict(row,diagnostic30_tag=item['tag'],diagnostic30_task_id=item['task_id'],
                 trial_path=str(directory),reused_original_nine=item['reuse_existing_trial'],
                 pre_model_environment_continuation=recovery is not None,
                 original_preparation_trial_path=str(original_directory)if recovery else None)
        rows.append(row)
    cache_path.write_text(''.join(json.dumps(row)+'\n'for row in rows))
    stats={}
    for tag in models:
        group=[row for row in rows if row['diagnostic30_tag']==tag]
        stats[tag]=aggregate(group,30)
        stats[tag]['native_results']=sum(row.get('native_result_exists',True)for row in group)
        stats[tag]['explicit_missing_native_result_unknown']=sum(not row.get('native_result_exists',True)for row in group)
    value=dict(checked_at=time.time(),complete=len(rows)==150,logical_terminal=len(rows),expected=150,
        models=stats,first_pass_models={tag:aggregate([r for r in first_pass if r['diagnostic30_tag']==tag],30)for tag in models},pre_model_continuations=sum(r['pre_model_environment_continuation']for r in rows),pending=pending,rows_sha256=sha(cache_path),plan_sha256=sha(plan_path),
        sampling_manifest_sha256=sha(sampling),wheel_sha256=config['wheel_sha256'],
        original_results_rewards_and_recorders_unmodified=True,formal801_excluded=True,
        old_r4_diagnostics_excluded=True,no_model_attempt_retried_or_best_attempt_selected=True,
        source_sha256=sha(Path(__file__)),actual_model_or_task_calls=0)
    save(E/'checks/DIAGNOSTIC150_MATRIX_R2.json',value)
    lines=['# 30题、五组Checkpoint诊断','',
        '同一份30题覆盖NEW-M1 Epoch3/Epoch5、NEW-M2 Epoch1/Epoch3/Epoch5，每组每题一次。原9题保留、按公开类别及seed42补21题，不读取模型成绩选题。全部结束后按已确认正确数选择一组，另跑完整89题×3次267项。原801计划保留为历史。','',
        '| 模型 | 逻辑终态/30 | 原生Result | 原始评分覆盖 | 协议及Recorder覆盖 | 确认成功 |','|---|---:|---:|---:|---:|---:|']
    for tag,s in stats.items():
        lines.append(f"| {tag} | {s['terminal']}/30 | {s['native_results']} | {s['raw_official_scoring_coverage']:.2%} | {s['protocol_and_recorder_qualified']/30:.2%} | {s['confirmed_reward_successes']} |")
    lines+=['','仅环境准备失败且Agent Setup/Execution/Result与模型调用均不存在的题目，使用独立身份做一次环境恢复接续，保留原始First-pass和恢复后统计；真实模型尝试不重跑。原M1 Epoch3两条控制器OOM缺原生Result继续作为显式UNKNOWN，未补造Reward或重跑。待运行记录不当作模型零分；未完成时确认成功率只是固定分母下界。五个Checkpoint不代表相同训练剂量；用户已明确改为按本30题已确认正确数选择模型，选择结果与原Epoch5预登记分开记录。',
        '',f'采样Manifest SHA：`{sha(sampling)}`；150身份计划SHA：`{sha(plan_path)}`；派生行SHA：`{sha(cache_path)}`。']
    (E/'reports/DIAGNOSTIC150_COMPARISON_R2.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(expected=150,logical_terminal=len(rows),pending=len(pending),complete=value['complete'],actual_model_calls=0)))


if __name__=='__main__':main()
