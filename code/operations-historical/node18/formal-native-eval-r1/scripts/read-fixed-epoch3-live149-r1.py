"""Read only this campaign's running repaired E3 containers; no dispatch."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
WHEEL = '1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'
os.environ['SSH_AUTH_SOCK'] = str(R.parent / 'near-r3-20261015/auth.sock')
DOCKER = ['docker', '--host', 'ssh://chenkeyi@127.0.0.1:5102']

INSIDE = r'''
from collections import Counter
import hashlib,json,pathlib
from foundation.rollouts.export import loadValue
p=pathlib.Path('/logs/agent/openharness-rollout')
raw=(p/'events.jsonl').read_bytes()
complete=raw[:raw.rfind(b'\n')+1]
events=[json.loads(line)for line in complete.splitlines()]
starts=[e for e in events if e['type']=='call_start'and e['data']['source']=='agent']
first=starts[0]
payload_event=next(e for e in events if e['type']=='call_payload'and e['data']['call_id']==first['data']['call_id'])
payload=loadValue(payload_event['data']['payload'],p/'artifacts')
request=payload.get('request',payload)
tools=request['tools']
run=next(e for e in events if e['type']=='run_start')
config=run['data']['config']
out=dict(session_id=run['data']['session_id'],run_id=run['data']['run_id'],
 agent_start_timestamp=run['timestamp'],first_call_id=first['data']['call_id'],
 first_agent_call_timestamp=first['timestamp'],latest_event_timestamp=events[-1]['timestamp'],
 latest_event_seq=events[-1]['seq'],actual_agent_model_calls_started=len(starts),
 actual_calls_ended=sum(e['type']=='call_end'for e in events),
 actual_tool_calls=sum(e['type']=='tool_start'for e in events),event_types=dict(Counter(e['type']for e in events)),
 recorder_snapshot_bytes=len(complete),recorder_snapshot_sha256=hashlib.sha256(complete).hexdigest(),
 trailing_incomplete_event_excluded=len(raw)!=len(complete),source_recorder_path=str(p/'events.jsonl'),
 actual_wire_fields={k:request.get(k)for k in ['model','stream','max_tokens','temperature','top_p','top_k',
 'min_p','presence_penalty','repetition_penalty','reasoning_effort','chat_template_kwargs']},
 tool_names=[t['function']['name']for t in tools],
 tool_schema_sha256=hashlib.sha256(json.dumps(tools,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
 actual_run_configuration={k:v for k,v in config.items()if any(x in k.lower()for x in ['compaction','finish','backgroundjobs','toolresultbudget'])},
 qualification_status='RUNNING_NOT_YET_SCORED',verifier_reward=None)
assert len(out['tool_names'])==11 and 'finish'in out['tool_names']
assert request['max_tokens']==81920 and request['chat_template_kwargs']['enable_thinking']
print(json.dumps(out))
'''


def run(args, **kwargs):
    value = subprocess.run(DOCKER + args, capture_output=True, text=True, timeout=35, **kwargs)
    value.check_returncode()
    return value.stdout


def main():
    engine = run(['info', '--format', '{{.ID}}']).strip()
    assert engine == 'c6e16cdf-e878-4cc5-84c8-78a56c54b5c5'
    containers = [json.loads(line) for line in run(['ps', '--format', '{{json .}}']).splitlines()]
    trials = []
    job = R / 'jobs/qwen35-new772-new-m1-epoch3-fixed-diagnostic'
    for container in containers:
        if not container['Names'].startswith('q35new772e3fixednewm1-'):
            continue
        cid = container['ID']
        labels = json.loads(run(['inspect', cid, '--format', '{{json .Config.Labels}}']))
        compose = Path(labels['com.docker.compose.project.config_files'])
        directory = compose.parent
        assert directory.parent == job and directory.name.endswith('__new-m1-e3-fixed-r1')
        artifact = json.loads((directory / 'agent/artifact.json').read_text())
        assert artifact['wheel_sha256'] == WHEEL
        row = json.loads(run(['exec', cid, '/harbor/agent-runtime/harbor-open-harness-venv/bin/python', '-c', INSIDE]))
        row.update(trial=directory.name, container_id=cid,
                   trial_config_sha256=hashlib.sha256((directory / 'config.json').read_bytes()).hexdigest(),
                   installed_artifact_sha256=hashlib.sha256((directory / 'agent/artifact.json').read_bytes()).hexdigest(),
                   actual_installed_wheel_sha256=artifact['wheel_sha256'])
        trials.append(row)
    proof = dict(kind='REPAIRED_WHEEL_ACTUAL_NATIVE_TRIAL_MODEL_RECORDER_EVIDENCE', at=time.time(),
                 native_job=job.name, official_engine_id=engine, model_execution_node='18',
                 model_endpoint_port=18303, wheel_sha256=WHEEL, trials=trials,
                 source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 original_results_rewards_exits_sessions_recorders_modified=False,
                 original_r4_diagnostics_are_historical_only=True)
    assert len(trials) == 2 and all(t['actual_agent_model_calls_started'] > 1 for t in trials)
    proof['two_real_agent_trials_overlap'] = max(t['agent_start_timestamp'] for t in trials) < min(t['latest_event_timestamp'] for t in trials)
    assert proof['two_real_agent_trials_overlap']
    output = R / 'checks/REPAIRED_EPOCH3_NATIVE_LIVE_ACCEPTANCE_R1.json'
    assert not output.exists(), 'Retain the original live acceptance snapshot'
    output.write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()
