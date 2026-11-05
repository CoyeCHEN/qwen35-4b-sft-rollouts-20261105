"""Frozen metric: a valid timeout success is distinct from normal completion."""
import ast
import argparse
import copy
from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).parent


def functions(name):
    tree = ast.parse((ROOT / name).read_text())
    return [node for node in tree.body if isinstance(node, ast.FunctionDef)
            and node.name in ['aggregate', 'scoring_admitted']]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rows', type=Path, default=ROOT / 'checks/DIAGNOSTIC30_MATRIX_ROWS_R1.jsonl')
    args = parser.parse_args()
    old, new = dict(Counter=Counter), dict(Counter=Counter)
    for name, namespace in [('compare-formal801-readonly-r7.py', old),
                            ('compare-formal801-readonly-r8.py', new)]:
        exec(compile(ast.Module(body=functions(name), type_ignores=[]), name, 'exec'), namespace)
    rows = [json.loads(line) for line in args.rows.open()]
    native = next(row for row in rows if row['task_id'] == 'video-processing')
    assert native['raw_official_score_valid'] and native['exception_type'] == 'AgentTimeoutError'
    assert not native['trajectory_complete'] and not native['protocol_issues'] and not native.get('audit_error')
    before = copy.deepcopy(native)
    assert old['aggregate']([native], 1)['unknown'] == 1
    fixed = new['aggregate']([native], 1)
    assert fixed['unknown'] == 0 and fixed['official_scoring_valid'] == 1
    assert native == before and native['reward']['reward'] == 0
    base = copy.deepcopy(native)
    base.update(raw_official_score_valid=True, valid_score=True, protocol_issues=[],
        audit_error=None, fatal_model_transport_error=False, fatal_context_overflow=False,
        unresolved_terminal_tool_identity_response=False, reward={'reward': 1},
        infrastructure_errors=[], trajectory_complete=True, normal_close=True,
        exception_type=None)
    cases = [
        ('normal_success', {}, 1, 1, 0),
        ('timeout_success_incomplete_recorder', dict(valid_score=False, normal_close=False,
            trajectory_complete=False, exception_type='AgentTimeoutError'), 1, 0, 0),
        ('timeout_zero', dict(valid_score=False, trajectory_complete=False,
            exception_type='AgentTimeoutError', reward={'reward': 0}), 0, 0, 0),
        ('invalid_verifier', dict(raw_official_score_valid=False), 0, 0, 1),
        ('unresolved_tool_identity', dict(unresolved_terminal_tool_identity_response=True), 0, 0, 1),
        ('unrecovered_backend', dict(fatal_model_transport_error=True), 0, 0, 1),
        ('unrecovered_overflow', dict(fatal_context_overflow=True), 0, 0, 1),
        ('wrong_tool_contract', dict(protocol_issues=['tool_contract:call']), 0, 0, 1),
        ('broken_recorder_artifact', dict(audit_error='Missing artifact'), 0, 0, 1),
        ('repaired_model_argument_errors', dict(tool_argument_invalid=3), 1, 1, 0),
    ]
    for name, updates, success, normal, unknown in cases:
        row = copy.deepcopy(base)
        row.update(updates)
        result = new['aggregate']([row], 1)
        assert result['confirmed_reward_successes'] == success, name
        assert result['normal_complete_successes'] == normal, name
        assert result['unknown'] == unknown, name
        if name == 'timeout_success_incomplete_recorder':
            assert result['timeout_reward_successes'] == 1
            assert result['protocol_and_recorder_qualified'] == 0
    print(json.dumps(dict(passed=True, synthetic_boundary_cases=len(cases),
        actual_closed_native_timeout_row_reclassified_from_unknown_to_valid_reward_zero=True,
        original_native_result_sha256=native['result_sha256'],
        original_reward_or_rows_modified=False, actual_model_or_task_calls=0,
        frozen_metric_spec_unchanged=True)))


if __name__ == '__main__':
    main()
