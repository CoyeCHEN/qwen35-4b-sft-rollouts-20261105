"""Real protocol parity and corruption tests; no model or container execution."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import time

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
WHEEL = R / 'wheels/open_harness_ai-0.3.0-py3-none-any.whl'
import sys
sys.path.insert(0, str(WHEEL))
import protocol_trial_cache_r23 as cache


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def loop(path):
    module = ast.parse(path.read_text())
    main = next(x for x in module.body if isinstance(x, ast.FunctionDef) and x.name == 'main')
    return next(x for x in main.body if isinstance(x, ast.For) and isinstance(x.target, ast.Name) and x.target.id == 'journal')


def evaluate(path, journals):
    spec = importlib.util.spec_from_file_location('protocol_validation_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    body = copy.deepcopy(loop(path))
    body.iter = ast.Name(id='_journals', ctx=ast.Load())
    tree = ast.fix_missing_locations(ast.Module(body=[body], type_ignores=[]))
    namespace = dict(vars(module), _journals=journals, rows=[], cache_hits=0, cache_misses=0,
        expected=json.loads((R / 'checks/offline-teacher-contract.json').read_text()), job='stream-collection-r4')
    start = time.monotonic()
    exec(compile(tree, str(path), 'exec'), namespace)
    return namespace['rows'], time.monotonic() - start, namespace['cache_hits']


def main():
    baseline = R / 'scripts/audit_native_canary_protocol_before_r23.py'
    producer = R / 'scripts/audit_native_canary_protocol_r23.py'
    assert sha(baseline) == '61a94cd78b32d61ebdea0e1bbb18b88161d22a3cd7301f009f4e4fc57242ba61'
    original_loop = loop(baseline)
    new_loop = copy.deepcopy(loop(producer))
    new_loop.body = [node for node in new_loop.body if not (
        isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and
        isinstance(node.value.func, ast.Attribute) and isinstance(node.value.func.value, ast.Name) and
        node.value.func.value.id == 'protocol_cache'
    ) and not (
        isinstance(node, ast.If) and any(isinstance(x, ast.Name) and x.id in ['cached_row', 'cache_value'] for x in ast.walk(node.test))
    )]
    assert ast.dump(original_loop, include_attributes=False) == ast.dump(new_loop, include_attributes=False)
    checks = ['original_protocol_loop_ast_unchanged']
    original_root, original_policy = cache.CACHE_ROOT, cache.POLICY_FILES
    with tempfile.TemporaryDirectory(prefix='protocol-cache-r23-', dir=R / 'derived') as tmp:
        tmp = Path(tmp)
        cache.CACHE_ROOT = tmp / 'cache'
        policy = tmp / 'policy.json'
        policy.write_text('{}')
        cache.POLICY_FILES = [policy]
        dummy_producer = tmp / 'producer.py'
        dummy_producer.write_text('# producer-a\n')
        trial = tmp / 'trial'
        root = trial / 'agent/openharness-rollout'
        (root / 'artifacts').mkdir(parents=True)
        payload = b'abc'
        digest = hashlib.sha256(payload).hexdigest()
        artifact = root / 'artifacts' / digest
        artifact.write_bytes(payload)
        journal = root / 'events.jsonl'
        journal.write_text(json.dumps(dict(type='fixture', data=dict(value={
            '$artifact':digest, 'size':3, 'encoding':'utf8'}))) + '\n')
        result = trial / 'result.json'
        result.write_text(json.dumps(dict(finished_at='2026-10-30T00:00:00Z',
            verifier_result=dict(rewards=dict(reward=0)), exception_info=None)))
        (trial / 'config.json').write_text('{}')
        row = dict(trial_directory=str(trial), journal_sha256=sha(journal), native_result_present=True,
            native_reward=dict(reward=0), native_exception=None, calls={})
        value, hit = cache.lookup(trial, dummy_producer, WHEEL)
        assert value is not None and hit is None
        cache.store(trial, value, row, dummy_producer, WHEEL)
        assert cache.lookup(trial, dummy_producer, WHEEL)[1] == row
        checks += ['cold_miss_then_content_verified_hit', 'original_artifact_references_verified']
        before = artifact.stat()
        artifact.write_bytes(b'xyz')
        import os
        os.utime(artifact, ns=(before.st_atime_ns, before.st_mtime_ns))
        changed, hit = cache.lookup(trial, dummy_producer, WHEEL)
        assert hit is None and changed != value
        try:
            cache.store(trial, changed, row, dummy_producer, WHEEL)
        except ValueError:
            checks.append('same_size_same_mtime_corruption_misses_and_reference_validation_rejects')
        else:
            raise AssertionError('Corrupt artifact was admitted')
        artifact.unlink()
        changed, hit = cache.lookup(trial, dummy_producer, WHEEL)
        assert hit is None
        try:
            cache.store(trial, changed, row, dummy_producer, WHEEL)
        except ValueError:
            checks.append('missing_artifact_misses_and_reference_validation_rejects')
        else:
            raise AssertionError('Missing artifact was admitted')
        artifact.write_bytes(payload)
        result_bytes = result.read_bytes()
        result.write_text(json.dumps(dict(finished_at='2026-10-30T00:00:00Z', verifier_result=dict(rewards=dict(reward=1)))))
        changed, hit = cache.lookup(trial, dummy_producer, WHEEL)
        assert hit is None
        try:
            cache.store(trial, changed, row, dummy_producer, WHEEL)
        except ValueError:
            checks.append('native_result_change_misses_and_wrong_reward_is_rejected')
        else:
            raise AssertionError('Reward was changed through a cache row')
        result.write_bytes(result_bytes)
        dummy_producer.write_text('# producer-b\n')
        assert cache.lookup(trial, dummy_producer, WHEEL)[1] is None
        dummy_producer.write_text('# producer-a\n')
        policy.write_text('{"changed":true}')
        assert cache.lookup(trial, dummy_producer, WHEEL)[1] is None
        policy.write_text('{}')
        checks += ['producer_change_invalidates', 'expected_policy_change_invalidates']
        proof = next(cache.CACHE_ROOT.glob('*/*.json'))
        proof.write_bytes(proof.read_bytes() + b' ')
        try:
            cache.lookup(trial, dummy_producer, WHEEL)
        except ValueError:
            checks.append('altered_cache_body_rejected_without_fallback')
        else:
            raise AssertionError('Changed cache body accepted')
        result.unlink()
        assert cache.lookup(trial, dummy_producer, WHEEL) == (None, None)
        checks.append('live_prefix_not_memoized_as_terminal')
    cache.CACHE_ROOT, cache.POLICY_FILES = original_root, original_policy
    report = json.loads((R / 'checks/stream-collection-r4-live-protocol.json').read_text())
    eligible = [x for x in report['trials'] if (x.get('native_reward') or {}).get('reward') == 1 and not x['contract_violations'] and len(x['calls']) > 1]
    chosen = min(eligible, key=lambda x:len(x['calls']))
    journals = [Path(chosen['trial_directory']) / 'agent/openharness-rollout/events.jsonl']
    original, original_seconds, _ = evaluate(baseline, journals)
    candidate, candidate_seconds, cold_hits = evaluate(producer, journals)
    reused, reused_seconds, warm_hits = evaluate(producer, journals)
    assert original == candidate == reused and len(original) == 1 and warm_hits == 1
    checks += ['real_terminal_original_full_scan_equals_new_cold_row', 'real_warm_row_equals_original_full_scan']
    summary = dict(passed=True, checks=checks, baseline_source_sha256=sha(baseline),
        candidate_source_sha256=sha(producer), cache_source_sha256=sha(Path(cache.__file__)),
        real_trial=chosen['trial_directory'], real_call_count=len(chosen['calls']),
        real_row_sha256=hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest(),
        original_seconds=original_seconds, candidate_cold_seconds=candidate_seconds,
        candidate_warm_seconds=reused_seconds, cold_cache_hits=cold_hits, warm_cache_hits=warm_hits,
        model_calls=0, original_recorder_or_result_changes=0, teacher_contract_changes=0,
        canonical_reader_activation='NOT_ACTIVATED; full-scope seed and parity check still required')
    with (R / 'checks/protocol-cache-r23-contract-acceptance.json').open('x') as stream:
        json.dump(summary, stream, indent=2)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
