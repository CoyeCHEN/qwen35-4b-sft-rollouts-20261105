"""Derived engineering classification and full Recorder ledger; never modify Results."""
from collections import Counter
import json
from pathlib import Path

from foundation.ai.utils.errors import isContextOverflow
from foundation.rollouts.export import RolloutView, loadValue
from eval_audit_new772 import inspect_trial as original_inspect, summary as original_summary


def inspect_trial(directory):
    directory = Path(directory)
    row = original_inspect(directory)
    if row.get('audit_error'):
        row.update(valid_score=False, task_success=False,
                   diagnostic_exclusion_reason='RECORDER_AUDIT_FAILED')
        return row
    if row['protocol_issues'] or not row.get('recorder_validation', {}).get('complete'):
        row.update(valid_score=False, task_success=False,
                   diagnostic_exclusion_reason='RECORDER_OR_PROTOCOL_INCOMPLETE')
    try:
        root = directory / 'agent/openharness-rollout'
        view = RolloutView.open(root)
        calls, _, _, _ = view.rows()
        totals, agent, auxiliary = Counter(), Counter(), Counter()
        last_agent = None
        zero_error_usage = []
        for call in calls:
            response = loadValue(call.get('response', {}), root / 'artifacts') or {}
            usage = response.get('usage') or {}
            current = Counter({k: usage.get(k, 0) for k in ('input', 'output', 'reasoning', 'totalTokens')})
            totals.update(current)
            if call.get('source') == 'agent':
                agent.update(current)
                last_agent = response
            else:
                auxiliary.update(current)
            if response.get('stopReason') in ('error', 'aborted') and not any(current.values()):
                zero_error_usage.append(call['call_id'])
        fatal = bool(last_agent and last_agent.get('stopReason') == 'error'
                     and isContextOverflow(last_agent, 262144))
        result = json.loads((directory / 'result.json').read_text())
        native = (result.get('agent_result') or {}).get('model_usage')
        row.update(fatal_context_overflow=fatal,
                   execution_engineering_failure='UNRECOVERED_CONTEXT_OVERFLOW' if fatal else None,
                   recorder_usage_all_calls=dict(totals), recorder_usage_agent_calls=dict(agent),
                   recorder_usage_auxiliary_calls=dict(auxiliary), raw_harbor_model_usage=native,
                   error_response_zero_usage_calls=zero_error_usage,
                   zero_error_usage_not_claimed_provider_metering=True,
                   raw_result_or_recorder_modified=False)
        if fatal:
            # Preserve raw official scoring validity and reward. Execution qualification
            # is a separate result, and cannot turn a framework failure into model zero.
            row['valid_score'] = False
            row['task_success'] = False
            row['diagnostic_exclusion_reason'] = 'UNRECOVERED_CONTEXT_OVERFLOW'
    except Exception as error:
        row['audit_error'] = type(error).__name__ + ': ' + str(error)
        row.update(valid_score=False, task_success=False,
                   diagnostic_exclusion_reason='RECORDER_ACCOUNTING_AUDIT_FAILED')
    return row


def summary(rows, expected):
    result = original_summary(rows, expected)
    result['context_recovery_terminations'] = sum(r.get('fatal_context_overflow', False) for r in rows)
    result['recorder_usage_all_calls'] = {
        k: sum((r.get('recorder_usage_all_calls') or {}).get(k, 0) for r in rows)
        for k in ('input', 'output', 'reasoning', 'totalTokens')}
    return result
