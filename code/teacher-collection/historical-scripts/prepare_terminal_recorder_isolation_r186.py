"""Prepare versioned derived-audit candidates; never edit frozen entry points."""
import ast
import hashlib
from pathlib import Path

R = Path(__file__).parent


def write(name, text):
    ast.parse(text)
    with (R / name).open('x') as stream:
        stream.write(text)
    print(name, hashlib.sha256(text.encode()).hexdigest())


source = (R / 'audit_native_canary_protocol.py').read_text()
begin = source.index('        for raw in journal.read_text().splitlines():')
end = source.index('        result_file = trial /', begin)
block = source[begin:end].replace('for raw in journal.read_text().splitlines():',
    'for line_number, raw in enumerate(journal.read_text().splitlines(), 1):', 1)
failure = '''        except json.JSONDecodeError as error:
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
            if cache_value is not None:
                protocol_cache.store(trial, cache_value, row, Path(__file__), WHEEL)
            continue
'''
write('audit_native_canary_protocol_r186.py', source[:begin] + '        try:\n' +
      ''.join('    ' + line if line.strip() else line for line in block.splitlines(keepends=True)) + failure + source[end:])

source = (R / 'export_native_canary_calls_r8.py').read_text()
begin = source.index('        for line in journal.open():')
end = source.index('        result=json.loads', begin)
block = source[begin:end].replace('for line in journal.open():',
    'for line_number, line in enumerate(journal.open(), 1):', 1)
failure = '''        except json.JSONDecodeError as error:
            result=json.loads((trial/'result.json').read_text())
            report.append(dict(trial_id=result['id'],task_name=result['task_name'],source_trial=str(trial),
                source_journal_sha256=journal_sha256,agent_calls=None,exported=0,
                errors=[dict(kind='TERMINAL_RECORDER_JSON_INVALID',line_number=line_number,error_kind=error.msg)],
                cost_token_ledger_complete=False,raw_attempts_preserved=True,
                reward=(result.get('verifier_result') or {}).get('rewards'),
                sft_admission='REJECTED_INVALID_RECORDER; no partial export or reconstructed history'))
            # No invented call ID or zero usage. Previously recorded call
            # accounting remains, and this report explicitly records its gap.
            ledger.extend(previous_ledger.get(result['id'], []))
            report[-1]['billing_status']='UNKNOWN_INCOMPLETE_RECORDER_NOT_ZERO'
            continue
'''
source = source[:begin] + '        try:\n' + ''.join('    ' + line if line.strip() else line for line in block.splitlines(keepends=True)) + failure + source[end:]
source = source.replace("cached=reuse_export(trial,immutable_inputs,previous.get(trial_identity),previous_ledger.get(trial_identity,[]))",
    "previous_row=previous.get(trial_identity)\n        if previous_row is not None and 'export' not in previous_row:previous_row=None\n        cached=reuse_export(trial,immutable_inputs,previous_row,previous_ledger.get(trial_identity,[]))")
write('export_native_canary_calls_r187.py', source)

source = (R / 'audit_stream_data_worker149_r6.py').read_text()
source = source.replace("source_revision='r6'", "source_revision='r7'")
source = source.replace("logs/stream-r6-data-audit.log", "logs/stream-r7-data-audit.log")
source = source.replace("script('audit_native_canary_protocol.py'", "script('audit_native_canary_protocol_r186.py'")
source = source.replace("script('export_native_canary_calls.py'", "script('export_native_canary_calls_r187.py'")
source = source.replace("if merged or changed:script('audit_collection_results.py')",
    "if merged or changed:\n    script('audit_collection_results.py')\n    errors.pop('worker_observation',None)")
write('audit_stream_data_worker149_r7.py', source)
