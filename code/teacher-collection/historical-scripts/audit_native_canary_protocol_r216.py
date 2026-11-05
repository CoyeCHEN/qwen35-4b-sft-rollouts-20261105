"""Read-only live/provider evidence; never equates a live prefix with success."""
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path
import sys
import ast

ROOT = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
WHEEL = ROOT / 'wheels/open_harness_ai-0.3.0-py3-none-any.whl'
sys.path.insert(0, str(WHEEL))
from foundation.rollouts.export import loadValue
import protocol_trial_cache_r23 as protocol_cache

# This is the same established cache, with the exact unchanged valid-row
# producer identity. R192 changes only the invalid-JSON exception path.
# Pin both source files and compare all other AST nodes before any reuse.
VALID_CACHE_PRODUCER=ROOT/'scripts/audit_native_canary_protocol_r186.py'
NEGATIVE_POLICY_SOURCE=ROOT/'scripts/audit_native_canary_protocol_r192.py'
assert hashlib.sha256(VALID_CACHE_PRODUCER.read_bytes()).hexdigest()=='7a5d634045d53cf3e9d889e4b1033f61fbf1905d71d0220ff3e110899de89e01'
assert hashlib.sha256(NEGATIVE_POLICY_SOURCE.read_bytes()).hexdigest()=='f35ce80802d85c74948261a0cbde8e86cfcbcebb00dfc424ea0d3f80385300a4'

def valid_path_ast(path):
    tree=ast.parse(path.read_bytes())
    for node in ast.walk(tree):
        if isinstance(node,ast.ExceptHandler) and isinstance(node.type,ast.Attribute) and node.type.attr=='JSONDecodeError':
            node.body=[ast.Pass()]
    return ast.dump(tree,include_attributes=False)

