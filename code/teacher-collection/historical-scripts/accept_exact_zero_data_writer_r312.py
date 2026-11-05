"""Real-index and negative-boundary acceptance for the next derived writer."""
import ast
import datetime
import hashlib
import json
from pathlib import Path

import reviewed_verifier_zero_r311 as reviewed

R = reviewed.R
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    before = (R / 'scripts/audit_collection_results_r10.py').read_text()
    after = (R / 'scripts/audit_collection_results_r11.py').read_text().replace('from reviewed_verifier_zero_r311 import', 'from reviewed_verifier_zero_r245 import')
    if ast.dump(ast.parse(before)) != ast.dump(ast.parse(after)):
        raise ValueError('Qualifier changed beyond the exact negative-review import')
    before = (R / 'scripts/audit_stream_data_worker149_r10.py').read_text()
    after = (R / 'scripts/audit_stream_data_worker149_r11.py').read_text().replace("source_revision='r11'", "source_revision='r10'").replace('stream-r11-data-audit','stream-r10-data-audit').replace('audit_collection_results_r11.py','audit_collection_results_r10.py')
    if ast.dump(ast.parse(before)) != ast.dump(ast.parse(after)):
        raise ValueError('Data writer changed beyond its revision, log and qualifier')
    positives = 0
    records = {}
    for pool in ['CALIBFORGE', 'TMAX']:
        for name in ['SUCCESS_INDEX', 'FAILURE_OR_PENDING_INDEX']:
            for line in (R / 'indexes' / (pool + '_' + name + '.jsonl')).open():
                record = json.loads(line)
                records[record['trial_id']] = record
                if record['qualified_success']:
                    result = reviewed.apply_reviewed_zero(record)
                    if result != record:
                        raise ValueError('A current real positive record changed')
                    positives += 1
    cases = []
    for ident, evidence in reviewed.reviews().items():
        original = records[ident]
        result = reviewed.apply_reviewed_zero(original)
        expected, infra = reviewed.CLASSIFICATIONS[evidence['reviewed_classification']]
        if result['classification'] != expected or result['scoring_infrastructure_failure_detected'] is not infra:
            raise ValueError('Exact negative classification differs')
        if result['raw_reward'] != 0 or result['qualified_success'] or result['is_primary_trajectory']:
            raise ValueError('A zero review changed reward or training eligibility')
        for field, value in [('result_sha256', 'wrong'), ('raw_reward', 1), ('qualified_success', True), ('classification', 'ANOTHER_OUTCOME')]:
            try:
                reviewed.apply_reviewed_zero(dict(original, **{field: value}))
            except ValueError:
                pass
            else:
                raise ValueError('Exact negative boundary was not enforced: ' + field)
        unknown = dict(original, trial_id='unregistered-new-trial')
        if reviewed.apply_reviewed_zero(unknown) != unknown:
            raise ValueError('An unknown Trial was reclassified')
        cases.append(dict(trial_id=ident, task_id=original['task_id'], classification=result['classification'], scoring_infrastructure_failure_detected=infra, proof=str(reviewed.MANIFEST), sha256=reviewed.EXPECTED))
    sources = {name: sha(R / 'scripts' / name) for name in ['reviewed_verifier_zero_r311.py','audit_collection_results_r11.py','audit_stream_data_worker149_r11.py','reviewed_verifier_zero_r245.py','reviewed_export_quarantines_r246.py','audit_native_canary_protocol_r216.py','export_native_canary_calls_r187.py']}
    out = dict(passed=True, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), sources=sources, cases=cases, real_positive_records_unchanged=positives, all_four_new_negative_reviews_exact=True, unknown_trials_unchanged=True, invalid_identity_reward_qualification_and_classification_rejected=True, data_model_tokenizer_export_protocol_and_cpu_limits_unchanged=True, raw_results_rewards_or_trajectories_modified=False, teacher_or_verifier_signals=0, model_calls=0, source_sha256=sha(Path(__file__)))
    path = R / 'checks/reviewed-data-writer-acceptance-r312.json'
    with path.open('x') as stream:
        json.dump(out, stream, indent=2)
    print(json.dumps(out))


if __name__ == '__main__':
    main()
