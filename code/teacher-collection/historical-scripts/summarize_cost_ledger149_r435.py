"""Aggregate recorded ledger fields, preserving missing usage and estimate semantics."""
from collections import Counter
from decimal import Decimal
import datetime
import hashlib
import json
from pathlib import Path

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source = R / 'indexes/NATIVE_TRIAL_COST_TOKEN_LEDGER.jsonl'
    digest = sha(source)
    rows = [json.loads(line) for line in source.open()]
    gate = json.loads((R / 'checks/data-finalization-readiness-r370.json').read_text())
    out = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        ledger=str(source), ledger_sha256=digest, ledger_native_trial_records=len(rows), pools={},
        recorded_cost_is_estimate_not_provider_invoice=True,
        cached_input_tokens_are_a_subset_of_input_tokens_not_added_to_them=True,
        missing_or_error_usage_is_not_assumed_zero_billed_cost=True,
        qwen_dataset_lengths_are_separate_from_deepseek_usage=True,
        model_calls=0, task_attempts_changed=0, training_started=False)
    for pool in ['calibforge', 'tmax']:
        records = [row for row in rows if row['pool'] == pool]
        models = {}
        for model in sorted({model for row in records for model in row['model_usage']}):
            usages = [row['model_usage'][model] for row in records if model in row['model_usage']]
            keys = sorted({key for usage in usages for key in usage})
            totals = {}
            for key in keys:
                values = [usage[key] for usage in usages if isinstance(usage.get(key), (int, float))]
                if key == 'cost_usd':
                    totals[key] = str(sum((Decimal(str(value)) for value in values), Decimal(0)))
                else:
                    totals[key] = sum(values)
            models[model] = dict(native_records_reporting_model_usage=len(usages), totals=totals,
                field_reporting_counts={key:sum(key in usage for usage in usages) for key in keys})
        out['pools'][pool] = dict(native_trial_records=len(records),
            native_records_without_model_usage=sum(not row['model_usage'] for row in records),
            distinct_native_trial_ids=len({row['trial_id'] for row in records}),
            actual_or_conservative_attempts=sum(row['attempt_budget_used_actual_or_conservative'] for row in gate['tasks'] if row['pool'] == pool),
            task_status_counts=dict(Counter(row['status'] for row in gate['tasks'] if row['pool'] == pool)),
            recorded_model_usage=models)
    assert sha(source) == digest
    destination = R / 'checks/RECORDED_COST_TOKEN_SUMMARY_R435.json'
    with destination.open('x') as stream:
        json.dump(out, stream, indent=2)
    print(json.dumps(out))


if __name__ == '__main__':
    main()
