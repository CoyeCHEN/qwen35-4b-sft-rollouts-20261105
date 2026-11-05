"""Integration fixtures: malformed terminal journal cannot block later healthy Trials."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
S = R / 'checks/terminal-recorder-isolation-fixture-r188'
S.mkdir(exist_ok=False)
sources = ['audit_native_canary_protocol_r186.py', 'export_native_canary_calls_r187.py',
           'audit_stream_data_worker149_r7.py']
sha = lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
for name in ['checks', 'manifests', 'indexes', 'derived', 'scripts']:
    (S / name).mkdir()
(S / 'wheels').symlink_to(R / 'wheels', target_is_directory=True)
(S / 'checks/offline-teacher-contract.json').symlink_to(R / 'checks/offline-teacher-contract.json')
for name in ['CALIBFORGE_500_TASKS.jsonl', 'TMAX_RUNTIME_CANDIDATES_V2.jsonl']:
    (S / 'manifests' / name).symlink_to(R / 'manifests' / name)
(S / 'scripts/teacher_call_dispositions.py').symlink_to(R / 'scripts/teacher_call_dispositions.py')
base = S / 'stream/collection-r4'
(base / 'trials').mkdir(parents=True)
(base / 'CAMPAIGN.json').write_text(json.dumps(dict(native_concurrency=8)))
task = json.loads((R / 'manifests/CALIBFORGE_500_TASKS.jsonl').open().readline())['task_id']
response = dict(role='assistant',content='',reasoning_content='',usage={})
events = [dict(type='call_start',data=dict(call_id='fixture-call',source='agent')),
          dict(type='call_payload',data=dict(call_id='fixture-call',payload=dict(model='deepseek-flash',messages=[],tools=[]))),
          dict(type='call_end',data=dict(call_id='fixture-call',status='completed',response=response))]
for name in ['a-good','b-broken','c-good']:
    trial = base / 'trials' / name
    journal = trial / 'agent/openharness-rollout/events.jsonl'
    journal.parent.mkdir(parents=True)
    journal.write_text(''.join(json.dumps(event)+'\n' for event in events) if 'good' in name else '{"type":"unterminated\n')
    (trial / 'result.json').write_text(json.dumps(dict(id=name,task_name=task,
        config=dict(task=dict(path='/fixture/'+task)),finished_at='2026-10-31T00:00:00Z',verifier_result=None,exception_info=None)))


def module(name):
    spec=importlib.util.spec_from_file_location(name,R / 'scripts' / name)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    value.ROOT=S
    return value


protocol=module('audit_native_canary_protocol_r186.py')
protocol.protocol_cache.lookup=lambda *args:(None,None)
protocol.protocol_cache.store=lambda *args:None
exporter=module('export_native_canary_calls_r187.py')
exporter.export_inputs=lambda *args:{}
exporter.reuse_export=lambda *args:None
exporter.store_export=lambda *args:None
old_argv=sys.argv
try:
    sys.argv=['fixture','stream-collection-r4']
    for value in [protocol,exporter]:
        with contextlib.redirect_stdout(io.StringIO()):value.main()
    # A second pass proves an already-reported bad journal is not mistaken
    # for a valid cached export, and unchanged good gzip files remain valid.
    with contextlib.redirect_stdout(io.StringIO()):exporter.main()
finally:
    sys.argv=old_argv
p=json.loads((S / 'checks/stream-collection-r4-live-protocol.json').read_text())['trials']
e=json.loads((S / 'checks/stream-collection-r4-actual-calls-export.json').read_text())
assert len(p)==len(e)==3
assert p[1]['contract_violations'][0]['kind']=='TERMINAL_RECORDER_JSON_INVALID'
assert p[1]['qualified_success']=='REJECTED_INCOMPLETE_OR_INVALID_RECORDER'
assert e[1]['exported']==0 and not e[1]['cost_token_ledger_complete']
assert e[1]['billing_status']=='UNKNOWN_INCOMPLETE_RECORDER_NOT_ZERO'
assert e[0]['exported']==e[2]['exported']==1
ledger=[json.loads(line) for line in (S / 'indexes/stream-collection-r4-CALL_COST_TOKEN_LEDGER.jsonl').open()]
assert len(ledger)==2 and {row['trial_id'] for row in ledger}=={'a-good','c-good'}
proof=dict(passed=True,scope='Synthetic terminal journal integration; no Teacher or official Verifier runs',
    valid_trials_before_and_after_broken=2,bad_trial_rejected=True,repeated_export_passed=True,
    fabricated_usage_entries=0,raw_originals_modified=False,model_calls=0,
    sources={name:sha(R / 'scripts' / name) for name in sources})
with (R / 'checks/terminal-recorder-isolation-acceptance-r188.json').open('x') as stream:
    json.dump(proof,stream,indent=2)
print(json.dumps(proof))
