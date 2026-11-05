"""Inventory pinned original tasks on the existing controller without model calls.

Answer fields and old solutions never enter the public metadata index. Originals
stay in the trusted source cache; only identities of private files are exported.
"""
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile

BASE = Path('/home/chenkeyi/.local/share/harbor-rsi')
ROOT = BASE / 'qwen35-new-cf500-tmax500-20261029'
CF = BASE / 'qwen35-calibforge-ab-20261027/sources/calibforge-task-release'
TB = BASE / 'near-r3-20261015/tb21-formal-20261015T023432Z/tasks'
CF_REV = 'c2fae4c1f536461142b2a89a8b9423a8bc376088'
TMAX_REV = 'e3ded940596cc611c9815684ba51a7e8ee0cffc9'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_rows(name, rows):
    target = ROOT / 'sources' / name
    with target.open('x') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    return dict(path=str(target), sha256=sha(target.read_bytes()), rows=len(rows))


def main():
    tb = []
    for directory in sorted(TB.iterdir()):
        if not (directory / 'task.toml').exists():
            continue
        raw = (directory / 'task.toml').read_bytes()
        config = tomllib.loads(raw.decode())
        instruction = (directory / 'instruction.md').read_bytes()
        tb.append(dict(task_id=directory.name, public_metadata=config.get('metadata', {}),
            public_description=config.get('task', {}).get('description'),
            public_keywords=config.get('task', {}).get('keywords'),
            instruction=instruction.decode(), instruction_sha256=sha(instruction),
            task_toml_sha256=sha(raw), source_path=str(directory),
            private_file_identities=[dict(path=str(p.relative_to(directory)), sha256=sha(p.read_bytes()))
                for p in sorted((directory / 'tests').rglob('*')) if p.is_file()]))
    if len(tb) != 89:
        raise ValueError(f'Frozen TB2.1 set must have 89 members, found {len(tb)}')
    cf = []
    for row in map(json.loads, (CF / 'metadata.jsonl').open()):
        directory = CF / row['task_path']
        header = (directory / 'task.toml').read_bytes()
        config = tomllib.loads(header.decode())
        instruction = (directory / 'instruction.md').read_bytes()
        if ' '.join(instruction.decode().split()) != ' '.join(row['instruction'].split()):
            raise ValueError('Published instruction/metadata mismatch: ' + row['task_id'])
        cf.append(dict(dataset='AweAI-Team/CalibForge', revision=CF_REV,
            **{k: row[k] for k in ['task_id', 'subset', 'category', 'difficulty', 'tags', 'task_path', 'docker_image']},
            instruction=instruction.decode(), instruction_sha256=sha(instruction),
            task_toml_sha256=sha(header), original_config=config, source_path=str(directory),
            environment_definition=(directory / 'environment/Dockerfile').read_text(),
            private_file_identities=[dict(path=str(p.relative_to(directory)), sha256=sha(p.read_bytes()))
                for p in sorted((directory / 'tests').rglob('*')) if p.is_file()]))
    archive = ROOT / 'sources/tmax/tasks.zip'
    with archive.open('rb') as stream:
        archive_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    if archive_sha != '59e2efd8785d68214f4f8f61c383ef806dff9778d965af5d13cf45f02e3dc106':
        raise ValueError('Original TMax archive changed')
    tmax = []
    with zipfile.ZipFile(archive) as z:
        names = set(z.namelist())
        for name in sorted(n for n in names if n.endswith('/task.json') and n.count('/') == 1):
            ident = name.split('/')[0]
            raw = z.read(name)
            row = json.loads(raw)
            if row['name'] != ident:
                raise ValueError('TMax directory/task identity mismatch')
            safe = {k: row.get(k) for k in ['domain', 'skill_type', 'primitive_skills', 'task_complexity',
                'command_complexity', 'scenario', 'language', 'anchor', 'verifier_kind', 'fixture_kind',
                'corpus_kind', 'base_image']}
            tmax.append(dict(dataset='allenai/TMax-15K', revision=TMAX_REV, task_id=ident,
                instruction=row['description'], instruction_sha256=sha(row['description'].encode()),
                task_json_sha256=sha(raw), truth_sha256=sha(row.get('truth', '').encode()), **safe,
                environment_definition=z.read(ident + '/container.def').decode(),
                setup_sha256=sha(z.read(ident + '/setup.sh')) if ident + '/setup.sh' in names else None,
                private_file_identities=[dict(path=p, sha256=sha(z.read(ident + '/' + p)))
                    for p in ['test_initial_state.py', 'test_final_state.py'] if ident + '/' + p in names],
                source_archive=str(archive), source_member=name,
                old_solution_members_used=False))
    result = dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        read_only_source_inventory=True, model_calls=0,
        tb21=write_rows('tb21-public-reference.jsonl', tb),
        calibforge=write_rows('calibforge-public-metadata.jsonl', cf),
        tmax=write_rows('tmax-public-metadata.jsonl', tmax), tmax_archive_sha256=archive_sha,
        source_counts=dict(calibforge_subsets=dict(Counter(r['subset'] for r in cf)),
            calibforge_categories=dict(Counter(r['category'] for r in cf)),
            tmax_domains=dict(Counter(r['domain'] for r in tmax)),
            tmax_skills=dict(Counter(r['skill_type'] for r in tmax)),
            tmax_complexity=dict(Counter(r['task_complexity'] for r in tmax)),
            tb21_categories=dict(Counter(r['public_metadata'].get('category') for r in tb))))
    (ROOT / 'checks/public-source-inventory.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
