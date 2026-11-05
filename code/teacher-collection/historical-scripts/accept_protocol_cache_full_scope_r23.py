"""Compare every seeded row to the original scanner, then rehash/replay all."""
import datetime
import hashlib
import json
from pathlib import Path

from accept_protocol_cache_r23 import evaluate, sha

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


def main():
    contract = json.loads((R / 'checks/protocol-cache-r23-contract-acceptance.json').read_text())
    assert contract['passed']
    baseline = R / 'scripts/audit_native_canary_protocol_before_r23.py'
    producer = R / 'scripts/audit_native_canary_protocol_r23.py'
    assert sha(baseline) == contract['baseline_source_sha256']
    assert sha(producer) == contract['candidate_source_sha256']
    assert sha(R / 'scripts/protocol_trial_cache_r23.py') == contract['cache_source_sha256']
    root = R / 'checks/protocol-cache-r23-seed'
    source = root / 'stream-collection-r4-live-protocol.json'
    blob = source.read_bytes()
    cold = json.loads(blob)
    with (root / 'SEED_COLD_REPORT_R23.json').open('xb') as stream:
        stream.write(blob)
    expected = {x['trial_directory']:x for x in cold['trials']}
    assert len(expected) == len(cold['trials']) and expected
    legacy_path = R / 'checks/stream-collection-r4-live-protocol.json'
    legacy_blob = legacy_path.read_bytes()
    with (root / 'LEGACY_BASELINE_REPORT_R23.json').open('xb') as stream:
        stream.write(legacy_blob)
    legacy = json.loads(legacy_blob)
    original = {x['trial_directory']:x for x in legacy['trials']}
    extra = sorted(set(expected) - set(original))
    extra_rows, extra_seconds, _ = evaluate(baseline,
        [Path(x) / 'agent/openharness-rollout/events.jsonl' for x in extra])
    original.update({x['trial_directory']:x for x in extra_rows})
    for ident, row in expected.items():
        if original[ident] != row:
            raise ValueError('Seeded protocol row differs from unchanged original scanner: ' + ident)
    journals = [Path(x['trial_directory']) / 'agent/openharness-rollout/events.jsonl' for x in cold['trials']]
    warm, seconds, hits = evaluate(producer, journals)
    if warm != cold['trials'] or hits != len(expected):
        raise ValueError('Full seeded scope warm replay changed a row or failed content reuse')
    proof = dict(passed=True, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_sha256=sha(Path(__file__)), baseline_source_sha256=sha(baseline),
        producer_source_sha256=sha(producer), cache_source_sha256=contract['cache_source_sha256'],
        cold_seed_report_sha256=hashlib.sha256(blob).hexdigest(),
        legacy_baseline_report_sha256=hashlib.sha256(legacy_blob).hexdigest(),
        seeded_terminal_trial_rows=len(expected), existing_original_rows_compared=len(expected) - len(extra),
        additional_rows_recomputed_by_original_scanner=len(extra), original_extra_rows_seconds=extra_seconds,
        all_seeded_rows_equal_original_full_scan=True, warm_rehashed_trial_rows=hits,
        warm_scope_seconds=seconds, all_warm_rows_equal_original_full_scan=True,
        original_loop_ast_parity=contract['checks'][0], all_recorders_and_native_results_rehashed=True,
        model_calls=0, source_or_task_or_result_changes=0, teacher_contract_changes=0,
        canonical_reader_activation='NOT_YET_ACTIVATED')
    with (R / 'checks/protocol-cache-r23-full-scope-acceptance.json').open('x') as stream:
        json.dump(proof, stream, indent=2)
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
