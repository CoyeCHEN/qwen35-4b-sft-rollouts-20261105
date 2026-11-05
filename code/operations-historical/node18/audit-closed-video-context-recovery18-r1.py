"""Stream a closed, SHA-verified native Recorder without opening its Session."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from foundation.ai.utils.errors import isContextOverflow
from foundation.rollouts.export import loadValue

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
E = R / 'formal-native-eval-r1'
NAME = 'video-processing__new-m1-e3-fixed-r1'
T = E / 'jobs/qwen35-new772-new-m1-epoch3-fixed-unstarted-continuation-r1' / NAME
EXPECTED_RESULT = 'af5fcdcc22d34019975557c50af6aa16ff5910b7cc7469a7d94f544ac658ea09'
WHEEL = '1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'


def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main():
    output = R / 'checks/ACTUAL_FIXED_E3_VIDEO_CONTEXT_RECOVERY_R1.json'
    assert not output.exists(), 'Keep accepted historical evidence immutable'
    assert sha(T / 'result.json') == EXPECTED_RESULT
    replica = json.loads((R / 'checks/E3_CLOSED_EVIDENCE_REPLICA_STATUS_R1.json').read_text())
    assert replica['passed'] and any(x['trial_name'] == NAME and x['result_sha256'] == EXPECTED_RESULT
                                    for x in replica['closed_trials'])
    artifact = json.loads((T / 'agent/artifact.json').read_text())
    assert artifact['wheel_sha256'] == WHEEL
    root = T / 'agent/openharness-rollout'
    events = Counter()
    starts = {}
    ended = set()
    calls = []
    contexts = []
    stops = Counter()
    usage = Counter()
    digest = hashlib.sha256()
    for line in (root / 'events.jsonl').open('rb'):
        digest.update(line)
        event = json.loads(line)
        kind, data = event['type'], event['data']
        events[kind] += 1
        if kind == 'call_start':
            assert data['call_id'] not in starts
            starts[data['call_id']] = data['source']
        elif kind == 'call_end':
            ident = data['call_id']
            assert ident not in ended
            ended.add(ident)
            response = loadValue(data.get('response'), root / 'artifacts') or {}
            source = starts[ident]
            stops[source + ':' + str(response.get('stopReason'))] += 1
            for key in ('input', 'output', 'reasoning'):
                usage[source + ':' + key] += (response.get('usage') or {}).get(key, 0)
            if source == 'agent':
                calls.append(dict(call_id=ident, time=event['timestamp'], stop=response.get('stopReason'),
                                  context_overflow=isContextOverflow(response, 262144)))
        elif kind == 'context_event':
            value = loadValue(data['event'], root / 'artifacts')
            contexts.append(dict(time=event['timestamp'], type=value['type'],
                                 reason=value.get('reason'), willRetry=value.get('willRetry'),
                                 result_present=value.get('result') is not None,
                                 errorMessage=value.get('errorMessage'), aborted=value.get('aborted')))
    overflow = [i for i, call in enumerate(calls) if call['context_overflow']]
    episodes = []
    for first, later in zip(overflow, overflow[1:]):
        between = calls[first + 1:later]
        normal = [call for call in between if call['stop'] in ('stop', 'toolUse')]
        if not normal:
            continue
        following = next((call for call in calls[later + 1:] if call['stop'] in ('stop', 'toolUse')), None)
        episodes.append(dict(first_overflow=calls[first], later_independent_overflow=calls[later],
                             normal_tool_use_between=sum(call['stop'] == 'toolUse' for call in normal),
                             normal_stop_between=sum(call['stop'] == 'stop' for call in normal),
                             first_complete_assistant_after_later_overflow=following))
    result = json.loads((T / 'result.json').read_text())
    assert sha(T / 'result.json') == EXPECTED_RESULT
    proof = dict(kind='CLOSED_NATIVE_VIDEO_CONTEXT_RECOVERY_READONLY', at=time.time(),
                 trial_name=NAME, trial_id=result['id'], result_sha256=EXPECTED_RESULT,
                 events_sha256=digest.hexdigest(), wheel_sha256=WHEEL,
                 source_replica_manifest_sha256=replica['source_manifest_sha256'],
                 source_sha256=sha(Path(__file__)), event_counts=dict(events),
                 model_stop_reasons_by_source=dict(stops), model_usage_by_source=dict(usage),
                 agent_calls_completed=len(calls), context_overflow_calls=len(overflow),
                 unfinished_calls=[dict(call_id=ident, source=source) for ident, source in starts.items()
                                   if ident not in ended],
                 context_events=contexts, independent_recovery_episodes=episodes,
                 raw_reward=result['verifier_result']['rewards'],
                 verifier_return_code=result['verifier_result']['return_code'],
                 raw_exception=(result.get('exception_info') or {}).get('exception_type'),
                 raw_infrastructure_errors=result.get('infrastructure_errors'),
                 recorder_run_end_present=bool(events['run_end']),
                 qualified_complete_task_success_not_claimed=True,
                 source_result_reward_recorder_or_exit_modified=False, new_model_or_tool_calls=0)
    with output.open('x') as target:
        target.write(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
