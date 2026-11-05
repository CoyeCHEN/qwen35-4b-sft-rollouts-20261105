"""Fixed-denominator comparison from unchanged native Results/Recorder; no dispatch."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
from audit_trial_behavior_new772_r3 import analyze_behavior
from importlib import import_module
inspect_trial=import_module('audit-native-context-accounting-r2').inspect_trial

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
J=R/'jobs/qwen35-new772-tb21-n3'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def aggregate(rows,denominator):
    admitted=lambda x:x['valid_score']and not x['protocol_issues']and not x.get('audit_error')
    confirmed=lambda x:admitted(x)and(x['reward']or{}).get('reward')==1
    ok=sum(confirmed(r)for r in rows);valid=sum(admitted(r)for r in rows)
    blocks=sum((r.get('behavior')or{}).get('thinking_complete_128_character_blocks',0)for r in rows)
    repeated=sum((r.get('behavior')or{}).get('thinking_repeated_128_character_blocks',0)for r in rows)
    return dict(expected_trials=denominator,terminal=len(rows),pending=denominator-len(rows),
        confirmed_reward_successes=ok,normal_complete_successes=sum(confirmed(r)and r['trajectory_complete']for r in rows),
        raw_official_reward_successes=sum(r['raw_official_score_valid']and(r['reward']or{}).get('reward')==1 for r in rows),
        abnormal_reward_successes=sum(confirmed(r)and not r['trajectory_complete']for r in rows),
        timeout_reward_successes=sum(confirmed(r)and r['exception_type']=='AgentTimeoutError'for r in rows),
        scoring_and_protocol_valid=valid,unknown=len(rows)-valid,coverage=valid/denominator,
        raw_official_scoring_coverage=sum(r['raw_official_score_valid']for r in rows)/denominator,
        recorder_audit_failures=sum(bool(r.get('audit_error'))for r in rows),
        confirmed_mean_single_trial_success_fixed_denominator=ok/denominator,
        rate_is_lower_bound_until_unknown_and_pending_resolved=valid<denominator,
        normal_complete_success_fixed_denominator=sum(confirmed(r)and r['trajectory_complete']for r in rows)/denominator,
        normal_closed=sum(r['normal_close']for r in rows),agent_timeouts=sum(r['exception_type']=='AgentTimeoutError'for r in rows),
        nonzero_cli_exit=sum(r.get('cli_exit_code')not in(None,0)for r in rows),
        schema_argument_errors=sum(r['tool_argument_invalid']for r in rows),
        length_calls=sum((r.get('model_stop_reasons')or{}).get('length',0)for r in rows),
        thinking_repeated_block_fraction=repeated/blocks if blocks else None,
        thinking_measured_complete_blocks=blocks,thinking_repeated_blocks=repeated,
        finish_calls=sum(len((r.get('behavior')or{}).get('finish_calls',[]))for r in rows),
        finish_requests_accepted=sum(sum(x['finish_requested']for x in(r.get('behavior')or{}).get('finish_calls',[]))for r in rows),
        exact_tool_and_observation_repeats=sum((r.get('behavior')or{}).get('exact_consecutive_tool_repeats_with_same_visible_observation',0)for r in rows),
        infrastructure_failures=sum(bool(r['infrastructure_errors'])for r in rows),
        protocol_failures=sum(bool(r['protocol_issues'])for r in rows),
        context_recovery_terminations=sum(r.get('fatal_context_overflow',False)for r in rows),
        recorder_usage_all_calls={k:sum((r.get('recorder_usage_all_calls')or{}).get(k,0)for r in rows)for k in ('input','output','reasoning','totalTokens')},
        behavior_audit_failures=sum('behavior_audit_error'in r for r in rows))


def main():
    plan_path=R/'manifests/FORMAL_801_TRIAL_PLAN.json';plan=json.loads(plan_path.read_text())
    expected={x['trial_name']:x for x in plan['trials']};assert len(expected)==801
    if not J.exists():print(json.dumps(dict(status='NOT_STARTED',formal_trials=0,expected=801)));return
    cache_path=R/'checks/FORMAL_801_FULL_BEHAVIOR_ROWS_R6.jsonl'
    cached={r['trial_name']:r for r in(json.loads(line)for line in cache_path.open())}if cache_path.exists()else{}
    rows=[];uuids=set()
    for p in sorted(J.glob('*/result.json')):
        row=cached.get(p.parent.name)
        if row:assert row['result_sha256']==sha(p),'Preserve changed source evidence for inspection'
        else:
            row=inspect_trial(p.parent)
            try:row['behavior']=analyze_behavior(p.parent)
            except Exception as e:row['behavior_audit_error']=repr(e)
        identity=expected[row['trial_name']]
        assert row['trial_id']not in uuids;uuids.add(row['trial_id'])
        row.update(model_name=identity['model_name'],repetition=identity['repetition'])
        rows.append(row)
    models={};names=['openai/qwen35-new772-'+x for x in ['m0','new-m1-e5','new-m2-e5']]
    for name in names:
        selected=[r for r in rows if r['model_name']==name];stats=aggregate(selected,267)
        stats['rounds']={str(i):aggregate([r for r in selected if r['repetition']==i],89)for i in [1,2,3]}
        stats['at_least_once_confirmed_task_fraction']=len({r['task_id']for r in selected if r['valid_score']and not r['protocol_issues']and not r.get('audit_error')and(r['reward']or{}).get('reward')==1})/89
        models[name]=stats
    tasks={}
    for item in plan['trials']:tasks.setdefault(item['task_id'],{})
    for task in tasks:
        for model in names:
            rs=sorted((r for r in rows if r['task_id']==task and r['model_name']==model),key=lambda r:r['repetition'])
            tasks[task][model]=dict(trials=[dict(repetition=r['repetition'],trial_id=r['trial_id'],reward=r['reward'],
                score_valid=r['valid_score']and not r['protocol_issues']and not r.get('audit_error'),normal_complete=r['trajectory_complete'])for r in rs])
    changes={}
    for before,after in zip(names,names[1:]):
        groups={k:[]for k in ['gained_any_success','lost_all_success','higher_success_count','lower_success_count','unknown_comparison']}
        for task,values in tasks.items():
            a=values[before]['trials'];b=values[after]['trials']
            if len(a)!=3 or len(b)!=3 or any(not x['score_valid']for x in a+b):
                groups['unknown_comparison'].append(task);continue
            ca=sum((x['reward']or{}).get('reward')==1 for x in a);cb=sum((x['reward']or{}).get('reward')==1 for x in b)
            if ca==0 and cb>0:groups['gained_any_success'].append(task)
            if ca>0 and cb==0:groups['lost_all_success'].append(task)
            if cb>ca:groups['higher_success_count'].append(task)
            if cb<ca:groups['lower_success_count'].append(task)
        changes[before+' -> '+after]=groups
    result=dict(kind='TB21_89_THREE_MODELS_THREE_INDEPENDENT_TRIALS',formal_801_plan_sha256=sha(plan_path),
        metric_spec_sha256=sha(R/'manifests/METRIC_SPECIFICATIONS_R1.json'),terminal=len(rows),expected=801,
        complete=len(rows)==801,models=models,per_task=tasks,per_task_model_changes=changes,
        raw_results_or_recorders_modified=False,unknown_not_recoded_as_reward0=True,
        seeds_not_claimed_strictly_paired=True,epoch3_diagnostics_excluded=True,
        formal_harness_deployment_sha256=sha(R/'checks/FORMAL801_WHEEL_ONLY_DEPLOYMENT_R2.json'),
        context_overflow_failures_separate_from_raw_official_reward=True,
        source_sha256=sha(Path(__file__)))
    tmp=cache_path.with_name(cache_path.name+'.tmp');tmp.write_text(''.join(json.dumps(r)+'\n'for r in rows));tmp.replace(cache_path)
    path=R/'checks/TB21_N3_FULL_COMPARISON.json';tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(result,indent=2)+'\n');tmp.replace(path)
    report_dir=R/'reports';report_dir.mkdir(exist_ok=True)
    lines=['# TB2.1 n=3 统一比较','',f'状态：{len(rows)}/801正式Trial终态。Epoch3诊断与本表分开。','',
      '| 模型 | 已确认Reward成功/267 | 平均单次确认成功率 | 正常完整成功/267 | 有效评分覆盖 | UNKNOWN | 至少一次成功任务比例 |',
      '|---|---:|---:|---:|---:|---:|---:|']
    for name in names:
        v=models[name]
        lines.append(f"| {name} | {v['confirmed_reward_successes']}/267 | {v['confirmed_mean_single_trial_success_fixed_denominator']:.4%} | {v['normal_complete_successes']}/267 | {v['coverage']:.4%} | {v['unknown']} | {v['at_least_once_confirmed_task_fraction']:.4%} |")
    lines+=['','存在UNKNOWN或待完成项时，固定分母成功率为已确认下界；未把UNKNOWN改成普通零分。至少一次成功比例不等于平均pass1。超时但Reward1与正常完整成功分列。','',
      '三轮逐次89题成绩、工具/Thinking/Finish与逐题得失见TB21_N3_FULL_COMPARISON.json及原始Result/Recorder。三次为独立Trial，不声称严格配对Seed。','',
      f"比较JSON SHA：`{sha(path)}`；固定Trial计划SHA：`{sha(plan_path)}`。Epoch5预先指定，未按结果挑Checkpoint或增训。"]
    (report_dir/'TB21_N3_COMPARISON.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(complete=result['complete'],terminal=len(rows),models=models)))


if __name__=='__main__':main()
