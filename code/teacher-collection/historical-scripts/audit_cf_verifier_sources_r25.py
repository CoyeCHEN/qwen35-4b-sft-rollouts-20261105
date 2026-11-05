"""Check CF source and every declared prepared teacher Task against frozen bytes."""
import datetime
import hashlib
import json
from pathlib import Path
import tomllib

from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows, original_rows
from run_collection_stream_r4 import R


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    active = [x for x in active_rows(attempt_counts()) if x['pool'] == 'calibforge']
    registered = {x['task_id']:x for x in original_rows() if x['pool'] == 'calibforge'}
    registered.update({x['task_id']:x for x in active})
    paths = {}
    declared = 0
    for p in R.glob('stream/*/dispatches/*/dispatch.json'):
        value = json.loads(p.read_text())
        if value['kind'] != 'teacher' or value.get('pool') != 'calibforge':
            continue
        cfg = p.parent / 'trial-config.json'
        if sha(cfg) != value['config_sha256']:
            raise ValueError('Declared native Trial configuration changed')
        task = Path(json.loads(cfg.read_text())['task']['path'])
        paths[str(task)] = registered[value['task_id']]
        declared += 1
    for p in (R / 'jobs').glob('*/config.json'):
        cfg = json.loads(p.read_text())
        if cfg.get('install_only') or not any(a.get('name') == 'open-harness' for a in cfg.get('agents', [])):
            continue
        for task in cfg['tasks']:
            path = Path(task['path'])
            if path.name in registered:
                paths[str(path)] = registered[path.name]
                declared += 1
    records = []
    failures = []
    for kind, candidates in [('active_original_source', {x['source_path']:x for x in active}),
        ('declared_teacher_task_copy', paths)]:
        for directory, row in sorted(candidates.items()):
            root = Path(directory)
            checked = []
            for item in row['private_file_identities']:
                p = root / item['path']
                actual = sha(p) if p.exists() else None
                checked.append(dict(path=item['path'], expected_sha256=item['sha256'], actual_sha256=actual))
                if actual != item['sha256']:
                    failures.append(dict(task_id=row['task_id'], directory=directory, kind=kind, mismatch=item['path']))
            instruction = root / 'instruction.md'
            if not instruction.exists() or sha(instruction) != row['instruction_sha256']:
                failures.append(dict(task_id=row['task_id'], directory=directory, kind=kind, mismatch='instruction.md'))
            source = Path(row['source_path'])
            if sha(source / 'task.toml') != row['task_toml_sha256']:
                failures.append(dict(task_id=row['task_id'], directory=directory, kind=kind, mismatch='original task.toml'))
            if root != source:
                original = tomllib.loads((source / 'task.toml').read_text())
                prepared = tomllib.loads((root / 'task.toml').read_text())
                prepared['environment']['docker_image'] = original['environment']['docker_image']
                if original != prepared:
                    failures.append(dict(task_id=row['task_id'], directory=directory, kind=kind, mismatch='Task fields beyond external image pin'))
            records.append(dict(task_id=row['task_id'], kind=kind, directory=directory, files=checked))
    result = dict(passed=not failures, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_sha256=sha(Path(__file__)), active_cf_tasks=len(active),
        declared_teacher_config_references=declared, unique_declared_teacher_task_paths=len(paths),
        checked_private_files=sum(len(x['files']) for x in records), records=records, failures=failures,
        declaration_counts_are_not_attempt_counts=True, model_calls=0, source_or_trial_modifications=0,
        finding='The optimization test script is the frozen script. Its original interpreter selection uses the image-provided Python3.13 verifier environment; the earlier inference that another bootstrap script had run was incorrect. Pipeline dask is a separate public application subprocess failure.')
    path = R / 'checks/cf-source-and-prepared-verifier-integrity-r25.json'
    with path.open('x') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({k:v for k,v in result.items() if k != 'records'}))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
