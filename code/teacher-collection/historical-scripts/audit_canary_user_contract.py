"""Account existing native trials against the USER's ten-tool contract.

Read-only: reward, normal exit, Recorder closure, tool contract, and billing
observability are deliberately separate. No requests and no trial restarts.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sys.path.insert(0,str(ROOT/'wheels/open_harness_ai-0.3.0-py3-none-any.whl'))
from foundation.rollouts.export import loadValue

rows=[];requests=[]
job=ROOT/'jobs/cf-tmax-canary-first2-20261030'
config=json.loads((job/'config.json').read_text())
expected={'read','bash','edit','write','grep','find','ls','bash_job','trajectory_read','edit_patch'}
for result_path in sorted(job.glob('*/result.json')):
    result=json.loads(result_path.read_text());trial=result_path.parent;rollout=trial/'agent/openharness-rollout'
    counts=Counter();names=set();run_ends=[];calls={};tools={};usage=[];payloads=0
    errors=[]
    with (rollout/'events.jsonl').open() as stream:
        for line,raw in enumerate(stream,1):
            event=json.loads(raw);kind=event['type'];data=event.get('data') or {};counts[kind]+=1
            if kind=='call_start':calls[data['call_id']]='RUNNING'
            elif kind=='call_payload':
                payloads+=1;payload=loadValue(data['payload'],rollout/'artifacts')
                actual={x['function']['name'] for x in payload.get('tools',[])};names|=actual
                requests.append(dict(trial_id=result['id'],task_id=result['task_name'],call_id=data['call_id'],
                    event_line=line,payload_ordinal=payloads,source='RECORDED_HTTP_PAYLOAD_BEFORE_SEND',
                    payload_sha256=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
                    request_billing_status='SEE_RESPONSE_USAGE; missing usage stays UNKNOWN'))
                if actual and actual!=expected:errors.append('TOOL_CONTRACT_MISMATCH_FINISH_PRESENT' if 'finish'in actual else 'TOOL_CONTRACT_MISMATCH')
            elif kind=='call_end':
                calls[data['call_id']]=data.get('status');response=loadValue(data.get('response'),rollout/'artifacts')
                usage.append(dict(call_id=data['call_id'],status=data.get('status'),usage=response.get('usage') if isinstance(response,dict) else None))
            elif kind=='tool_start':tools[data['execution_id']]='RUNNING'
            elif kind=='tool_end':tools[data['execution_id']]=data.get('status')
            elif kind=='run_end':run_ends.append(data.get('status'))
    complete=bool(run_ends) and all(x=='completed' for x in run_ends) and 'RUNNING' not in calls.values() and 'RUNNING' not in tools.values()
    rewards=(result.get('verifier_result')or{}).get('rewards',{})
    agent_finish=trial/'agent/open-harness.complete.json'
    agent_exit=json.loads(agent_finish.read_text()).get('exit_code') if agent_finish.exists() else None
    score_valid=(result.get('verifier_result')or{}).get('return_code')==0 and type(rewards.get('reward'))in(int,float)
    ledger_config=config['agents'][0]['kwargs']['config'].get('tokenObservation',{})
    normal=not result.get('exception_info') and agent_exit==0
    rows.append(dict(task_id=result['task_name'],trial_id=result['id'],result_path=str(result_path),
        reward=rewards,verifier_valid=score_valid,normal_agent_exit=normal,agent_exit_code=agent_exit,
        recorder_complete=complete,run_end_statuses=run_ends,events=dict(counts),declared_tool_names=sorted(names),
        native_token_observation_enabled=ledger_config.get('enabled',False),observed_http_payloads=payloads,
        response_usage=usage,user_protocol_violations=sorted(set(errors)),
        qualified_for_new_training=bool(score_valid and rewards['reward']==1 and normal and complete and not errors),
        role='EXISTING_PROTOCOL_DIAGNOSTIC_ATTEMPT; preserve and count, do not silently relabel',
        source_recorder=str(rollout/'events.jsonl')))
with (ROOT/'stage2/observed-request-ledger-first2.jsonl').open('w') as stream:
    for row in requests:stream.write(json.dumps(row)+'\n')
proof=dict(trials=rows,teacher_trial_attempts=len(rows),valid_verifier_successes=sum(r['verifier_valid'] and r['reward']['reward']==1 for r in rows),
    qualified_new_training_successes=sum(r['qualified_for_new_training']for r in rows),
    observed_http_payload_requests=len(requests),request_retry_count='NOT_EQUATED_WITH_TASK_ATTEMPTS; original call/event identities retained',
    legacy_11_tool_canary_is_not_ten_tool_acceptance=True,new_requests=0,new_trials=0)
(ROOT/'checks/canary2-user-contract-audit.json').write_text(json.dumps(proof,indent=2))
print(json.dumps({k:v for k,v in proof.items()if k!='trials'}))
