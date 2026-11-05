"""Read-only operational behavior statistics on original native Recorder data."""
from collections import Counter
import hashlib
import json
from pathlib import Path
from foundation.rollouts.export import RolloutView,loadValue


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def analyze_behavior(directory):
    directory=Path(directory);root=directory/'agent/openharness-rollout'
    view=RolloutView.open(root)
    def resolve(value):
        if isinstance(value,list):return[resolve(v)for v in value]
        if isinstance(value,dict):
            if value.get('kind')in('inline','artifact'):return resolve(loadValue(value,root/'artifacts'))
            return{k:resolve(v)for k,v in value.items()}
        return value
    calls,tools,runs,contexts=view.rows()
    agent=[c for c in calls if c.get('source')=='agent']
    observations={};all_blocks=0;repeated_blocks=0;thinking_chars=0;max_thinking=0
    stops=Counter();body_transition=0;reasoning_only_length=0
    for call in agent:
        payload=resolve(call.get('payload'))or{}
        for message in payload.get('messages',[]):
            if message.get('role')=='tool':observations.setdefault(message['tool_call_id'],message.get('content'))
        response=resolve(call.get('response'))or{};parts=response.get('content')or[]
        thinking=''.join(p.get('thinking','')for p in parts if p.get('type')=='thinking')
        blocks=[thinking[i:i+128]for i in range(0,len(thinking)-127,128)]
        all_blocks+=len(blocks);repeated_blocks+=len(blocks)-len(set(blocks))
        thinking_chars+=len(thinking);max_thinking=max(max_thinking,len(thinking))
        reason=response.get('stopReason','missing');stops[reason]+=1
        transitioned=any(p.get('type')=='toolCall'or(p.get('type')=='text'and p.get('text'))for p in parts)
        body_transition+=bool(thinking and transitioned)
        reasoning_only_length+=bool(thinking and not transitioned and reason=='length')
    previous=None;repeats=0;run_length=0;max_run=0;missing=0;failures=[];finish=[]
    ordered=sorted(tools,key=lambda x:(x.get('started_at')or 0,x.get('tool_call_id','')))
    for tool in ordered:
        ident=tool.get('tool_call_id');visible=observations.get(ident)
        if ident in observations:
            signature=digest([tool['name'],resolve(tool.get('original_args')),visible])
            if signature==previous:repeats+=1;run_length+=1
            else:run_length=1
            previous=signature;max_run=max(max_run,run_length)
        else:previous=None;run_length=0;missing+=1
        raw=resolve(tool.get('raw_result'))or{} if tool['name']in('bash','bash_job','finish')else{}
        exit_code=raw.get('exitCode')if isinstance(raw,dict)else None
        failed=tool.get('is_error')or tool.get('status')in('error','aborted')or(isinstance(exit_code,int)and exit_code!=0)
        if failed:failures.append(dict(tool_call_id=ident,name=tool['name'],started_at=tool.get('started_at'),
            original_args_sha256=digest(resolve(tool.get('original_args')))))
        if tool['name']=='finish':finish.append(dict(tool_call_id=ident,executed=tool.get('executed'),
            finish_requested=bool(raw.get('finishRequested'))if isinstance(raw,dict)else False,is_error=bool(failed)))
    first=failures[0]if failures else None
    after=sum(c.get('started_at',0)>(first['started_at']or 0)for c in agent)if first else None
    return dict(agent_model_calls=len(agent),model_stop_reasons=dict(stops),thinking_characters=thinking_chars,
        longest_single_call_thinking_characters=max_thinking,thinking_complete_128_character_blocks=all_blocks,
        thinking_repeated_128_character_blocks=repeated_blocks,
        thinking_repeated_block_fraction=repeated_blocks/all_blocks if all_blocks else None,
        thinking_to_body_or_tool_transition_calls=body_transition,reasoning_only_length_calls=reasoning_only_length,
        literal_think_close_tags_not_observable_after_native_reasoning_parser=True,
        tool_calls=len(tools),tool_failures=len(failures),finish_calls=finish,
        exact_consecutive_tool_repeats_with_same_visible_observation=repeats,
        longest_identical_tool_and_observation_run=max_run,tool_calls_without_later_visible_observation=missing,
        first_tool_error=first,agent_decisions_after_first_tool_error=after,
        repetition_statistics_do_not_establish_semantic_task_nonprogress=True,
        recorder_integrity=view.validate(),raw_recorder_modified=False,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
