"""Read-only acceptance of a bounded, identity-pinned derived proof correction."""
import copy
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
S = '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029'
E17 = '/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029'
EXPECTED = {
    'audit_stream_data_worker149_r12.py': 'e7c8d2b3b7338da1ce5c5a6f2a13f949807e33a675451467d52f5424ee97dde0',
    'merge_student_proofs_nfc_r368.py': 'c19a6a1fae4ad844240037fcef42decfef736c192a1cf14e538d8739bd674049',
    'audit_collection_results_r11.py': 'dcd718f4564133738a539b366350118c3bfeb4791d54fa63dc5b7df47c8140fc',
    'audit_stream_data_worker149_r11.py': '70a5175a98d90bc1f867cc97ad9b303a318788b691ac1afaa70abe236ef3e04a',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    for name, digest in EXPECTED.items():
        assert sha(R/'scripts'/name) == digest, name
    registry_path = R/'checks/ENCODER_NFC_REPROOF_CASES_R367.json'
    assert sha(registry_path) == 'bc57ec4ffc95601ce94a1346b2d5432ab38f37c80d5593d5e414779b41ae6d1e'
    registry = json.loads(registry_path.read_text())
    spec = importlib.util.spec_from_file_location('nfc_merge', R/'scripts/merge_student_proofs_nfc_r368.py')
    merger = importlib.util.module_from_spec(spec); spec.loader.exec_module(merger)
    index = R/'checks/STUDENT_AUDIT_TRIALS.json'
    baseline_sha = sha(index)
    entries = {x['trial_id']: x for x in json.loads(index.read_text())['entries']}
    for ident, case in registry['cases'].items():
        assert merger.digest(entries[ident]) == case['old_entry_sha256']
        assert sha(case['result_path']) == case['result_sha256']
    ident = '8f42b40e-deae-429c-874e-5cf488c0c665'
    incoming = R/'derived/stream-student-proofs-nfc-r12'/ident/'checks/STUDENT_AUDIT_TRIALS_ALL.json'
    bundle = json.loads(incoming.read_text()); new, = bundle['entries']
    assert new['trial_id'] == ident and new['semantic_projection_passed'] is True
    assert len(new['original_call_ids']) == 72
    for proof in bundle['proofs'].values():
        relative = Path(proof['relative_path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        assert sha(incoming.parent.parent/relative) == proof['sha256']
    merger.validate_upgrade(entries[ident], new, registry)
    rejected = []
    def reject(name, old, candidate, scope=registry):
        try:
            merger.validate_upgrade(old, candidate, scope)
        except (ValueError, KeyError):
            rejected.append(name)
        else:
            raise AssertionError('Unsafe proof accepted: '+name)
    for field in ['source_journal_sha256', 'raw_export_sha256', 'encoder_sha256', 'qwen_revision']:
        bad = copy.deepcopy(new); bad[field] = 'incorrect'
        reject('wrong_'+field, entries[ident], bad)
    for field in ['encoder_sha256', 'backend_semantics_sha256', 'official_revision']:
        bad = copy.deepcopy(new); bad['student_tokenizer_runtime_contract'][field] = 'incorrect'
        reject('wrong_contract_'+field, entries[ident], bad)
    for field in ['exact_deployment_prefixes', 'all_original_targets_once', 'native_loader_and_collator_passed', 'native_streaming_and_nonstreaming_parsers_passed', 'native_loss_gradient_reference_passed']:
        bad = copy.deepcopy(new); bad[field] = False
        reject('missing_'+field, entries[ident], bad)
    for name, calls in [('omitted_target', new['original_call_ids'][:-1]), ('reordered_targets', list(reversed(new['original_call_ids']))), ('duplicate_target', new['original_call_ids']+[new['original_call_ids'][0]])]:
        bad = copy.deepcopy(new); bad['original_call_ids'] = calls
        reject(name, entries[ident], bad)
    bad = copy.deepcopy(new); bad['trial_id'] = 'not-in-the-pinned-scope'
    reject('unknown_trial', entries[ident], bad)
    bad_scope = copy.deepcopy(registry); bad_scope['cases'][ident]['result_sha256'] = 'incorrect'
    reject('changed_original_result', entries[ident], new, bad_scope)
    accepted = [x for x in entries.values() if x['semantic_projection_passed']]
    for old in accepted:
        reject('accepted_proof_immutable_'+old['trial_id'], old, new)
    remote_code = """from pathlib import Path
import hashlib,json
S=Path(S_VALUE); E=Path(E_VALUE)
paths={
 'training_unit':S/'metadata-snapshots/nfc-prefix-unit-r361/ACCEPTANCE.json',
 'serving_unit':S/'metadata-snapshots/nfc-prefix-unit-serving-r362/ACCEPTANCE.json',
 'input_policy':S/'metadata-snapshots/ENCODER_NFC_INPUT_POLICY_R364.json',
 'encoder':S/'sft-code-nfc-prefix-r4/sft/teacher_segments.py',
 'driver':E/'scripts/audit_stream_nfc_canonical17_r366.py',
 'packager':E/'scripts/package_nfc_student_evidence_r365.py'}
out={}
for name,path in paths.items():
 out[name]=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
 if path.suffix=='.json':
  doc=json.loads(path.read_text()); assert doc['passed'];out[name]['passed']=True
print(json.dumps(out))""".replace('S_VALUE',repr(S)).replace('E_VALUE',repr(E17))
    ssh = ['ssh','-S','/home/chenkeyi/.ssh/cf17-20261028.sock','-oBatchMode=yes','-oProxyCommand=false','chenkeyi@180.163.192.17']
    reply = subprocess.run(ssh+[shlex.join(['python3','-c',remote_code])],check=True,capture_output=True,text=True,timeout=40)
    remote = json.loads(reply.stdout)
    expected_remote = {
      'training_unit':'f710f0c2f61c0855f95c44a9dea806f95a2f9be47dfc673f4dbb64795695c901',
      'serving_unit':'9eacdbc77deb4a68bcc17d2389f082ce4c92edcb4c60bb4086fd9b06bd6a2c8b',
      'input_policy':'e22f1e718464adc9b7a1f04323f8901ec1a03235641b31d5e0b64d4346530900',
      'encoder':registry['current_encoder_sha256']}
    for name,digest in expected_remote.items(): assert remote[name]['sha256']==digest,name
    assert sha(index) == baseline_sha, 'Acceptance must not write the shared index'
    value = dict(passed=True, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        sources=EXPECTED, cases=[dict(proof=str(incoming),sha256=sha(incoming)),dict(proof=str(registry_path),sha256=sha(registry_path))],
        prototype_original_targets=72, prototype_all_native_target_audits_passed=True,
        existing_accepted_proofs_immutable=len(accepted), unsafe_mutations_rejected=len(rejected),
        exact_identity_pinned_reproof_cases=len(registry['cases']), remote_evidence=remote,
        global_index_sha256_before_and_after=baseline_sha, shared_index_modified=False,
        raw_task_result_recorder_or_target_text_modified=False, teacher_calls=0, new_gpu_processes=0,
        source_sha256=sha(Path(__file__)))
    target=R/'checks/NFC_DATA_WRITER_ACCEPTANCE_R375.json'
    with target.open('x') as stream:json.dump(value,stream,indent=2)
    print(json.dumps(value))


if __name__ == '__main__':
    main()
