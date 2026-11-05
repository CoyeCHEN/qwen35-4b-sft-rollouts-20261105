"""Compact numerical evidence for the complete 772-primary partial cache audit."""
import datetime
import hashlib
import json
from pathlib import Path

S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
D = S / 'data-corpus-snapshots/r426'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
read = lambda path: json.loads(path.read_text())


def main():
    source = D / 'DATA_AUDIT_PARTIAL.json'
    assert sha(source) == '24430fbef7e873c508b3c699b9cd9854dd602571bc9834ec2dc168b4d81bea41'
    audit = read(source)
    assert audit['full_campaign_complete'] is False and audit['formal_corpus_release'] is False
    out = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        status='ALL_AVAILABLE_772_PRIMARY_TASKS_FULL_NATIVE_CACHE_AUDIT_PASSED',
        source=str(source), data_audit_sha256=sha(source), pools={},
        full_campaign_complete=False, formal_release=False, model_calls=0, training_started=False)
    count_fields = ['qualified_tasks', 'semantically_projected_tasks', 'retained_independent_tasks',
        'complete_tasks', 'closing_tasks', 'original_targets', 'retained_targets', 'segments',
        'multi_assistant_samples', 'supervised_tokens', 'input_plus_target_qwen_tokens']
    for pool, proof in audit['pools'].items():
        manifest_path = D / pool / 'DATA_MANIFEST.json'
        native_path = D / pool / 'NATIVE_CACHE_AUDIT.json'
        manifest, native = read(manifest_path), read(native_path)
        assert sha(manifest_path) == proof['manifest_sha256'] == native['manifest_sha256']
        assert sha(native_path) == proof['formal_loader_audit_sha256']
        assert native['passed'] and native['all_row_labels_checked']
        assert native['all_caches_and_both_fixed_splits_read_through_formal_loader']
        assert native['numerical_reference']['passed'] and native['numerical_reference']['maximum_gradient_error'] == 0
        assert not native['cuda_initialized'] and not native['model_loaded_for_training']
        views = {}
        for cap, splits in manifest['length_views'].items():
            totals = {key: sum(view[key] for view in splits.values()) for key in count_fields}
            for key in ['supervision_token_classes', 'stage_target_counts']:
                totals[key] = {label:sum(view[key][label] for view in splits.values())
                    for label in next(iter(splits.values()))[key]}
            assert sum(totals['supervision_token_classes'].values()) == totals['supervised_tokens']
            assert sum(totals['stage_target_counts'].values()) == totals['retained_targets']
            lengths = sorted(row['collated_tokens'] for row in native['rows'] if str(row['cutoff']) == cap)
            assert len(lengths) == totals['segments'] and max(lengths) <= int(cap)
            totals['collated_token_length_quantiles'] = {str(q): lengths[round((len(lengths)-1)*q)]
                for q in [0, 0.5, 0.9, 0.95, 0.99, 1]}
            totals['fixed_split_qualified_tasks'] = {name: view['qualified_tasks'] for name, view in splits.items()}
            totals['overlong_original_targets_separately_quarantined'] = totals['original_targets'] - totals['retained_targets']
            views[cap] = totals
        assert views['262144']['complete_tasks'] == manifest['qualified_independent_tasks']
        out['pools'][pool] = dict(qualified_independent_tasks=manifest['qualified_independent_tasks'],
            cached_rows_both_views=len(native['rows']), all_labels_checked=True,
            numerical_reference=native['numerical_reference'], length_views=views,
            manifest_path=str(manifest_path), manifest_sha256=sha(manifest_path),
            formal_loader_audit_sha256=sha(native_path),
            fixed_family_splits_checked=True, per_task_weight_metadata_checked=native['sample_mean_weight_metadata_checked'])
    out['snapshot_qualified_independent_tasks'] = sum(p['qualified_independent_tasks'] for p in out['pools'].values())
    assert out['snapshot_qualified_independent_tasks'] == 772
    destination = S / 'metadata-snapshots/FORMAL_AVAILABLE_CACHE_AUDIT_SUMMARY_R434.json'
    with destination.open('x') as stream:
        json.dump(out, stream, indent=2)
    print(json.dumps(dict(proof=str(destination), sha256=sha(destination),
        tasks=out['snapshot_qualified_independent_tasks'], pools={name:p['length_views'] for name,p in out['pools'].items()})))


if __name__ == '__main__':
    main()
