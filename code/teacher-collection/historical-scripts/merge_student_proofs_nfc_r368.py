"""Merge immutable proofs; only six identity-pinned NFC negatives may be superseded."""
import hashlib
import json
from pathlib import Path
import shutil
import sys


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def validate_upgrade(old, new, registry):
    ident = new['trial_id']
    case = registry['cases'].get(ident)
    if case is None or digest(old) != case['old_entry_sha256']:
        raise ValueError('Conflicting proof is outside the exact NFC reproof cases')
    if old['semantic_projection_passed'] or old.get('quarantine_reasons') != ['Generation-boundary tokenization changed template text']:
        raise ValueError('Never replace an accepted proof or an unrelated quarantine')
    for key in ['source_journal_sha256', 'raw_export_sha256']:
        if old[key] != case[key] or new[key] != case[key]:
            raise ValueError('NFC reproof refers to another original trajectory')
    if sha(case['result_path']) != case['result_sha256']:
        raise ValueError('Original native Result changed')
    contract = new.get('student_tokenizer_runtime_contract', {})
    if contract.get('encoder_sha256') != registry['current_encoder_sha256'] or contract.get('backend_semantics_sha256') != registry['backend_semantics_sha256'] or contract.get('official_revision') != registry['qwen_revision']:
        raise ValueError('NFC reproof uses another tokenizer or encoder')
    calls = new.get('original_call_ids', [])
    if not calls or len(calls) != len(set(calls)) or calls != old['original_call_ids']:
        raise ValueError('Every original target must remain in the reproof in order')
    if new['semantic_projection_passed']:
        for flag in ['exact_deployment_prefixes', 'all_original_targets_once', 'native_loader_and_collator_passed',
                     'native_streaming_and_nonstreaming_parsers_passed', 'native_loss_gradient_reference_passed']:
            if new.get(flag) is not True:
                raise ValueError('NFC positive reproof lacks full per-target native evidence')
        if new.get('encoder_sha256') != registry['current_encoder_sha256'] or new.get('qwen_revision') != registry['qwen_revision']:
            raise ValueError('NFC positive reproof identity differs')


def main():
    root = Path(sys.argv[1])
    incoming = Path(sys.argv[2])
    cohort = sys.argv[3]
    registry_path = root / 'checks/ENCODER_NFC_REPROOF_CASES_R367.json'
    if sha(registry_path) != 'bc57ec4ffc95601ce94a1346b2d5432ab38f37c80d5593d5e414779b41ae6d1e':
        raise ValueError('Exact reviewed NFC reproof scope changed')
    registry = json.loads(registry_path.read_text())
    index = root / 'checks/STUDENT_AUDIT_TRIALS.json'
    old = json.loads(index.read_text())
    new = json.loads(incoming.read_text())
    entries = {x['trial_id']: x for x in old['entries']}
    superseded = []
    for item in new['entries']:
        ident = item['trial_id']
        if ident in entries and entries[ident] != item:
            validate_upgrade(entries[ident], item, registry)
            superseded.append(dict(trial_id=ident, old_entry_sha256=digest(entries[ident]), new_entry_sha256=digest(item)))
        entries[ident] = item
    for name, proof in new['proofs'].items():
        relative = Path(proof['relative_path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Proof artifact escaped its immutable bundle')
        source = incoming.parent.parent / relative
        if sha(source) != proof['sha256']:
            raise ValueError('Incoming native proof artifact changed')
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if sha(target) != sha(source):
                raise ValueError('Existing immutable artifact changed')
        else:
            shutil.copyfile(source, target)
        key = cohort + '/' + name
        fixed = dict(proof, path=str(target))
        if key in old['proofs'] and old['proofs'][key] != fixed:
            raise ValueError('Proof cohort identity changed')
        old['proofs'][key] = fixed
    frozen = index.parent / 'student-proof-index-history' / (sha(index) + '.json')
    frozen.parent.mkdir(exist_ok=True)
    if not frozen.exists():
        shutil.copyfile(index, frozen)
    old['entries'] = list(entries.values())
    old['scope'] = 'Exact native proofs; reviewed NFC input admission correction preserves raw sources and target text'
    old['does_not_approve_reward_or_task_provenance'] = True
    temporary = index.with_suffix('.tmp')
    temporary.write_text(json.dumps(old, indent=2))
    temporary.replace(index)
    print(json.dumps(dict(trials=len(entries), superseded=superseded,
        targets=sum(len(x.get('original_call_ids', [])) for x in entries.values()))))


if __name__ == '__main__':
    main()
