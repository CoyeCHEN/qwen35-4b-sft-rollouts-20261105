"""Materialize original TMax task inputs without extracting old solutions.

Validate the native adapter and private-material boundary for each selected task.
This preparation phase creates no teacher attempt and does not replace a task.
"""
from collections import Counter
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import zipfile

ROOT = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
SPEC = importlib.util.spec_from_file_location('tmax_adapter', ROOT / 'scripts/tmax_adapter.py')
if SPEC is None or SPEC.loader is None:
    raise ImportError('Pinned Harbor TMax adapter unavailable')
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def materialize(z, ident, members):
    target = ROOT / 'sources/tmax/original-tasks' / ident
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    for member in members:
        relative = Path(member.filename).relative_to(ident)
        # Solutions and summary files are intentionally never extracted or read.
        if relative.parts[0] != 'fixtures' and str(relative) not in {
            'task.json', 'container.def', 'setup.sh', 'test_initial_state.py', 'test_final_state.py'
        }:
            continue
        if '..' in relative.parts or member.is_dir():
            continue
        if stat.S_ISLNK(member.external_attr >> 16):
            raise adapter.TaskPreparationError('Original ZIP fixture symlink requires review')
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        raw = z.read(member)
        if path.exists():
            if path.read_bytes() != raw:
                raise ValueError('Previously materialized original source changed')
        else:
            path.write_bytes(raw)
            path.chmod((member.external_attr >> 16) & 0o777 or 0o600)
    return target


def main():
    out = ROOT / 'checks/tmax-source-acceptance'; out.mkdir(exist_ok=True)
    destination = ROOT / 'tasks/tmax'; destination.mkdir(parents=True, exist_ok=True)
    selected = list(map(json.loads, (ROOT / 'manifests/TMAX_500_TASKS.jsonl').open()))
    canary = json.loads((ROOT / 'manifests/SAMPLING_MANIFEST.json').read_text())['pools']['tmax']['canary_task_ids']
    selected.sort(key=lambda r: (canary.index(r['task_id']) if r['task_id'] in canary else 8, r['task_id']))
    archive = ROOT / 'sources/tmax/tasks.zip'
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != '59e2efd8785d68214f4f8f61c383ef806dff9778d965af5d13cf45f02e3dc106':
            raise ValueError('Pinned TMax archive changed')
    counts = Counter()
    with zipfile.ZipFile(archive) as z:
        wanted = {r['task_id'] for r in selected}
        members = {ident: [] for ident in wanted}
        for member in z.infolist():
            ident = member.filename.split('/')[0]
            if ident in wanted:
                members[ident].append(member)
        for row in selected:
            ident = row['task_id']; result_path = out / (ident + '.json')
            if result_path.exists():
                counts[json.loads(result_path.read_text())['status']] += 1
                continue
            record = dict(task_id=ident, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                source_revision=row['revision'], model_attempts=0, stratum=row['stratum'])
            try:
                source = materialize(z, ident, members[ident])
                if adapter.digest(source / 'task.json') != row['task_json_sha256']:
                    raise ValueError('Selected task JSON identity differs from source inventory')
                receipt = adapter.convert_task(source, destination,
                    native_converter=ROOT / 'scripts/upstream-convert-to-harbor.py',
                    intricate_base_definition=ROOT / 'scripts/base_intricate.def')
                record.update(status='CONVERSION_VERIFIED_BUILD_AND_VERIFIER_PENDING', receipt=receipt,
                    task_path=str(destination / ident))
            except adapter.TaskPreparationError as error:
                record.update(status='SOURCE_PREPARATION_NOT_ACCEPTED', reason=str(error))
            result_path.write_text(json.dumps(record, indent=2))
            counts[record['status']] += 1
            summary = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), status='PREPARING',
                tasks_observed=sum(counts.values()), planned_selected_tasks=500, counts=dict(counts),
                model_attempts=0, replacements_applied=0, old_solutions_read_or_extracted=False,
                adapter_sha256=adapter.digest(ROOT / 'scripts/tmax_adapter.py'))
            (ROOT / 'checks/tmax-source-preparation.json').write_text(json.dumps(summary, indent=2))
            print(json.dumps(dict(task_id=ident, status=record['status'])), flush=True)
    summary.update(status='SOURCE_INSPECTION_FINISHED_ENVIRONMENTS_PENDING')
    (ROOT / 'checks/tmax-source-preparation.json').write_text(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
