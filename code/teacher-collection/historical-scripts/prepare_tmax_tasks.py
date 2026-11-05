"""Finalize source candidates with audited, fixed-stratum pre-model reserves.

The previous source-only passes are preserved. This pass incorporates the
observed hidden expected files; it does not approve images or run teachers.
"""
from collections import Counter, defaultdict
import datetime
import hashlib
import json
from pathlib import Path
import zipfile

import prepare_tmax_sources as source_io

ROOT = source_io.ROOT
adapter = source_io.adapter


def inspect_candidate(z, row, members):
    source = source_io.materialize(z, row['task_id'], members[row['task_id']])
    if adapter.digest(source / 'task.json') != row['task_json_sha256']:
        raise ValueError('Frozen candidate source identity changed')
    native = adapter.load_native_converter(ROOT / 'scripts/upstream-convert-to-harbor.py')
    receipt = adapter.inspect_source(source, native)
    target = ROOT / 'tasks/tmax' / row['task_id']
    if not target.exists():
        receipt = adapter.convert_task(source, ROOT / 'tasks/tmax',
            native_converter=ROOT / 'scripts/upstream-convert-to-harbor.py',
            intricate_base_definition=ROOT / 'scripts/base_intricate.def')
    else:
        metadata = json.loads((source / 'task.json').read_text())
        expected = {'instruction.md': metadata['description'].encode(),
            'tests/test_final_state.py': (source / 'test_final_state.py').read_bytes(),
            'tests/test.sh': native.TEST_SH.encode(),
            'task.toml': native.generate_task_toml(metadata,
                source='v2' if metadata.get('base_image') == 'intricate' else 'legacy').encode()}
        for relative, raw in expected.items():
            if (target / relative).read_bytes() != raw:
                raise ValueError('Existing native conversion identity changed: ' + row['task_id'] + '/' + relative)
        receipt.update(status='EXISTING_NATIVE_CONVERSION_REVERIFIED',
            converter_sha256=adapter.CONVERTER_SHA256,
            original_source_unchanged=True, task_toml_sha256=adapter.digest(target / 'task.toml'))
    return dict(receipt, adapter_sha256=adapter.digest(ROOT / 'scripts/tmax_adapter.py'),
        task_path=str(target), image_setup_verifier_status='PENDING')


def main():
    output = ROOT / 'manifests/TMAX_PREPARED_TASKS.jsonl'
    ledger = ROOT / 'manifests/TMAX_PREPARATION_REPLACEMENTS.jsonl'
    if output.exists() or ledger.exists():
        raise FileExistsError('Final source preparation identities exist; inspect rather than overwrite')
    selected_file = ROOT / 'manifests/TMAX_500_TASKS.jsonl'
    reserve_file = ROOT / 'manifests/TMAX_RESERVES.jsonl'
    selected = list(map(json.loads, selected_file.open()))
    reserves = defaultdict(list)
    for row in map(json.loads, reserve_file.open()):
        reserves[tuple(row['stratum'])].append(row)
    for values in reserves.values():
        values.sort(key=lambda r: r['reserve_rank'])
    used = {r['task_id'] for r in selected}
    final = []
    counts = Counter()
    decisions = ROOT / 'checks/tmax-preparation-v2'; decisions.mkdir(exist_ok=True)
    with zipfile.ZipFile(ROOT / 'sources/tmax/tasks.zip') as z, ledger.open('x') as journal:
        members = defaultdict(list)
        for member in z.infolist():
            members[member.filename.split('/')[0]].append(member)
        for initial in selected:
            accepted = None
            for candidate in [initial] + reserves[tuple(initial['stratum'])]:
                if candidate is not initial and candidate['task_id'] in used:
                    continue
                used.add(candidate['task_id'])
                event = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    initial_task_id=initial['task_id'], candidate_task_id=candidate['task_id'],
                    candidate_reserve_rank=candidate['reserve_rank'], stratum=candidate['stratum'],
                    family_id=candidate['family_id'], frozen_split=candidate['split'],
                    model_attempts_before_selection=0)
                try:
                    receipt = inspect_candidate(z, candidate, members)
                    event.update(status='SOURCE_ACCEPTED_ENVIRONMENT_VERIFIER_PENDING', receipt=receipt)
                    accepted = dict(candidate, initial_task_id=initial['task_id'],
                        source_status=event['status'], task_path=receipt['task_path'])
                    counts['accepted_original' if candidate is initial else 'accepted_reserve'] += 1
                except adapter.TaskPreparationError as error:
                    event.update(status='SOURCE_NOT_ACCEPTED', reason=str(error))
                    counts['source_not_accepted'] += 1
                journal.write(json.dumps(event) + '\n'); journal.flush()
                (decisions / (candidate['task_id'] + '.json')).write_text(json.dumps(event, indent=2))
                if accepted is not None:
                    break
            if accepted is None:
                accepted = dict(initial, initial_task_id=initial['task_id'], source_status='SAME_STRATUM_RESERVES_EXHAUSTED', task_path=None)
                counts['unfilled'] += 1
            final.append(accepted)
            print(json.dumps(dict(event='slot_prepared', initial_task_id=initial['task_id'],
                final_task_id=accepted['task_id'], status=accepted['source_status'])), flush=True)
    if len(final) != 500 or len({r['task_id'] for r in final}) != 500:
        raise ValueError('Final candidate slots must remain 500 unique task IDs')
    for initial, candidate in zip(selected, final):
        if candidate['stratum'] != initial['stratum'] or candidate['split'] != initial['split']:
            raise ValueError('Pre-model replacement changed preregistered stratum/split')
    with output.open('x') as stream:
        for row in final:
            stream.write(json.dumps(row) + '\n')
    initial_canary = json.loads((ROOT / 'manifests/SAMPLING_MANIFEST.json').read_text())['pools']['tmax']['canary_task_ids']
    by_initial = {r['initial_task_id']: r for r in final}
    report = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        status='SOURCE_PREPARED_BUILD_SETUP_VERIFIER_PENDING', counts=dict(counts),
        slots=500, source_accepted=500-counts['unfilled'], model_attempts=0,
        original_manifest_sha256=adapter.digest(selected_file), reserve_manifest_sha256=adapter.digest(reserve_file),
        candidate_manifest_sha256=adapter.digest(output), replacement_ledger_sha256=adapter.digest(ledger),
        adapter_sha256=adapter.digest(ROOT / 'scripts/tmax_adapter.py'),
        split_counts=dict(Counter(r['split'] for r in final)),
        canary_task_ids=[by_initial[ident]['task_id'] for ident in initial_canary],
        canary_initial_task_ids=initial_canary, task_strata_preserved=True,
        family_split_reselected=False, any_model_outcome_used=False,
        fixture_counts_before=dict(Counter(str(r.get('fixture_kind')) for r in selected)),
        fixture_counts_after=dict(Counter(str(r.get('fixture_kind')) for r in final)),
        source_acceptance_is_not_runtime_readiness=True,
        limitations='Static native conversion boundary plus known hidden-file review; image/setup and trusted verifier acceptance still required')
    (ROOT / 'checks/tmax-preparation-v2.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
