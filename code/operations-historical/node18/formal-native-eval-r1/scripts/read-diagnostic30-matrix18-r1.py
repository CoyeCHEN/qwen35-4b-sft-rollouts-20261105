"""Read the common 30-task checkpoint matrix; retain old native/OOM evidence."""
import hashlib
import importlib
import json
from pathlib import Path
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1'
legacy=importlib.import_module('compare-epoch3-epoch5-readonly149-r6')
inspect_trial=importlib.import_module('audit-native-response-qualification-r1').inspect_trial
aggregate=importlib.import_module('compare-formal801-readonly-r7').aggregate
def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    temp=path.with_name(path.name+'.tmp');temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(path)


def main():
    config=read(R/'configs/diagnostic30-four-model-r1.json')
    plan_path=E/'manifests/DIAGNOSTIC30_120_TRIAL_PLAN_R1.json';plan=read(plan_path)
    sampling=E/'manifests/DIAGNOSTIC30_SAMPLING_MANIFEST_R1.json'
    assert sha(sampling)==plan['sampling_manifest_sha256']and len(plan['trials'])==120
    models={m['tag']:m for m in config['models']}
    cache_path=E/'checks/DIAGNOSTIC30_MATRIX_ROWS_R1.jsonl'
    cached={}
    for path in [E/'checks/EPOCH3_VS_EPOCH5_ROWS_R6.jsonl',cache_path]:
        if path.exists():
            for line in path.open():
                row=json.loads(line)
                if row.get('trial_path'):cached[str(Path(row['trial_path']).resolve())]=row
    rows=[];pending=[];identities=set()
    for item in plan['trials']:
        model=models[item['tag']]
        directory=E/'jobs'/model['job_name']/item['trial_name']
        if item['reuse_existing_trial']:
            original=E/'jobs/qwen35-new772-new-m1-epoch3-fixed-diagnostic'/item['trial_name']
            directory=legacy.e3_directory('new-m1',item['task_id'],original)
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
                 trial_path=str(directory),reused_original_nine=item['reuse_existing_trial'])
        rows.append(row)
    cache_path.write_text(''.join(json.dumps(row)+'\n'for row in rows))
    stats={}
    for tag in models:
        group=[row for row in rows if row['diagnostic30_tag']==tag]
        stats[tag]=aggregate(group,30)
        stats[tag]['native_results']=sum(row.get('native_result_exists',True)for row in group)
        stats[tag]['explicit_missing_native_result_unknown']=sum(not row.get('native_result_exists',True)for row in group)
    value=dict(checked_at=time.time(),complete=len(rows)==120,logical_terminal=len(rows),expected=120,
        models=stats,pending=pending,rows_sha256=sha(cache_path),plan_sha256=sha(plan_path),
        sampling_manifest_sha256=sha(sampling),wheel_sha256=config['wheel_sha256'],
        original_results_rewards_and_recorders_unmodified=True,formal801_excluded=True,
        old_r4_diagnostics_excluded=True,no_best_attempt_or_checkpoint_selection=True,
        source_sha256=sha(Path(__file__)),actual_model_or_task_calls=0)
    save(E/'checks/DIAGNOSTIC30_MATRIX_R1.json',value)
    lines=['# 30题、四组Checkpoint诊断','',
        '同一份30题覆盖NEW-M1 Epoch3/Epoch5、NEW-M2 Epoch1/Epoch3，每组每题一次。原9题保留、按公开类别及seed42补21题，不读取模型成绩选题。正式89题×3模型×3次的801项单独统计。','',
        '| 模型 | 逻辑终态/30 | 原生Result | 原始评分覆盖 | 协议及Recorder覆盖 | 确认成功 |','|---|---:|---:|---:|---:|---:|']
    for tag,s in stats.items():
        lines.append(f"| {tag} | {s['terminal']}/30 | {s['native_results']} | {s['raw_official_scoring_coverage']:.2%} | {s['coverage']:.2%} | {s['confirmed_reward_successes']} |")
    lines+=['','原M1 Epoch3两条控制器OOM缺原生Result继续作为显式UNKNOWN，未补造Reward或重跑。待运行记录不当作模型零分；未完成时确认成功率只是固定分母下界。四个Checkpoint不代表相同训练剂量，不据此选择正式主模型。',
        '',f'采样Manifest SHA：`{sha(sampling)}`；120身份计划SHA：`{sha(plan_path)}`；派生行SHA：`{sha(cache_path)}`。']
    (E/'reports/DIAGNOSTIC30_COMPARISON.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(expected=120,logical_terminal=len(rows),pending=len(pending),complete=value['complete'],actual_model_calls=0)))


if __name__=='__main__':main()
