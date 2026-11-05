"""Rehash the 267 fixed results, inspect lost tasks and success controls.

Read-only, one worker. No benchmark, API, container or model execution.
"""
from collections import Counter, defaultdict
import csv
import datetime
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys
import time
import tomllib

BASE=Path('/home/chenkeyi/.local/share/harbor-rsi')
ROOT=BASE/'qwen35-new-cf500-tmax500-20261029'
OLD=BASE/'qwen35-m1-m2-tb21-20261026'
SEALED=BASE/'qwen35-m0-baseline-tb21-20261026/evidence/first-round-m0-m1-m2-comparison.json'
WHEEL=OLD/'wheels/null-delta/open_harness_ai-0.3.0-py3-none-any.whl'
assert hashlib.sha256(WHEEL.read_bytes()).hexdigest()=='f84f810e8a61545d685fb6722593886a0c88cc829b2ab9ca7c3476fe11e1209e'
sys.path.insert(0,str(WHEEL))
from foundation.rollouts.export import loadValue


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def safe(value):
    text=str(value)
    text=re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9_.-]+',r'\1[REDACTED]',text)
    text=re.sub(r'\b(?:sk-|gh[pousr]_|github_pat_|hf_)[A-Za-z0-9_-]{20,}','[REDACTED]',text)
    text=re.sub(r'(?i)((?:api[_-]?key|password|secret|access[_-]?token)\s*[=:]\s*)[^\s,;]+',r'\1[REDACTED]',text)
    return text[:600]


def seconds(span):
    try:
        return (datetime.datetime.fromisoformat(span['finished_at'].replace('Z','+00:00'))-
                datetime.datetime.fromisoformat(span['started_at'].replace('Z','+00:00'))).total_seconds()
    except (KeyError,ValueError,TypeError):return None


def text(value):
    if isinstance(value,str):return value
    if isinstance(value,list):return '\n'.join(str(x.get('text',''))for x in value if isinstance(x,dict)and x.get('type')=='text')
    if isinstance(value,dict):return text(value.get('content',value.get('tail',value.get('text',''))))
    return ''


sealed=json.loads(SEALED.read_text());models={};resources=[];all_results=[]
for model in ('m0','m1','m2'):
    frozen=sealed['models'][model];audit=Path(frozen['audit_path'])
    assert hashlib.sha256(audit.read_bytes()).hexdigest()==frozen['audit_sha256']
    index={x['trial_id']:x for x in map(json.loads,audit.open())};rows={}
    for entry in frozen['trials']:
        file=Path(entry['result_path']);raw=json.loads(file.read_text());old=index[raw['id']]
        assert hashlib.sha256(file.read_bytes()).hexdigest()==entry['result_sha256']==old['result_sha256']
        task=raw['task_name'];rows[task]=(old,raw,file.parent)
        config=json.loads((file.parent/'config.json').read_text());task_dir=Path(config['task']['path'])
        spec=tomllib.loads((task_dir/'task.toml').read_text())
        agent=config.get('agent',{});verifier=config.get('verifier',{})
        compose=[]
        for cp in file.parent.glob('*.compose.json'):
            value=json.loads(cp.read_text())
            for name,service in value.get('services',{}).items():
                compose.append(dict(service=name,cpus=service.get('cpus'),mem_limit=service.get('mem_limit'),
                    deploy_limits=service.get('deploy',{}).get('resources',{}).get('limits'),
                    compose_path=str(cp),compose_sha256=hashlib.sha256(cp.read_bytes()).hexdigest()))
        resources.append(dict(model=model,task_id=task,trial_id=raw['id'],result_path=str(file),result_sha256=entry['result_sha256'],
            task_config_path=str(task_dir/'task.toml'),task_config_sha256=hashlib.sha256((task_dir/'task.toml').read_bytes()).hexdigest(),
            task_agent_timeout=spec.get('agent',{}).get('timeout_sec'),agent_override=agent.get('override_timeout_sec'),
            task_verifier_timeout=spec.get('verifier',{}).get('timeout_sec'),verifier_override=verifier.get('override_timeout_sec'),
            task_environment=spec.get('environment',{}),recorded_compose=compose,
            agent_execution_seconds=seconds(raw.get('agent_execution')or{}),
            setup_seconds=seconds(raw.get('environment_setup')or{}),
            exception=(raw.get('exception_info')or{}).get('exception_type'),
            historical_actual_cgroup='UNKNOWN_NOT_PRESERVED_OR_CONTAINER_ALREADY_REMOVED',
            model_gpu_memory='Separate serving allocation; not sandbox memory'))
        all_results.append(raw['id'])
    assert len(rows)==89;models[model]=rows
