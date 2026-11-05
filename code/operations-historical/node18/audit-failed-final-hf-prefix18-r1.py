"""CPU audit of the completed calls in the preserved failed final-HF smoke."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from foundation.rollouts.export import RolloutView
from foundation.rollouts.store import isArtifactRef

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    failure_path = R / 'checks/NEW_M2_FINAL_HF_NATIVE_CLI_FAILURE_R1.json'
    failure = json.loads(failure_path.read_text())
    original = Path(failure['smoke'])
    view = RolloutView.open(original / 'recorder')
    validation = view.validate()
    assert validation['complete'] is False
    def resolve(value):
        if isArtifactRef(value):
            raw = view.readArtifact(value)
            return raw.decode() if value['encoding'] == 'utf-8' else raw
        if isinstance(value, dict):
            return {key: resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve(item) for item in value]
        return value
    calls, tools, runs, contexts = [resolve(value) for value in view.rows()]
    active = [call for call in calls if call['source'] == 'agent']
    assert len(runs) == 1 and runs[0]['status'] != 'completed'
    assert active and all(call['status'] in ['stop', 'toolUse'] for call in active)
    projected = []
    for call in active:
        payload = call['payload']
        assert call['fidelity'] == 'provider_payload'
        assert payload['model'] == failure['model']
        assert len(payload['tools']) == 11
        for key, expected in dict(max_tokens=81920, temperature=1., top_p=.95,
                top_k=20, min_p=0., presence_penalty=1.5, repetition_penalty=1.,
                stream=True).items():
            assert payload[key] == expected
        response = call['response']
        assistant = dict(role='assistant',
            content=''.join(x['text'] for x in response['content'] if x['type'] == 'text'),
            reasoning_content=''.join(x['thinking'] for x in response['content'] if x['type'] == 'thinking'))
        tc = [dict(id=x['id'], type='function', function=dict(name=x['name'],
            arguments=json.dumps(x['arguments'], ensure_ascii=False)))
            for x in response['content'] if x['type'] == 'toolCall']
        if tc:
            assistant['tool_calls'] = tc
        usage = response['usage']
        projected.append(dict(call_id=call['call_id'], context_fidelity='provider_payload',
            provider_payload=payload, assistant_response=assistant,
            actual_prompt_tokens=usage['input'] + usage['cacheRead']))
    output = R / 'checks/failed-final-hf-prefix-r1'
    output.mkdir()
    (output / 'config.json').write_bytes((original / 'config.json').read_bytes())
    (output / 'RESOLVED_NATIVE_CALLS.json').write_text(json.dumps(projected, ensure_ascii=False) + '\n')
    run = subprocess.run([str(R / 'env/serve-new11-r1/bin/python'),
        str(R / 'audit-native-cli-prefix-r1.py'), str(output)],
        env=os.environ | dict(CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='1'),
        capture_output=True, text=True, timeout=180)
    (output / 'prefix-audit.stdout.log').write_text(run.stdout)
    (output / 'prefix-audit.stderr.log').write_text(run.stderr)
    proof = dict(at=time.time(), original_smoke=str(original),
        completed_agent_calls=len(active), actual_tools=len(tools),
        recorder_validation=validation, native_run_status=runs[0]['status'],
        finish_calls=sum(tool['name'] == 'finish' for tool in tools),
        full_hf_protocol_admission=False, actual_new_model_or_tool_calls=0,
        prefix_auditor_returncode=run.returncode,
        prefix_audit=json.loads((output / 'NATIVE_PREFIX_AUDIT.json').read_text())
            if (output / 'NATIVE_PREFIX_AUDIT.json').exists() else None,
        source_sha256=sha(Path(__file__)), failed_smoke_evidence_sha256=sha(failure_path),
        original_events_sha256=sha(original / 'recorder/events.jsonl'),
        failed_smoke_preserved=True)
    assert proof['original_events_sha256'] == failure['files'][str(original / 'recorder/events.jsonl')]
    target = R / 'checks/NEW_M2_FAILED_FINAL_HF_PREFIX_AUDIT_R1.json'
    assert not target.exists()
    target.write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(dict(completed_agent_calls=len(active), actual_tools=len(tools),
        prefix_auditor_returncode=run.returncode,
        prefix_passed=bool(proof['prefix_audit'] and proof['prefix_audit']['passed']),
        full_hf_protocol_admission=False, actual_new_model_or_tool_calls=0)))


if __name__ == '__main__':
    main()
