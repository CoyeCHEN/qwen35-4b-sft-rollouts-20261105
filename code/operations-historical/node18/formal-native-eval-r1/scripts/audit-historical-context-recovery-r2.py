"""Read-only completed E3 Recorder audit and bounded inputs for token investigation."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import time

from foundation.ai.utils.errors import isContextOverflow
from foundation.persistence.manager import SessionManager
from foundation.rollouts.export import RolloutView, loadValue
from rsi_modules.memory.history import contextItems, estimateSessionContext
from rsi_modules.memory.context import estimateContextTokens, estimateTokens

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def historical_estimate(directory, call, native):
    ids=[x['message_id'] for x in call['input_origins']]
    for path in (directory/'agent/openharness-sessions').rglob('*.jsonl'):
        raw=[json.loads(line) for line in path.open()]
        known={e['id'] for e in raw}
        if not all(i in known for i in ids):continue
        entries=[e for e in raw if e['timestamp']<=call['started_at']*1000]
        manager=SessionManager()  # In-memory replay only; never open() or repair the source.
        for entry in entries:
            item=copy.deepcopy(entry)
            manager._entries.append(item)
            manager._accept(item)
        branch=manager.getBranch(ids[-1])
        items=contextItems(branch,entries)
        assert [i for i,_ in items]==ids
        original=[m for _,m in items]
        effective=native['messages']
        assert len(original)==len(effective)
        differences=[]
        for index,(before,after) in enumerate(zip(original,effective)):
            if before!=after:
                assert before['role']==after['role']=='toolResult'
                differences.append(dict(index=index,message_id=ids[index],
                    tool_name=after.get('toolName'),raw_characters=len(json.dumps(before)),
                    visible_characters=len(json.dumps(after))))
        if differences:
            cleared=copy.deepcopy(effective)
            for message in cleared:
                if message['role']=='assistant':message['usage']={}
            estimated=estimateContextTokens(cleared)
            policy='Projected tool results differ: all assistant usage anchors cleared; chars/4 fallback'
        else:
            estimated=estimateSessionContext(branch,entries)
            policy='Native branch history usage anchor plus estimated trailing messages'
        return dict(session_path=str(path),session_sha256=sha(path),policy=policy,
            exact_native_history_projection_reconciled=True,session_timestamps_are_milliseconds=True,
            projection_changes=differences,
            actual_trigger_estimate=estimated,
            raw_context_anchor_estimate=estimateSessionContext(branch,entries),
            visible_messages_chars4_without_usage=sum(estimateTokens(m)for m in effective),
            system_not_explicitly_counted_by_trigger=bool(native.get('systemPrompt')),
            system_characters=len(native.get('systemPrompt','')),
            tool_schema_not_explicitly_counted_by_trigger=bool(native.get('tools')),tool_count=len(native.get('tools',[])),
            system_and_schema_missing_from_no_anchor_fallback=estimated['usageTokens']==0,
            thinking_blocks=sum(b.get('type')=='thinking' for m in effective for b in m.get('content',[])if isinstance(b,dict)),
            native_image_blocks=sum(b.get('type')=='image' for m in effective for b in m.get('content',[])if isinstance(b,dict)))
    raise ValueError('No immutable Session contains all actual input origins')


def main():
    output=R/'checks/context-recovery-history-r2'
    output.mkdir(exist_ok=True)
    trials=[];estimates=[]
    for job in sorted((R/'jobs').glob('qwen35-new772-*-epoch3-diagnostic')):
        for result_path in sorted(job.glob('*/result.json')):
            directory=result_path.parent
            source_before=sha(result_path)
            result=json.loads(result_path.read_text())
            root=directory/'agent/openharness-rollout'
            if not (root/'events.jsonl').exists():
                trials.append(dict(trial_name=directory.name,result_path=str(result_path),
                    result_sha256=source_before,raw_reward=(result.get('verifier_result')or{}).get('rewards'),
                    raw_exception=(result.get('exception_info')or{}).get('exception_type'),
                    failure_phase=result.get('failure_phase'),recorder_available=False,
                    affected_by_once_per_drive_guard=None,
                    audit_classification='NO_RECORDER_ENVIRONMENT_OR_SETUP_FAILURE'))
                continue
            view=RolloutView.open(root);calls,_,runs,contexts=view.rows()
            resolve=lambda v:loadValue(v,root/'artifacts')
            agent=sorted((c for c in calls if c['source']=='agent'),key=lambda c:c['started_at'])
            responses=[resolve(c.get('response')) for c in agent]
            overflows=[i for i,r in enumerate(responses)if r and isContextOverflow(r,262144)]
            recovered=[]
            for a,b in zip(overflows,overflows[1:]):
                successful=[(i,r)for i,r in enumerate(responses[a+1:b],a+1)
                            if r and r.get('stopReason')in ('stop','toolUse')]
                if successful:
                    recovered.append(dict(first_overflow_call=agent[a]['call_id'],
                        later_overflow_call=agent[b]['call_id'],
                        normal_tool_use_between=sum(r['stopReason']=='toolUse' for _,r in successful),
                        normal_stop_between=sum(r['stopReason']=='stop' for _,r in successful),
                        auxiliary_success_between=sum(c['source']!='agent' and (resolve(c.get('response')) or {}).get('stopReason')in ('stop','toolUse')
                            and agent[a]['ended_at']<c['started_at']<agent[b]['started_at'] for c in calls),
                        later_overflow_is_terminal=b==len(agent)-1))
            affected=bool(recovered and recovered[-1]['later_overflow_is_terminal']
                and responses[-1]['stopReason']=='error')
            row=dict(trial_name=directory.name,result_path=str(result_path),result_sha256=source_before,
                raw_reward=(result.get('verifier_result')or{}).get('rewards'),
                verifier_return_code=(result.get('verifier_result')or{}).get('return_code'),
                raw_exception=(result.get('exception_info')or{}).get('exception_type'),
                recorder_integrity=view.validate(),run_statuses=[r['status'] for r in runs],
                recorder_events_sha256=sha(root/'events.jsonl'),overflow_calls=len(overflows),
                last_agent_stop_reason=(responses[-1] or {}).get('stopReason'),
                last_agent_error=(responses[-1] or {}).get('errorMessage'),
                repeated_after_success_episodes=recovered,affected_by_once_per_drive_guard=affected)
            trials.append(row)
            for index in overflows:
                call=agent[index];native=resolve(call['input']);payload=resolve(call['payload'])
                investigation=historical_estimate(directory,call,native)
                message=responses[index].get('errorMessage','')
                match=re.search(r'(\d+) tokens from the input messages',message)
                stem=directory.name+'--'+call['call_id']
                path=output/(stem+'.json')
                value=dict(trial_name=directory.name,call_id=call['call_id'],source_result_sha256=source_before,
                    source_events_sha256=row['recorder_events_sha256'],native_input=native,provider_payload=payload,
                    provider_actual_input_tokens=int(match.group(1))if match else None,
                    raw_error=message,harness_replay=investigation)
                encoded=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
                if path.exists():assert path.read_text()==encoded
                else:path.write_text(encoded);path.chmod(0o600)
                estimates.append(dict(trial_name=directory.name,call_id=call['call_id'],path=str(path),
                    sha256=sha(path),provider_actual_input_tokens=value['provider_actual_input_tokens'],
                    harness_replay=investigation))
            assert sha(result_path)==source_before
    result=dict(kind='READ_ONLY_EXISTING_EPOCH3_CONTEXT_RECOVERY_AUDIT',checked_at=time.time(),
        actual_terminal_trials=len(trials),affected_trials=sum(t['affected_by_once_per_drive_guard'] is True for t in trials),
        trials=trials,token_investigation_inputs=estimates,source_sha256=sha(__file__),
        raw_results_rewards_exits_recorders_or_sessions_modified=False,
        source_scope='Only completed original E3 diagnostic Jobs; running Trials are not opened or altered')
    p=R/'checks/HISTORICAL_CONTEXT_RECOVERY_AUDIT_R2.json'
    tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
    print(json.dumps(dict(terminal=len(trials),affected=result['affected_trials'],
        affected_names=[t['trial_name']for t in trials if t['affected_by_once_per_drive_guard']],
        token_inputs=len(estimates))),flush=True)


if __name__=='__main__':main()
