"""Reproject each frozen qualified target with an explicit canonical backend.

Run separately in training and serving runtimes. Existing bytes, indexes and
token caches are read-only; mismatches are recorded without stopping other Tasks.
"""
import datetime
import gzip
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import sys
import time

from sft.qwen35 import digest, load_tokenizer
from sft.teacher_segments import project_decision

S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
inputs = S / 'data-primary-snapshots/r161'
label = sys.argv[1]
assert label in ['training', 'serving']
assert os.environ['QWEN35_MODEL_PATH'] == str(S / 'student-tokenizer-r155')
out = S / 'data-canonical-primary-r161' / label
out.mkdir(parents=True, exist_ok=False)
source_manifest = json.loads((inputs / 'INPUTS.json').read_text())
rows = []
for pool in ['CALIBFORGE', 'TMAX']:
    path = inputs / (pool + '_SUCCESS_INDEX.jsonl')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == source_manifest['files'][path.name]['sha256']
    rows.extend(json.loads(line) for line in path.open())
assert len({row['task_id'] for row in rows}) == len(rows)
tokenizer = load_tokenizer()
encoder_sha = hashlib.sha256(Path(inspect.getfile(project_decision)).read_bytes()).hexdigest()
assert encoder_sha == '8506585c55ea67585d2512a86a45b689f324a766ac1679fb98aba30a6170b947'
resource = S / 'student-tokenizer-r155'
assert hashlib.sha256((resource / 'tokenizer.json').read_bytes()).hexdigest() == '5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42'
assert hashlib.sha256((resource / 'tokenizer_config.json').read_bytes()).hexdigest() == '3dd1cee8a0cb8f51800bcb47bd157eeef5bda2d39c85b7569892b9af95170071'
backend = json.loads(tokenizer.backend_tokenizer.to_str())
backend.pop('padding', None)
backend.pop('truncation', None)
backend_sha = digest(backend)
assert backend_sha == '027a3f1c30acd5438805f34bb427a99772640beba2a4e5153ada9c90fc259281'
identity = dict(label=label, tokenizer_class=type(tokenizer).__module__ + '.' + type(tokenizer).__name__,
    backend_semantics_sha256=backend_sha, model_resource=os.environ['QWEN35_MODEL_PATH'],
    versions={name:importlib.metadata.version(name) for name in ['transformers', 'tokenizers', 'jinja2']},
    resource_manifest_sha256=hashlib.sha256((S / 'student-tokenizer-r155/SOURCE_MANIFEST_R155.json').read_bytes()).hexdigest(),
    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    encoder_sha256=encoder_sha,
    qwen_serializer_sha256=hashlib.sha256(Path(inspect.getfile(load_tokenizer)).read_bytes()).hexdigest(),
    input_manifest_sha256=hashlib.sha256((inputs / 'INPUTS.json').read_bytes()).hexdigest(),
    model_calls=0, final_corpus_release=False, old_cache_modified=False)
(out / 'IDENTITY.json').write_text(json.dumps(identity, indent=2))
completed = []
keys = ['generation_prefix_sha256', 'input_sha256', 'labels_sha256',
        'provider_payload_sha256', 'normalized_history_sha256', 'supervision_token_classes']
for ordinal, row in enumerate(rows):
    started = time.monotonic()
    item = dict(task_id=row['task_id'], trial_id=row['trial_id'], pool=row['pool'], split=row['split'],
        result_sha256=row['result_sha256'], source_journal_sha256=row['source_journal_sha256'],
        backend_semantics_sha256=backend_sha, compared_targets=0, mismatches=[], errors=[])
    try:
        proof = row['student_proof']
        root = Path(proof['length_views']['262144']['cache']).parent.parent.parent
        bundle = json.loads((root / 'checks/STUDENT_AUDIT_TRIALS_ALL.json').read_text())
        artifact = bundle['proofs']['canary-qwen-projection-all-v4.json']
        projection = Path(artifact['path'])
        assert hashlib.sha256(projection.read_bytes()).hexdigest() == artifact['sha256']
        native, = [x for x in json.loads(projection.read_text()) if x['trial_id'] == row['trial_id']]
        target_path = Path(native['target_mapping'])
        assert hashlib.sha256(target_path.read_bytes()).hexdigest() == native['target_mapping_sha256']
        old = {x['call_id']:x for x in json.loads(target_path.read_text())}
        candidates = []
        for path in (root / 'sources/canary-calls-all').glob('*.jsonl.gz'):
            with gzip.open(path, 'rt') as stream:
                first = json.loads(next(stream))
            if first['trial_id'] == row['trial_id']:
                candidates.append(path)
        source, = candidates
        assert hashlib.sha256(source.read_bytes()).hexdigest() == proof['raw_export_sha256']
        item.update(source_export_sha256=proof['raw_export_sha256'], original_target_mapping_sha256=native['target_mapping_sha256'])
        seen = []
        for line in gzip.open(source, 'rt'):
            call = json.loads(line)
            decision = project_decision(tokenizer, call)
            evidence = decision.evidence
            seen.append(call['call_id'])
            different = [key for key in keys if evidence[key] != old[call['call_id']][key]]
            if different:
                item['mismatches'].append(dict(call_id=call['call_id'], different_fields=different,
                    expected={k:old[call['call_id']][k] for k in different}, actual={k:evidence[k] for k in different}))
            item['compared_targets'] += 1
        assert seen == proof['original_call_ids']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == proof['raw_export_sha256']
        item['all_original_targets_compared_once'] = True
    except Exception as error:
        item['errors'].append(dict(type=type(error).__name__, message=str(error)[:500]))
    item.update(passed=not item['mismatches'] and not item['errors'], seconds=time.monotonic()-started,
        checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out / (row['trial_id'] + '.json')).write_text(json.dumps(item, indent=2))
    completed.append(item)
    summary = dict(**identity, checked_at=item['checked_at'], planned_tasks=len(rows), completed_tasks=len(completed),
        passed_tasks=sum(x['passed'] for x in completed), compared_targets=sum(x['compared_targets'] for x in completed),
        failed_trial_ids=[x['trial_id'] for x in completed if not x['passed']],
        status='COMPLETE' if len(completed)==len(rows) else 'RUNNING',
        note='Matching IDs preserve historical parser/label evidence; final combined formal Loader audit is still required')
    temporary = out / 'progress.pending'
    temporary.write_text(json.dumps(summary, indent=2))
    temporary.replace(out / 'PROGRESS.json')
print(json.dumps(summary))
