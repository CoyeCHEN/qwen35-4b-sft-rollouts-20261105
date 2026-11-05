"""Readonly9-task E3n1 versus all3 E5 trials; no model/recipe selection."""
import hashlib
import importlib
import json
from pathlib import Path
import time
from eval_audit_new772 import inspect_trial
from audit_trial_behavior_new772_r3 import analyze_behavior

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
aggregate=importlib.import_module('compare-formal801-readonly-r4').aggregate
EXPECTED_PREREG='472afd0e83e7bbcf748f8d5c5e6a04494774b45aea44052cef11bf03f0bc0434'
EXPECTED_FORMAL='ca38c348707a111d7583114c4f222102194e46fb6343ebe16024d7079fab4b16'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def save(p,v):
    tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)


def main():
    prereg=R/'manifests/EPOCH3_DIAGNOSTIC_PREREGISTRATION.json';formal=R/'manifests/FORMAL_801_TRIAL_PLAN.json'
    if sha(prereg)!=EXPECTED_PREREG or sha(formal)!=EXPECTED_FORMAL:raise ValueError('Preregistered comparison membership changed')
    tasks=read(prereg)['tasks'];plan=read(formal)['trials']
    if len(tasks)!=9 or len(set(tasks))!=9:raise ValueError('Expected exactly9 preregistered diagnostic tasks')
    source_identity={n:sha(R/'scripts'/n)for n in ['eval_audit_new772.py','audit_trial_behavior_new772_r3.py','compare-formal801-readonly-r4.py']}
    cache=R/'checks/EPOCH3_VS_EPOCH5_ROWS_R1.jsonl'
    existing={r['trial_path']:r for r in(json.loads(line)for line in cache.open())}if cache.exists()else{}
    rows=[];comparisons={};identities=set()
    for stage in ['new-m1','new-m2']:
        wanted={x['trial_name']:x for x in plan if x['task_id']in tasks and x['model_name']=='openai/qwen35-new772-'+stage+'-e5'}
        if len(wanted)!=27:raise ValueError('Use all3 E5 trials on all9 tasks; no best-trial selection')
        e3_job=R/'jobs'/('qwen35-new772-'+stage+'-epoch3-diagnostic')
        e3_wanted={t+'__'+stage+'-e3-r1':dict(task_id=t,repetition=1)for t in tasks}
        groups={3:[],5:[]}
        for epoch,job,scope in [(3,e3_job,e3_wanted),(5,R/'jobs/qwen35-new772-tb21-n3',wanted)]:
            for name,identity in scope.items():
                directory=job/name;result=directory/'result.json'
                if not result.exists():continue
                key=str(directory);row=existing.get(key)
                if row:
                    if row['result_sha256']!=sha(result)or row['comparison_audit_sources']!=source_identity:
                        raise ValueError('Preserve changed Results or old analysis source; create a new derived version')
                else:
                    row=inspect_trial(directory)
                    try:row['behavior']=analyze_behavior(directory)
                    except Exception as error:row['behavior_audit_error']=repr(error)
                    row.update(trial_path=key,comparison_audit_sources=source_identity,stage=stage,epoch=epoch,
                        repetition=identity['repetition'])
                if row['task_id']!=identity['task_id']or row['trial_id']in identities:raise ValueError('Comparison Task/Trial identity differs')
                identities.add(row['trial_id']);rows.append(row);groups[epoch].append(row)
        e3=aggregate(groups[3],9);e5=aggregate(groups[5],27)
        comparisons[stage]=dict(epoch3_n1=e3,epoch5_all3_trials=e5,
            epoch5_rounds={str(i):aggregate([x for x in groups[5]if x['repetition']==i],9)for i in (1,2,3)},
            complete=e3['terminal']==9 and e5['terminal']==27,
            per_task={task:{'epoch'+str(epoch):[dict(trial_id=x['trial_id'],repetition=x['repetition'],reward=x['reward'],
                official_score_valid=x['raw_official_score_valid'],protocol_valid=x['valid_score']and not x['protocol_issues']and not x.get('audit_error'),
                normal_complete=x['trajectory_complete'],timeout=x['exception_type']=='AgentTimeoutError',
                length_calls=(x.get('model_stop_reasons')or{}).get('length',0))for x in groups[epoch]if x['task_id']==task]
                for epoch in (3,5)}for task in tasks})
    temp=cache.with_name(cache.name+'.tmp');temp.write_text(''.join(json.dumps(x)+'\n'for x in rows));temp.replace(cache)
    result=dict(checked_at=time.time(),preregistration_sha256=sha(prereg),formal_plan_sha256=sha(formal),
        complete=all(x['complete']for x in comparisons.values()),models=comparisons,
        different_doses_and_denominators=True,epoch5_preselected=True,paired_seed_claimed=False,
        all3_epoch5_trials_used=True,no_additional_trials_dispatched=True,raw_evidence_unchanged=True,
        rows_sha256=sha(cache),audit_sources=source_identity,source_sha256=sha(Path(__file__)))
    path=R/'checks/EPOCH3_VS_EPOCH5_COMPARISON_R1.json';save(path,result)
    lines=['# Epoch3 / Epoch5 预登记9题比较','',
        'E3每题一次，E5使用正式n=3中同9题的全部三次；两组训练剂量、样本量不同，不声称配对Seed。Epoch5预先指定，不据此选Checkpoint或改配方。','',
        '| 模型 | 阶段 | 终态/分母 | 已确认Reward成功 | 固定分母成功率 | 评分及协议覆盖 | 正常完整成功 | Timeout | length调用 | Thinking重复块比例 |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for stage,values in comparisons.items():
        for label,key,den in [('E3 n1','epoch3_n1',9),('E5 n3','epoch5_all3_trials',27)]:
            v=values[key];rate=f"{v['confirmed_mean_single_trial_success_fixed_denominator']:.2%}"if v['terminal']else'待执行'
            repetition=v['thinking_repeated_block_fraction'];repetition='暂无可测记录'if repetition is None else f'{repetition:.2%}'
            lines.append(f"| {stage} | {label} | {v['terminal']}/{den} | {v['confirmed_reward_successes']} | {rate} | {v['coverage']:.2%} | {v['normal_complete_successes']} | {v['agent_timeouts']} | {v['length_calls']} | {repetition} |")
    lines+=['','UNKNOWN保留；结果未齐时固定分母确认率为下界，0条终态不当作模型零分。Thinking重复为预登记的单次调用内128字符块统计，工具重复同样只是观察代理，不证明语义上无进展。',
        '',f'完整比较JSON SHA：`{sha(path)}`；派生行SHA：`{sha(cache)}`。']
    (R/'reports').mkdir(exist_ok=True)
    (R/'reports/EPOCH3_VS_EPOCH5_DIAGNOSTIC.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(complete=result['complete'],terminal_comparison_rows=len(rows),expected_rows=72,actual_new_trials=0)))


if __name__=='__main__':main()
