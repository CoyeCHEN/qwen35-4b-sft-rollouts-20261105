"""Read-only live/provider evidence; never equates a live prefix with success."""
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
WHEEL = ROOT / 'wheels/open_harness_ai-0.3.0-py3-none-any.whl'
sys.path.insert(0, str(WHEEL))
from foundation.rollouts.export import loadValue


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def main():
    submission = json.loads((ROOT / 'checks/canary-first2-submission.json').read_text())
    expected = json.loads((ROOT / 'checks/offline-teacher-contract.json').read_text())
    rows = []
    for journal in sorted((ROOT / 'jobs' / submission['job_name']).glob('*/agent/openharness-rollout/events.jsonl')):
        rollout = journal.parent; trial = rollout.parent.parent
        calls = {}; tools = Counter(); event_counts = Counter(); thinking = 0; models = set(); violations = []; effective = []
        for raw in journal.read_text().splitlines():
            event = json.loads(raw); data = event.get('data') or {}; kind = event['type']; event_counts[kind] += 1
            ident = data.get('call_id')
            if kind == 'run_start':
                config = loadValue(data.get('config'), rollout / 'artifacts')
                if isinstance(config, dict):
                    effective.append({k: config.get(k) for k in ['toolResultBudget', 'compaction', 'backgroundJobs',
                        'finish', 'timeBudget', 'persist', 'requestOptions', 'tools', 'thinkingLevel']})
            elif kind == 'call_start':
                calls.setdefault(ident, {}).update(source=data.get('source'))
            elif kind == 'call_payload':
                payload = loadValue(data['payload'], rollout / 'artifacts')
                schemas = [{k: t['function'][k] for k in ['name', 'description', 'parameters']} for t in payload.get('tools', [])]
                names = [t['name'] for t in schemas]
                systems = [m['content'] for m in payload['messages'] if m.get('role') == 'system']
                prompt_sha = hashlib.sha256(systems[0].encode()).hexdigest() if len(systems) == 1 else None
                proof = dict(call_id=ident, tool_names=names, tool_schema_sha256=digest(schemas),
                    provider_tools_sha256=digest(payload.get('tools', [])), system_prompt_sha256=prompt_sha,
                    model=payload['model'], thinking=payload.get('thinking'), reasoning_effort=payload.get('reasoning_effort'),
                    max_tokens=payload.get('max_tokens'), stream=payload.get('stream'), temperature=payload.get('temperature'),
                    payload_sha256=digest(payload), visible_roles=dict(Counter(m['role'] for m in payload['messages'])))
                if calls.get(ident, {}).get('source') == 'agent':
                    if names != expected['tool_names'] or digest(schemas) != expected['tool_schema_sha256']:
                        violations.append(dict(call_id=ident, kind='TOOL_CONTRACT_MISMATCH'))
                    if prompt_sha != expected['system_prompt_sha256']:
                        violations.append(dict(call_id=ident, kind='SYSTEM_PROMPT_MISMATCH'))
                    if payload.get('thinking') != {'type': 'enabled'} or payload.get('reasoning_effort') != 'max':
                        violations.append(dict(call_id=ident, kind='THINKING_CONTRACT_MISMATCH'))
                    if payload.get('max_tokens') != 65536 or payload.get('stream') is not True or payload.get('temperature') != 1:
                        violations.append(dict(call_id=ident, kind='REQUEST_BUDGET_CONTRACT_MISMATCH'))
                calls.setdefault(ident, {}).update(payload=proof)
            elif kind == 'call_chunk':
                value = loadValue(data['chunk'], rollout / 'artifacts')
                try:
                    chunk = json.loads(value) if isinstance(value, str) else value
                except ValueError:
                    continue
                if not isinstance(chunk, dict):
                    continue
                if chunk.get('model'): models.add(chunk['model'])
                for choice in chunk.get('choices', []):
                    thinking += len((choice.get('delta') or {}).get('reasoning_content') or '')
            elif kind == 'call_end':
                response = loadValue(data.get('response'), rollout / 'artifacts')
                calls.setdefault(ident, {}).update(status=data.get('status'),
                    stop_reason=response.get('stopReason') if isinstance(response, dict) else None,
                    usage=response.get('usage') if isinstance(response, dict) else None)
            elif kind == 'tool_start':
                tools[data['name']] += 1
        result_file = trial / 'result.json'
        result = json.loads(result_file.read_text()) if result_file.exists() else None
        rows.append(dict(trial_directory=str(trial), journal_sha256=hashlib.sha256(journal.read_bytes()).hexdigest(),
            event_counts=dict(event_counts), calls=calls, observed_tool_calls=dict(tools), effective_runtime_config=effective,
            raw_thinking_characters_observed=thinking, provider_response_models=sorted(models),
            contract_violations=violations, native_result_present=result is not None,
            native_reward=(result.get('verifier_result') or {}).get('rewards') if result else None,
            native_exception=(result.get('exception_info') or {}).get('exception_type') if result else None,
            qualified_success='NOT_DECIDED_BY_THIS_LIVE_PREFIX_AUDIT'))
    report = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        status='LIVE_PREFIX_PROTOCOL_OBSERVATION', job_name=submission['job_name'], trials=rows,
        teacher_attempts_requested=2, canary_cohort_total=16,
        actual_provider_payload_evidence=True, full_canary_acceptance=False,
        recorder_integrity_and_student_conversion_acceptance='PENDING_TERMINAL_AUDIT',
        tool_schema_digest_format='json.dumps(sort_keys=True,ensure_ascii=False), UTF-8 SHA256')
    file = ROOT / 'checks/canary-first2-live-protocol.json'; temporary = file.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2)); temporary.replace(file)
    print(json.dumps(dict(status=report['status'], trials=[dict(path=r['trial_directory'], calls=len(r['calls']),
        tools=r['observed_tool_calls'], thinking_chars=r['raw_thinking_characters_observed'],
        payloads=sum('payload' in c for c in r['calls'].values()), violations=r['contract_violations'],
        native_reward=r['native_reward']) for r in rows])))


if __name__ == '__main__':
    main()
