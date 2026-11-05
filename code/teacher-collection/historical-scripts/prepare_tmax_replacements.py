"""Apply preregistered same-stratum reserves to pre-model source failures.

Only source/conversion acceptance is decided here. Image, setup and verifier
acceptance still gate every selected candidate before any teacher dispatch.
"""
from collections import Counter, defaultdict
import datetime
import hashlib
import json
from pathlib import Path
import zipfile

import prepare_tmax_sources as preparation

ROOT = preparation.ROOT
adapter = preparation.adapter


def main():
    output = ROOT / 'manifests/TMAX_SOURCE_PREPARED_CANDIDATES.jsonl'
    ledger = ROOT / 'manifests/TMAX_SOURCE_REPLACEMENT_LEDGER.jsonl'
    if output.exists() or ledger.exists():
        raise FileExistsError('Preserve the existing candidate and replacement identities; inspect before continuing')
    selected = list(map(json.loads, (ROOT / 'manifests/TMAX_500_TASKS.jsonl').open()))
    used = {r['task_id'] for r in selected}
    reserves = defaultdict(list)
    for row in map(json.loads, (ROOT / 'manifests/TMAX_RESERVES.jsonl').open()):
        reserves[tuple(row['stratum'])].append(row)
    for values in reserves.values():
        values.sort(key=lambda r: r['reserve_rank'])
    accepted = []
    counts = Counter()
    with zipfile.ZipFile(ROOT / 'sources/tmax/tasks.zip') as z, ledger.open('x') as journal:
        members = defaultdict(list)
        for member in z.infolist():
            members[member.filename.split('/')[0]].append(member)
        for row in selected:
            initial_path = ROOT / 'checks/tmax-source-acceptance' / (row['task_id'] + '.json')
            initial = json.loads(initial_path.read_text())
            if initial['status'] == 'CONVERSION_VERIFIED_BUILD_AND_VERIFIER_PENDING':
                accepted.append(dict(row, source_preparation_status=initial['status'], task_path=initial['task_path']))
                counts['initial_source_accepted'] += 1
                continue
            replacement = None
            for candidate in reserves[tuple(row['stratum'])]:
                if candidate['task_id'] in used:
                    continue
                used.add(candidate['task_id'])
                event = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    initial_task_id=row['task_id'], candidate_task_id=candidate['task_id'],
                    initial_failure_path=str(initial_path), initial_failure_sha256=hashlib.sha256(initial_path.read_bytes()).hexdigest(),
                    initial_failure_reason=initial['reason'], stratum=row['stratum'],
                    candidate_reserve_rank=candidate['reserve_rank'], model_attempts_before_replacement=0,
                    family_id=candidate['family_id'], frozen_split=candidate['split'])
                try:
                    source = preparation.materialize(z, candidate['task_id'], members[candidate['task_id']])
                    if adapter.digest(source / 'task.json') != candidate['task_json_sha256']:
                        raise ValueError('Preregistered reserve source identity mismatch')
                    receipt = adapter.convert_task(source, ROOT / 'tasks/tmax',
                        native_converter=ROOT / 'scripts/upstream-convert-to-harbor.py',
                        intricate_base_definition=ROOT / 'scripts/base_intricate.def')
                    event.update(status='SOURCE_ACCEPTED_BUILD_AND_VERIFIER_PENDING', receipt=receipt)
                    replacement = dict(candidate, replaced_initial_task_id=row['task_id'],
                        source_preparation_status=event['status'], task_path=str(ROOT / 'tasks/tmax' / candidate['task_id']))
                    counts['source_replacement_accepted'] += 1
                except adapter.TaskPreparationError as error:
                    event.update(status='RESERVE_SOURCE_NOT_ACCEPTED', reason=str(error))
                    counts['reserve_source_not_accepted'] += 1
                journal.write(json.dumps(event) + '\n'); journal.flush()
                print(json.dumps({k: event[k] for k in ['initial_task_id', 'candidate_task_id', 'status']}), flush=True)
                if replacement is not None:
                    break
            if replacement is None:
                counts['exact_stratum_reserves_exhausted'] += 1
                accepted.append(dict(row, source_preparation_status='SOURCE_UNACCEPTED_NO_SAME_STRATUM_RESERVE',
                    task_path=None))
            else:
                accepted.append(replacement)
    if len(accepted) != 500 or len({r['task_id'] for r in accepted}) != 500:
        raise ValueError('Source preparation violated the 500 unique-task slot invariant')
    with output.open('x') as stream:
        for row in accepted:
            stream.write(json.dumps(row) + '\n')
    report = dict(status='SOURCE_CANDIDATES_READY_ENVIRONMENT_VERIFIER_ACCEPTANCE_PENDING',
        counts=dict(counts), slots=500, accepted_original_tasks=counts['initial_source_accepted'],
        accepted_replacement_tasks=counts['source_replacement_accepted'],
        source_accepted_tasks=counts['initial_source_accepted'] + counts['source_replacement_accepted'],
        split_counts=dict(Counter(r['split'] for r in accepted)),
        candidate_manifest_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        replacement_ledger_sha256=hashlib.sha256(ledger.read_bytes()).hexdigest(),
        initial_manifest_sha256=hashlib.sha256((ROOT / 'manifests/TMAX_500_TASKS.jsonl').read_bytes()).hexdigest(),
        model_attempts=0, source_failures_are_not_teacher_failures=True,
        source_acceptance_is_not_runtime_readiness=True,
        success_or_failure_trajectories_used=False)
    (ROOT / 'checks/tmax-source-replacements.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