assert len(all_results)==len(set(all_results))==267
lost=sorted(t for t,(row,_,_)in models['m1'].items()if row['task_success']and not models['m2'][t][0]['task_success'])
assert len(lost)==12
controls=sorted(t for t,(row,_,_)in models['m2'].items()if row['task_success'])
assert len(controls)==3
(ROOT/'checks/frozen-267-resource-audit.json').write_text(json.dumps(dict(
    source_manifest=str(SEALED),source_manifest_sha256=hashlib.sha256(SEALED.read_bytes()).hexdigest(),
    results_rehashed=267,successes={m:sum(r[0]['task_success']for r in rows.values())for m,rows in models.items()},
    rows=resources),indent=2))

cases=[];parameter_values=defaultdict(Counter);start=time.monotonic()
for task in sorted(set(lost+controls)):
    for model in ('m0','m1','m2'):
        row,raw,directory=models[model][task];root=directory/'agent/openharness-rollout';file=root/'events.jsonl'
        calls={};executions={};tool_order=[];previous_observations={};context_events=[];user_notices=Counter()
        events_sha=hashlib.sha256()
        with file.open('rb') as stream:
            for number,line in enumerate(stream,1):
                events_sha.update(line)
                event=json.loads(line);kind=event.get('type');data=event.get('data')or{};when=event.get('timestamp')
                ident=data.get('call_id');entry=calls.setdefault(ident,dict(call_id=ident))if ident else None
                if kind=='call_start':entry.update(started_at=when,source=data.get('source'),line=number)
                elif kind=='call_payload':
                    payload=loadValue(data.get('payload'),root/'artifacts')
                    if not isinstance(payload,dict):continue
                    messages=payload.get('messages',[]);roles=Counter(m.get('role')for m in messages)
                    thinking=sum(bool(m.get('reasoning_content'))for m in messages if m.get('role')=='assistant')
                    entry.update(payload_line=number,payload_sha256=digest(payload),roles=dict(roles),historical_thinking_messages=thinking,
                        input_images=sum(isinstance(m.get('content'),list)and any(p.get('type')in('image_url','image')for p in m['content'])for m in messages))
                    for parameter in ['model','temperature','top_p','top_k','min_p','presence_penalty','frequency_penalty','repetition_penalty','stop','ignore_eos','max_tokens','chat_template_kwargs']:
                        parameter_values[parameter][json.dumps(payload.get(parameter,'NOT_SENT'),sort_keys=True)]+=1
                    # Distinguish exact user tool-response wrappers from new user turns.
                    genuine=[m for m in messages if m.get('role')=='user'and not(text(m.get('content')).startswith('<tool_response>')and text(m.get('content')).rstrip().endswith('</tool_response>'))]
                    if genuine:
                        latest=text(genuine[-1].get('content'))
                        if re.search(r'(?i)background|后台|job.*(?:completed|finished)',latest):user_notices['background_last_user_payloads']+=1
                        if re.search(r'(?i)compact|summary|summarized',latest):user_notices['compaction_or_summary_last_user_payloads']+=1
                    for message in messages[-8:]:
                        if message.get('role')!='tool':continue
                        tool_id=message.get('tool_call_id');visible=text(message.get('content'))
                        previous_observations[tool_id]=dict(content_sha256=hashlib.sha256(visible.encode()).hexdigest(),
                            visible_excerpt=safe(visible),visible_chars=len(visible),next_payload_call_id=ident,next_payload_line=number)
                elif kind=='call_end':
                    response=loadValue(data.get('response'),root/'artifacts');response=response if isinstance(response,dict)else{}
                    blocks=response.get('content')or[];thought='\n'.join(str(b.get('thinking',''))for b in blocks if b.get('type')=='thinking')
                    entry.update(ended_at=when,status=data.get('status'),stop_reason=response.get('stopReason'),usage=response.get('usage'),
                        response_line=number,thinking_only=bool(thought)and all(b.get('type')=='thinking'for b in blocks),
                        thinking_excerpt=safe(thought[:200]),body_excerpt=safe(text(blocks)),
                        tool_calls=sum(b.get('type')=='toolCall'for b in blocks))
                elif kind=='tool_start':
                    key=data['execution_id'];args=loadValue(data.get('original_args',data.get('args')),root/'artifacts')
                    executions[key]=dict(execution_id=key,call_id=ident,tool_call_id=data.get('tool_call_id'),name=data.get('name'),
                        started_at=when,line=number,arguments_sha256=digest(args),arguments_excerpt=safe(json.dumps(args,ensure_ascii=False)))
                    tool_order.append(key)
                elif kind in ('tool_raw','tool_end'):
                    target=executions.get(data.get('execution_id'))
                    if target is None:continue
                    value=loadValue(data.get('result'),root/'artifacts')
                    if kind=='tool_raw':
                        target.update(raw_result_sha256=digest(value),raw_excerpt=safe(text(value)),
                            raw_exit_code=value.get('exitCode')if isinstance(value,dict)else None,
                            raw_total_bytes=value.get('totalBytes')if isinstance(value,dict)else None)
                    else:target.update(ended_at=when,end_line=number,status=data.get('status'),is_error=data.get('is_error'),
                        rendered_result_sha256=digest(value),rendered_excerpt=safe(text(value)))
                elif kind=='context_event':context_events.append(dict(line=number,keys=sorted(data),kind=data.get('kind',data.get('event'))))
        assert events_sha.hexdigest()==row['events_sha256'], 'Original event journal identity changed'
        tools=[];runs=[];current=None
        for ordinal,key in enumerate(tool_order,1):
            item=executions[key];item.update(ordinal=ordinal,visible=previous_observations.get(item.get('tool_call_id')))
            visible=item.get('visible')or{};signature=(item.get('name'),item['arguments_sha256'],visible.get('content_sha256'))
            if current is None or signature!=current['signature']:
                if current:runs.append(current)
                current=dict(signature=signature,count=0,first_ordinal=ordinal,start_line=item['line'],last_ordinal=ordinal)
            current['count']+=1;current['last_ordinal']=ordinal;tools.append(item)
        if current:runs.append(current)
        repeats=[{k:v for k,v in run.items()if k!='signature'}for run in runs if run['count']>=3]
        bad_commands=[x for x in tools if x.get('is_error')or x.get('raw_exit_code')not in(None,0)]
        length=[x for x in calls.values()if x.get('status')=='length'or x.get('stop_reason')=='length']
        durations=[x['ended_at']-x['started_at']for x in calls.values()if isinstance(x.get('ended_at'),(int,float))and isinstance(x.get('started_at'),(int,float))]
        case=dict(model=model,task_id=task,trial_id=row['trial_id'],control=task in controls,
            source_events=str(file),events_sha256=events_sha.hexdigest(),result_path=str(directory/'result.json'),result_sha256=row['result_sha256'],
            success=row['task_success'],exception=row.get('exception_type'),normal_close=row.get('normal_close'),
            calls=list(calls.values()),tools=tools,consecutive_same_action_and_observation_runs=repeats,
            first_command_error=bad_commands[0]if bad_commands else None,first_length=length[0]if length else None,
            model_call_seconds=dict(count=len(durations),sum=sum(durations),median=statistics.median(durations)if durations else None,
                max=max(durations)if durations else None,queue_vs_generation='UNKNOWN_NOT_SEPARATELY_RECORDED'),
            context_events=context_events,user_notice_payload_counts=dict(user_notices),
            repeated_action_interpretation='Same visible observation is not proof of a deadlock; inspect background state and real side effects',
            counts=dict(model_calls=len(calls),tool_executions=len(tools),command_errors=len(bad_commands),length_calls=len(length)))
        cases.append(case)
        out=ROOT/'stage1'/('case-'+model+'-'+task.rsplit('/',1)[-1]+'.private.json')
        out.write_text(json.dumps(case,indent=2));out.chmod(0o600)
        print(json.dumps(dict(event='case_complete',model=model,task=task,**case['counts'],seconds=time.monotonic()-start)),flush=True)

