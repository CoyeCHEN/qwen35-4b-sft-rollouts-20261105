"""Review one recorded malformed tool call without repairing or dropping it."""
import hashlib
import json
from pathlib import Path

from export_native_canary_calls_r8 import loadValue, raw_response

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
TRIAL = '36fb2a86-9897-499b-8f73-ec42079c18bd'
CALL = 'aa468b80-1111-4e6b-9647-e45e402a0617'


def review(item, export):
    if item['trial_id'] != TRIAL or export['trial_id'] != TRIAL:
        raise ValueError('Unreviewed export error remains pending')
    if len(export['errors']) != 1 or export['errors'][0]['call_id'] != CALL:
        raise ValueError('Reviewed malformed-call scope changed')
    result = Path(item['result_path'])
    if hashlib.sha256(result.read_bytes()).hexdigest() != item['result_sha256']:
        raise ValueError('Original Result changed')
    journal = result.parent / 'agent/openharness-rollout/events.jsonl'
    if hashlib.sha256(journal.read_bytes()).hexdigest() != item['source_journal_sha256']:
        raise ValueError('Original Recorder changed')
    chunks = []
    for line in journal.open():
        event = json.loads(line)
        data = event.get('data') or {}
        if event['type'] == 'call_chunk' and data.get('call_id') == CALL:
            value = loadValue(data['chunk'], journal.parent / 'artifacts')
            if isinstance(value, str) and value.strip() == '[DONE]':
                continue
            value = json.loads(value) if isinstance(value, str) else value
            if isinstance(value, dict):
                chunks.append(value)
    response = raw_response(chunks)
    invalid = []
    for call in response.get('tool_calls', []):
        arguments = call['function']['arguments']
        try:
            json.loads(arguments)
        except json.JSONDecodeError as error:
            invalid.append(dict(call_id=CALL, tool_name=call['function']['name'],
                raw_arguments_sha256=hashlib.sha256(arguments.encode()).hexdigest(),
                raw_arguments_characters=len(arguments), parser_error=str(error)))
    if not invalid or not any(x['parser_error'] == export['errors'][0]['reason'] for x in invalid):
        raise ValueError('Cannot reproduce the exact raw-SSE malformed tool argument')
    disposition_file = Path(export['call_dispositions'])
    if hashlib.sha256(disposition_file.read_bytes()).hexdigest() != export['call_dispositions_sha256']:
        raise ValueError('Original call-disposition identity changed')
    dispositions = json.loads(disposition_file.read_text())
    if dispositions['source_journal_sha256'] != item['source_journal_sha256']:
        raise ValueError('Call dispositions refer to another Recorder')
    ids = [x['call_id'] for x in dispositions['calls'] if x['source'] == 'agent'
           and x['disposition'] != 'RECOVERED_EMPTY_TRANSPORT_CALL_NO_ASSISTANT_TARGET']
    if CALL not in ids or len(ids) != len(set(ids)) or len(ids) != export['agent_calls']:
        raise ValueError('Original Assistant target set is incomplete')
    reason = 'Raw model tool arguments are invalid JSON and cannot round-trip through the frozen Qwen tool schema; retain whole raw Trial, do not delete this call or admit its partial export'
    evidence = dict(trial_id=TRIAL, call_id=CALL, original_result_sha256=item['result_sha256'],
        source_journal_sha256=item['source_journal_sha256'], original_assistant_targets=ids,
        canonical_export_sha256=export['export_sha256'], exported_targets=export['exported'],
        malformed_tool_arguments=invalid, call_dispositions_sha256=export['call_dispositions_sha256'],
        quarantine_reason=reason, partial_export_admitted=False, raw_response_repaired=False,
        original_result_or_recorder_modified=False, new_model_calls=0,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    blob = json.dumps(evidence, indent=2).encode()
    digest = hashlib.sha256(blob).hexdigest()
    incoming = R / 'derived/stream-student-export-quarantine-r164' / TRIAL
    relative = Path('checks/student-proof-artifacts') / (digest + '.json')
    path = incoming / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == blob
    else:
        with path.open('xb') as stream:
            stream.write(blob)
    entry = dict(trial_id=TRIAL, task_name=export['task_name'], semantic_projection_passed=False,
        all_original_targets_once=False, original_call_ids=ids, source_journal_sha256=item['source_journal_sha256'],
        raw_export_sha256=export['export_sha256'], native_loader_and_collator_passed=False,
        native_streaming_and_nonstreaming_parsers_passed=False, quarantine_class='UNREPRESENTABLE_TOOL_ARGUMENTS',
        quarantine_reasons=[reason, *[x['parser_error'] for x in invalid]],
        affected_targets=len(invalid), partial_text_prefixes_not_admitted=True, source_reward_checked_separately=True)
    proof = incoming / 'checks/STUDENT_AUDIT_TRIALS_ALL.json'
    report = dict(entries=[entry], proofs={'malformed-tool-arguments-r164.json':
        dict(path=str(path), relative_path=str(relative), sha256=digest)},
        does_not_approve_reward_or_task_provenance=True)
    text = json.dumps(report, indent=2)
    if proof.exists():
        assert proof.read_text() == text
    else:
        with proof.open('x') as stream:
            stream.write(text)
    return proof
