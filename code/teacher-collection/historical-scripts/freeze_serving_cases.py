"""Read three existing failed textual requests; do not execute tasks or tools."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
WHEEL = ROOT.parent/'qwen35-m1-m2-tb21-20261026/wheels/null-delta/open_harness_ai-0.3.0-py3-none-any.whl'
assert hashlib.sha256(WHEEL.read_bytes()).hexdigest() == 'f84f810e8a61545d685fb6722593886a0c88cc829b2ab9ca7c3476fe11e1209e'
sys.path.insert(0, str(WHEEL))
from foundation.rollouts.export import loadValue

rows = []
for task in ['build-pmars', 'cancel-async-tasks', 'nginx-request-logging']:
    case = json.loads((ROOT/f'stage1/case-m2-{task}.private.json').read_text())
    call = case['first_length']
    assert call and call['source'] == 'agent' and call['input_images'] == 0
    path = Path(case['source_events'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == case['events_sha256']
    found = {}
    with path.open() as stream:
        for line, raw in enumerate(stream, 1):
            if line not in (call['payload_line'], call['response_line']):
                continue
            event = json.loads(raw)
            assert event['data']['call_id'] == call['call_id']
            key = 'payload' if line == call['payload_line'] else 'response'
            found[key] = loadValue(event['data'][key], path.parent/'artifacts')
    assert set(found) == {'payload', 'response'}
    assert all(m['role'] in ('system', 'user', 'assistant', 'tool') for m in found['payload']['messages'])
    rows.append(dict(task=task, call_id=call['call_id'], source_events=str(path),
        source_events_sha256=case['events_sha256'], payload_line=call['payload_line'],
        response_line=call['response_line'], historical_input_tokens=call['usage']['input'], **found))
target = ROOT/'stage1/serving-frozen-cases.private.json'
with target.open('x') as stream:
    json.dump(rows, stream)
target.chmod(0o600)
print(json.dumps(dict(cases=len(rows), path=str(target), sha256=hashlib.sha256(target.read_bytes()).hexdigest())))