rows=[]
for task in lost:
    case=next(x for x in cases if x['model']=='m2'and x['task_id']==task)
    if case['first_length']:
        point=case['first_length'];kind='MODEL_OUTPUT_LIMIT';line=point['response_line'];call=point['call_id']
    elif case['consecutive_same_action_and_observation_runs']:
        point=case['consecutive_same_action_and_observation_runs'][0];kind='REPEATED_ACTION_UNCHANGED_VISIBLE_OBSERVATION_REQUIRES_PROGRESS_REVIEW';line=point['start_line'];call=None
    elif case['first_command_error']:
        point=case['first_command_error'];kind='FIRST_COMMAND_ERROR_NOT_AUTOMATICALLY_ROOT_CAUSE';line=point['line'];call=point['call_id']
    else:kind='NO_AUTOMATIC_LOCALIZATION_MANUAL_VERIFIER_AND_ACTION_REVIEW_REQUIRED';line=None;call=None
    rows.append(dict(task_id=task,m1_success=True,m2_success=False,first_observed_anomaly=kind,
        call_id=call,event_line=line,final_exception=case['exception'],normal_close=case['normal_close'],
        model_calls=case['counts']['model_calls'],tool_executions=case['counts']['tool_executions'],
        evidence_file='stage1/case-m2-'+task.rsplit('/',1)[-1]+'.private.json',raw_events=case['source_events'],
        causal_root='UNRESOLVED_UNLESS_SUPPORTED_BY_MANUAL_REVIEW'))
with(ROOT/'stage1/FAILED_TASKS.csv').open('x')as stream:
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
summary=dict(passed=True,raw_results_rehashed=267,lost_tasks=lost,success_controls=controls,cases_read=len(cases),
    payload_parameter_values={k:dict(v)for k,v in parameter_values.items()},source_modified=False,
    new_benchmark_trials=0,new_model_requests=0,seconds=time.monotonic()-start,
    scope='Observed anomaly index plus original-resource evidence; manual causal assessment remains separate')
(ROOT/'checks/trajectory-case-audit.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
