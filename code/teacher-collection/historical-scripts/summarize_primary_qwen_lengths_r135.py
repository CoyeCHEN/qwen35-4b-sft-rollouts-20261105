"""Aggregate existing per-Trial Qwen audits; no new cache/final-loader claim."""
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


def main():
    result = dict(status='PARTIAL_METADATA_AGGREGATION_OF_ACCEPTED_PER_TRIAL_QWEN_AUDITS',
        checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        formal_corpus_release=False, final_assembled_cache_loader_audit=False,
        training_started=False, model_calls=0, pools={},
        scope='Accepted per-Trial native Qwen/processor lengths and supervision summaries. This does not repeat token/label or full assembled corpus Loader audits. Historical R12 full-cache audit remains separately identified.')
    for pool in ['calibforge', 'tmax']:
        path = R / 'indexes' / (pool.upper() + '_SUCCESS_INDEX.jsonl')
        raw = path.read_bytes()
        rows = [json.loads(line) for line in raw.splitlines()]
        if len({item['task_id'] for item in rows}) != len(rows):
            raise ValueError('Repeated primary Task identity')
        counts = dict(qualified_independent_tasks=len(rows), primary_trajectories=len(rows),
            source_index=str(path), source_index_sha256=hashlib.sha256(raw).hexdigest(),
            fixed_splits=dict(Counter(item['split'] for item in rows)), original_assistant_targets=0,
            trajectories_with_multiple_assistant_targets=0, original_supervision_token_classes={}, length_views={})
        classes = Counter()
        for item in rows:
            if not item['qualified_success'] or not item['is_primary_trajectory']:
                raise ValueError('Unqualified source entered the inventory')
            proof = item['student_proof']
            for key in ['exact_deployment_prefixes', 'all_original_targets_once',
                'native_loader_and_collator_passed', 'native_loss_gradient_reference_passed']:
                if not proof[key]:
                    raise ValueError('Required accepted per-Trial evidence is absent')
            counts['original_assistant_targets'] += len(proof['original_call_ids'])
            counts['trajectories_with_multiple_assistant_targets'] += len(proof['original_call_ids']) > 1
            classes.update(proof['supervision_token_classes'])
        counts['original_supervision_token_classes'] = dict(classes)
        for cutoff in ['131072', '262144']:
            totals = Counter()
            weights = []
            for item in rows:
                proof = item['student_proof']
                view = proof['length_views'][cutoff]
                original = proof['original_call_ids']
                removed = {entry['call_id'] for entry in view['quarantine']}
                if view['targets'] != len(original) - len(removed) or len(view['collated_lengths']) != view['segments']:
                    raise ValueError('Accepted target/segment inventory differs')
                if any(length > int(cutoff) for length in view['collated_lengths']):
                    raise ValueError('Actual native collated input+target length exceeds its view')
                totals.update(assistant_targets=view['targets'], derived_segments=view['segments'],
                    supervised_qwen_tokens=view['supervised_tokens'], quarantined_targets=len(removed),
                    input_plus_target_qwen_tokens=sum(view['collated_lengths']),
                    tasks_with_retained_targets=view['targets'] > 0,
                    tasks_with_all_original_targets=len(removed) == 0,
                    normal_closure_last_target_retained=bool(original and original[-1] not in removed))
                weights.append(dict(task_id=item['task_id'], trial_id=item['trial_id'],
                    retained_targets=view['targets'], supervised_qwen_tokens=view['supervised_tokens']))
            for item in weights:
                item['share_of_pool_supervision_tokens'] = item['supervised_qwen_tokens'] / totals['supervised_qwen_tokens'] if totals['supervised_qwen_tokens'] else 0
            counts['length_views'][cutoff] = dict(totals, task_supervision_contributions=weights,
                lengths='Native Qwen input+target including the fixed processor and actual padding. DeepSeek usage is not used.',
                cached_sample_count_not_recomputed=True)
        result['pools'][pool] = counts
    path = R / 'checks/current-primary-qwen-length-inventory-r135.json'
    with path.open('x') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({pool:{key:value for key,value in item.items() if key in
        ['qualified_independent_tasks', 'original_assistant_targets', 'trajectories_with_multiple_assistant_targets']}
        for pool,item in result['pools'].items()}))


if __name__ == '__main__':
    main()
