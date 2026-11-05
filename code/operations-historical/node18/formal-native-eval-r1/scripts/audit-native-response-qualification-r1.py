"""Conservative derived qualification of terminal tool-identity response errors.

Keep the official score and existing native audits. A missing wire identity with
a tool_calls finish cannot yet distinguish generated markup from Serving parsing.
Only this unresolved terminal condition is excluded; recovered errors and model
argument/schema mistakes retain their original qualification.
"""
from collections import Counter
import importlib
import json
from pathlib import Path

from foundation.rollouts.export import loadValue

base = importlib.import_module('audit-native-context-accounting-r2')


def qualify(row, last_response, wire):
    unresolved = bool(last_response.get('stopReason') == 'error'
                      and last_response.get('rawStopReason') == 'tool_calls'
                      and last_response.get('errorMessage') == 'Incomplete tool call identity')
    row.update(unresolved_terminal_tool_identity_response=unresolved,
               native_terminal_tool_identity_wire=wire if unresolved else None)
    if unresolved:
        row.update(valid_score=False, task_success=False,
                   diagnostic_exclusion_reason='UNRESOLVED_MODEL_OR_SERVING_TOOL_IDENTITY_RESPONSE',
                   response_origin_unresolved=True,
                   raw_official_reward_not_rewritten=True)
    return row


def terminal_response(directory):
    root = Path(directory) / 'agent/openharness-rollout'
    starts = {}
    last = None
    for line in (root / 'events.jsonl').open('rb'):
        event = json.loads(line)
        data = event['data']
        if event['type'] == 'call_start':
            starts[data['call_id']] = data['source']
        elif event['type'] == 'call_end' and starts[data['call_id']] == 'agent':
            last = (data['call_id'], loadValue(data.get('response'), root / 'artifacts') or {})
    if last is None:
        return {}, None
    call_id, response = last
    if not (response.get('errorMessage') == 'Incomplete tool call identity'
            and response.get('rawStopReason') == 'tool_calls'):
        return response, None
    indices = {}
    finishes = []
    done = 0
    chunks = 0
    for line in (root / 'events.jsonl').open('rb'):
        event = json.loads(line)
        data = event['data']
        if event['type'] != 'call_chunk' or data['call_id'] != call_id:
            continue
        raw = loadValue(data['chunk'], root / 'artifacts')
        chunks += 1
        if raw == '[DONE]':
            done += 1
            continue
        chunk = json.loads(raw)
        for choice in chunk.get('choices', []):
            if choice.get('index', 0) != 0:
                continue
            if choice.get('finish_reason'):
                finishes.append(choice['finish_reason'])
            for tool in (choice.get('delta') or {}).get('tool_calls') or []:
                state = indices.setdefault(str(tool.get('index')), dict(id_seen=False, name_seen=False))
                state['id_seen'] |= bool(tool.get('id'))
                state['name_seen'] |= bool(tool.get('function', {}).get('name'))
    return response, dict(call_id=call_id, native_sse_chunks=chunks,
                          done_markers=done, finish_reasons=finishes, indices=indices,
                          identity_missing_on_wire=bool(indices) and any(
                              not v['id_seen'] or not v['name_seen'] for v in indices.values()),
                          cause_not_attributed_to_model_or_serving=True)


def inspect_trial(directory):
    row = base.inspect_trial(directory)
    if row.get('audit_error'):
        return row
    try:
        response, wire = terminal_response(directory)
        return qualify(row, response, wire)
    except Exception as error:
        row.update(valid_score=False, task_success=False,
                   audit_error='ResponseQualification: ' + repr(error),
                   diagnostic_exclusion_reason='RESPONSE_QUALIFICATION_AUDIT_FAILED')
        return row


def summary(rows, expected):
    result = base.summary(rows, expected)
    result.update(unresolved_terminal_tool_identity_responses=sum(
        r.get('unresolved_terminal_tool_identity_response', False) for r in rows),
        unknown_terminal_trials=sum(not r['valid_score'] or bool(r['protocol_issues'])
                                    or bool(r.get('audit_error')) for r in rows),
        raw_native_infrastructure_error_list_nonempty=sum(bool(r['infrastructure_errors']) for r in rows),
        failure_phase_counts=dict(Counter(r['failure_phase'] for r in rows)),
        qualification_exclusion_counts=dict(Counter(r.get('diagnostic_exclusion_reason') for r in rows
                                                    if not r['valid_score'])))
    return result