assert valid_path_ast(VALID_CACHE_PRODUCER)==valid_path_ast(NEGATIVE_POLICY_SOURCE)
VALID_PARSER_AST_SHA256=hashlib.sha256(valid_path_ast(VALID_CACHE_PRODUCER).encode()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def runtime_violations(config):
    required={
        ('toolResultBudget','enabled'):True,('toolResultBudget','maxCharsPerBatch'):200000,
        ('toolResultBudget','previewChars'):2000,('finish','enabled'):True,
        ('backgroundJobs','enabled'):True,('backgroundJobs','maxConcurrent'):2,
        ('backgroundJobs','maxOutputBytes'):20000000,('backgroundJobs','keepProcesses'):True,
        ('backgroundJobs','handoffTimeout'):600,('timeBudget','seconds'):0,
        ('compaction','enabled'):True,('compaction','reserveTokens'):81920,
        ('compaction','keepRecentTokens'):20000,('compaction','maxTurns'):0,
        ('retry','enabled'):True,('retry','maxRetries'):3,
        ('requestOptions','maxTokens'):65536,('requestOptions','temperature'):1,
        ('requestOptions','timeout'):120,
    }
    result=[]
    for keys,expected in required.items():
        actual=config
        for key in keys:actual=actual.get(key) if isinstance(actual,dict) else None
        if actual!=expected:result.append(dict(kind='EFFECTIVE_RUNTIME_CONTRACT_MISMATCH',field='.'.join(keys),expected=expected,actual=actual))
    return result


def main():
    job=sys.argv[1]
    submissions = {
        'cf-tmax-canary-first2-20261030': 'canary-first2-submission.json',
        'cf-tmax-canary-remaining14-20261030': 'canary-remaining14-submission.json',
        'cf-tmax-canary-second-attempt6-20261030': 'canary-second-attempt6-submission.json',
        'cf-summary-contract-canary-20261030': 'canary-summary-cf-submission.json',
        'tmax-summary-contract-canary-20261030': 'canary-summary-tmax-submission.json',
        'cf-tmax-original-environment-canary-20261030': 'canary-original-environment-corrective9-submission.json',
        'tmax-original-environment-acceptance-extension-20261030': 'canary-tmax-acceptance-extension-submission.json',
    }
    trial_root=ROOT/'jobs'/job
    if job in ['stream-collection-r3','stream-collection-r4']:
        trial_root=ROOT/'stream'/job.removeprefix('stream-')/'trials'
        campaign=json.loads((trial_root.parent/'CAMPAIGN.json').read_text())
        if campaign['native_concurrency']!=8:raise ValueError('Native queue concurrency differs')
        dispatches=[]
        for path in trial_root.parent.glob('dispatches/*/dispatch.json'):
            dispatch=json.loads(path.read_text())
            if dispatch['kind']!='teacher':continue
            config_file=path.parent/'trial-config.json'
            if hashlib.sha256(config_file.read_bytes()).hexdigest()!=dispatch['config_sha256']:raise ValueError('Native TrialConfig changed')
            config=json.loads(config_file.read_text())
            if config['agent']['kwargs']['wheel_sha256']!=campaign['wheel_sha256']:raise ValueError('Native wheel differs')
            if config['agent']['kwargs']['config']!=json.loads((ROOT/'configs/teacher-native-11tools-summary-r1.json').read_text()):raise ValueError('Native teacher contract differs')
            dispatches.append(dispatch)
        submission=dict(job_name=job,requested_attempts=len(dispatches),native_queue_campaign=True)
    elif job in ['cf-tmax-formal-first-pass-summary-r1-20261030','cf-tmax-formal-second-pass-summary-r1-20261030']:
        config_file=ROOT/'jobs'/job/'config.json'
        config=json.loads(config_file.read_text())
        assert config['n_attempts']==1 and config['retry']['max_retries']==0 and config['n_concurrent_trials']==8
        assert config['agents'][0]['name']=='open-harness'
        assert config['agents'][0]['kwargs']['wheel_sha256']=='c686ba3f429d8257a060cf6b6a6e4c5aa7d740f33b2d59180d9a2717b55d0db8'
        assert config['agents'][0]['kwargs']['config']==json.loads((ROOT/'configs/teacher-native-11tools-summary-r1.json').read_text())
        submission=dict(job_name=job,requested_attempts=len(config['tasks']),native_job_config_sha256=hashlib.sha256(config_file.read_bytes()).hexdigest())
    else:
        submission_file = submissions[job]
        submission = json.loads((ROOT / 'checks' / submission_file).read_text())
    expected = json.loads((ROOT / 'checks/offline-teacher-contract.json').read_text())
    rows = []
    cache_hits = cache_misses = 0
    for journal in sorted(trial_root.glob('*/agent/openharness-rollout/events.jsonl')):
        rollout = journal.parent; trial = rollout.parent.parent
        if job in ['stream-collection-r3','stream-collection-r4'] and not (trial/'result.json').exists():continue
        cache_value, cached_row = protocol_cache.lookup(trial, VALID_CACHE_PRODUCER, WHEEL)
        if cached_row is not None:
            rows.append(cached_row)
            cache_hits += 1
            continue
        if cache_value is not None:
            cache_misses += 1
        calls = {}; tools = Counter(); event_counts = Counter(); thinking = 0; models = set(); violations = []; effective = []
        try:
            for line_number, raw in enumerate(journal.read_text().splitlines(), 1):
                event = json.loads(raw); data = event.get('data') or {}; kind = event['type']; event_counts[kind] += 1
                ident = data.get('call_id')
                if kind == 'run_start':
                    config = loadValue(data.get('config'), rollout / 'artifacts')
                    if isinstance(config, dict):
                        if job in ['stream-collection-r3','stream-collection-r4']:violations.extend(runtime_violations(config))
                        effective.append({k: config.get(k) for k in ['cwd','model','resources','retry','branchSummary','toolResultBudget', 'compaction', 'backgroundJobs',
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
                    source = calls.get(ident, {}).get('source')
                    if payload.get('thinking') != {'type': 'enabled'} or payload.get('reasoning_effort') != 'max':
                        violations.append(dict(call_id=ident, source=source, kind='THINKING_CONTRACT_MISMATCH'))
                    if payload.get('max_tokens') != 65536 or payload.get('stream') is not True or payload.get('temperature') != 1:
                        violations.append(dict(call_id=ident, source=source, kind='REQUEST_BUDGET_CONTRACT_MISMATCH'))
                    if payload.get('model') != 'deepseek-flash':
                        violations.append(dict(call_id=ident, source=source, kind='MODEL_CONTRACT_MISMATCH'))
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
        except json.JSONDecodeError as error:
            # Terminal malformed Recorder: retain bytes and reject this Trial,
            # while continuing independent healthy Trial audits.
            result = json.loads((trial / 'result.json').read_text())
            row = dict(trial_directory=str(trial),
                journal_sha256=hashlib.sha256(journal.read_bytes()).hexdigest(),
                event_counts=dict(event_counts), calls=calls, observed_tool_calls=dict(tools),
                effective_runtime_config=effective, raw_thinking_characters_observed=thinking,
                provider_response_models=sorted(models),
                contract_violations=[dict(kind='TERMINAL_RECORDER_JSON_INVALID',
                    line_number=line_number, error_kind=error.msg,
                    partial_prefix_is_not_a_complete_protocol_audit=True)],
                native_result_present=True,
                native_reward=(result.get('verifier_result') or {}).get('rewards'),
                native_exception=(result.get('exception_info') or {}).get('exception_type'),
                qualified_success='REJECTED_INCOMPLETE_OR_INVALID_RECORDER')
            rows.append(row)
            # Invalid JSON cannot pass the cache's complete reference audit.
            # Keep this negative row in the report, never in the valid cache.
            continue
        result_file = trial / 'result.json'
        result = json.loads(result_file.read_text()) if result_file.exists() else None
        rows.append(dict(trial_directory=str(trial), journal_sha256=hashlib.sha256(journal.read_bytes()).hexdigest(),
            event_counts=dict(event_counts), calls=calls, observed_tool_calls=dict(tools), effective_runtime_config=effective,
            raw_thinking_characters_observed=thinking, provider_response_models=sorted(models),
            contract_violations=violations, native_result_present=result is not None,
            native_reward=(result.get('verifier_result') or {}).get('rewards') if result else None,
            native_exception=(result.get('exception_info') or {}).get('exception_type') if result else None,
            qualified_success='NOT_DECIDED_BY_THIS_LIVE_PREFIX_AUDIT'))
        if cache_value is not None:
            protocol_cache.store(trial, cache_value, rows[-1], VALID_CACHE_PRODUCER, WHEEL)
    report = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        status='LIVE_PREFIX_PROTOCOL_OBSERVATION', job_name=submission['job_name'], trials=rows,
        teacher_attempts_requested=submission.get('canary_cohort_attempts_requested',submission.get('requested_attempts')), initial_canary_task_scope=16,
        actual_provider_payload_evidence=True, full_canary_acceptance=False,
        thinking_and_output_contract_scope='ALL_MODEL_CALLS_INCLUDING_AUXILIARY_SUMMARIES',
        recorder_integrity_and_student_conversion_acceptance='PENDING_TERMINAL_AUDIT',
        tool_schema_digest_format='json.dumps(sort_keys=True,ensure_ascii=False), UTF-8 SHA256')
    report['actual_protocol_reader_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['valid_protocol_parser_ast_sha256']=VALID_PARSER_AST_SHA256
    report['terminal_protocol_cache'] = dict(hits=cache_hits, full_scans=cache_misses,valid_row_producer_sha256=hashlib.sha256(VALID_CACHE_PRODUCER.read_bytes()).hexdigest(),
        every_reuse_hashes_all_recorder_files_and_native_result=True, legacy_adoptions=0)
    directory = ROOT/'checks/protocol-cache-r23-seed' if '--cache-seed' in sys.argv else ROOT/'checks'
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / (job+'-live-protocol.json'); temporary = file.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2)); temporary.replace(file)
    print(json.dumps(dict(status=report['status'], trials=[dict(path=r['trial_directory'], calls=len(r['calls']),
        tools=r['observed_tool_calls'], thinking_chars=r['raw_thinking_characters_observed'],
        payloads=sum('payload' in c for c in r['calls'].values()), violations=r['contract_violations'],
        native_reward=r['native_reward']) for r in rows])))


if __name__ == '__main__':
    main()
