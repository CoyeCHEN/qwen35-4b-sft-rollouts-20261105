"""Resolve frozen sampling slots and independently verified source-only reserves."""
from pathlib import Path
from collections import Counter
import hashlib
import json

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
MANIFESTS = ['CALIBFORGE_500_TASKS.jsonl', 'TMAX_RUNTIME_CANDIDATES_V2.jsonl']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def original_rows():
    rows = [row for name in MANIFESTS for row in map(json.loads, (R / 'manifests' / name).open())]
    if len(rows) != 1000 or len({x['task_id'] for x in rows}) != 1000 or Counter(x['pool'] for x in rows) != {'calibforge': 500, 'tmax': 500}:
        raise ValueError('Frozen original two-pool slot scope differs')
    return rows


def active_rows(attempts):
    reserve_indexes = {}
    originals = {row['task_id']: row for row in original_rows()}
    selected = {key: dict(row, slot_id=key) for key, row in originals.items()}
    for file in sorted((R / 'manifests/runtime-bindings-r4').glob('*.json')):
        binding = json.loads(file.read_text())
        if binding['kind'] != 'REGISTERED_SOURCE_ENVIRONMENT_REPLACEMENT':
            raise ValueError('Unrecognized sampling addendum')
        slot = binding['replaced_task_id']; candidate = binding['candidate_row']
        if slot not in originals or selected[slot]['task_id'] != slot:
            raise ValueError('Sampling slot replaced more than once or is unknown')
        old = originals[slot]
        if attempts.get(slot, 0) or binding['teacher_attempts_before_replacement'] != 0:
            raise ValueError('Attempted original Task cannot be replaced')
        if sha(Path(binding['source_environment_failure']))!=binding['source_environment_failure_sha256']:
            raise ValueError('Original source environment failure evidence changed')
        if candidate['pool'] != old['pool'] or candidate['stratum'] != old['stratum'] or candidate['split'] != old['split'] or candidate['exclusion_reasons']:
            raise ValueError('Reserve category/skill/difficulty/subset/fixed-split stratum differs')
        proof = Path(binding['native_environment_proof'])
        if sha(proof) != binding['native_environment_proof_sha256']:
            raise ValueError('Native reserve acceptance proof changed')
        accepted = json.loads(proof.read_text())
        if accepted['status'] != 'ENV_READY' or accepted['task_id'] != candidate['task_id'] or accepted['model_calls'] != 0:
            raise ValueError('Unaccepted reserve cannot bind a sampling slot')
        reserve = R / 'manifests' / (candidate['pool'].upper() + '_RESERVES.jsonl')
        if reserve not in reserve_indexes:
            if sha(reserve) != binding['preregistered_reserves_sha256']:
                raise ValueError('Preregistered source reserve universe changed')
            registered_rows=list(map(json.loads,reserve.open()))
            index={x['task_id']:x for x in registered_rows}
            if len(index)!=len(registered_rows):raise ValueError('Duplicate preregistered reserve Task identity')
            reserve_indexes[reserve] = (binding['preregistered_reserves_sha256'], index)
        if reserve_indexes[reserve][0] != binding['preregistered_reserves_sha256']:
            raise ValueError('Conflicting reserve identities in the same frozen selection')
        registered = reserve_indexes[reserve][1][candidate['task_id']]
        for key, value in registered.items():
            if key == 'task_path' and candidate['pool'] == 'tmax':
                if Path(candidate[key]) != R / 'tasks/tmax' / candidate['task_id']:
                    raise ValueError('Native converted reserve path escaped its owned task directory')
                continue
            if candidate.get(key) != value:
                raise ValueError('Reserve source metadata differs from its original preregistration: ' + key)
        selected[slot] = dict(candidate, slot_id=slot, sampling_binding=str(file), sampling_binding_sha256=sha(file))
    rows = list(selected.values())
    if len({x['task_id'] for x in rows}) != 1000 or not set(attempts) <= {x['task_id'] for x in rows}:
        raise ValueError('Duplicate Task or prior teacher identity lost from active scope')
    families = {}
    for row in rows:
        key = row['family_id']
        if key in families and families[key] != row['split']:
            raise ValueError('Original family split crossed')
        families[key] = row['split']
    return rows
