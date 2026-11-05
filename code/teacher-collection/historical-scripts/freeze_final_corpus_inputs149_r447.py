"""Freeze final data inputs only after the existing full-campaign gate passes.

No collection admission, model call, tokenizer change, or training. This creates
new SSD metadata; original Tasks, Trials, Results and indexes remain untouched.
"""
import argparse
from collections import Counter
import datetime
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
P = R / 'controller-runtime-r270/venv/bin/python'


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    if not args.name.isascii() or not args.name.replace('-', '').isalnum():
        raise ValueError('Use a simple new final snapshot identity')
    gate = R / 'scripts/check_final_data_readiness_r446.py'
    subprocess.run([str(P), str(gate), '--require-ready'], check=True)
    gate_path = R / 'checks/data-finalization-readiness-r370.json'
    gate_bytes = gate_path.read_bytes()
    ready = json.loads(gate_bytes)
    if ready['status'] != 'READY_FOR_FINAL_CORPUS_INPUT_FREEZE' or any(ready['blockers'].values()):
        raise ValueError('Final full-campaign admission remains closed')
    if sum(ready['task_status_counts'].values()) != 1000:
        raise ValueError('The final Task denominator changed')
    from collection_attempts_r8 import attempt_counts
    from collection_selection_r7 import active_rows
    counts = attempt_counts()
    rows = active_rows(counts)
    if Counter(x['pool'] for x in rows) != {'calibforge': 500, 'tmax': 500}:
        raise ValueError('Final active sampling scope changed')
    authority = ready['authority']
    campaign_path = Path(authority['manifest'])
    campaign_blob = campaign_path.read_bytes()
    if sha(campaign_blob) != authority['manifest_sha256']:
        raise ValueError('Current Campaign changed')
    campaign = json.loads(campaign_blob)
    deployment_path = Path(campaign['deployment_config'])
    deployment_blob = deployment_path.read_bytes()
    if sha(deployment_blob) != campaign['deployment_config_sha256']:
        raise ValueError('Current deployment changed')
    deployment = json.loads(deployment_blob)
    ssd = Path(deployment['runtime']['ssd_root'])
    destination = ssd / 'data-final-inputs' / args.name
    metadata = {}
    files = {}
    for pool in ['CALIBFORGE', 'TMAX']:
        for kind in ['SUCCESS_INDEX', 'FAILURE_OR_PENDING_INDEX']:
            name = pool + '_' + kind + '.jsonl'
            path = R / 'indexes' / name
            blob = path.read_bytes()
            if sha(blob) != ready['source_index_sha256'][str(path)]:
                raise ValueError('Final indexes moved after the full-campaign gate')
            metadata[name] = blob
            files[name] = dict(sha256=sha(blob), bytes=len(blob), rows=len(blob.splitlines()), source=str(path))
    names = ['checks/collection-qualification.json', 'indexes/NATIVE_TRIAL_COST_TOKEN_LEDGER.jsonl',
             'checks/attempt-environment-only-reconciliation-r6.json',
             'configs/teacher-native-11tools-summary-r1.json',
             str(gate_path.relative_to(R)), str(campaign_path.relative_to(R)), str(deployment_path.relative_to(R))]
    sampling = json.loads((R / 'manifests/SAMPLING_MANIFEST.json').read_text())
    names += ['manifests/SAMPLING_MANIFEST.json']
    names += [str(Path(item['path']).relative_to(R)) for item in sampling['files'].values()]
    names += [str(path.relative_to(R)) for path in (R / 'manifests/runtime-bindings-r4').glob('*.json')]
    for row in rows:
        if row.get('sampling_binding'):
            if sha(Path(row['sampling_binding']).read_bytes()) != row['sampling_binding_sha256']:
                raise ValueError('Fixed sampling replacement identity changed')
    for name in sorted(set(names)):
        metadata['metadata/' + name] = (R / name).read_bytes()
    metadata['ACTIVE_1000_TASKS.jsonl'] = b''.join((json.dumps(row) + '\n').encode() for row in rows)
    qualification = json.loads(metadata['metadata/checks/collection-qualification.json'])
    final_pools = {pool: dict(value,
        active_selected=qualification['pools'][pool]['active_sampling_distribution'],
        successful=qualification['pools'][pool]['qualified_primary_distribution'])
        for pool, value in sampling['pools'].items()}
    manifest = dict(status='FINAL_SAMPLING_AND_SUCCESS_DISTRIBUTIONS_FROZEN',
        seed=42, planned_unique_tasks=1000, pools=final_pools, original_sampling_manifest=sampling,
        active_fixed_tasks_sha256=sha(metadata['ACTIVE_1000_TASKS.jsonl']),
        final_qualification_distributions=qualification['pools'],
        fixed_splits_not_selected_by_success=True,
        category_mapping_does_not_imply_equal_task_distributions=True,
        sampling_bindings=[dict(task_id=x['task_id'], slot_id=x['slot_id'],
            path=x.get('sampling_binding'), sha256=x.get('sampling_binding_sha256')) for x in rows],
        actual_or_conservative_attempt_counts=dict(counts),
        research_caps=dict(unique_tasks=1000, complete_attempts=2000, attempts_per_task=2),
        final_gate_sha256=sha(gate_bytes), training_started=False)
    metadata['SAMPLING_MANIFEST.json'] = json.dumps(manifest, indent=2).encode()
    contract = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), files=files,
        all_files={name: dict(sha256=sha(blob), bytes=len(blob)) for name, blob in metadata.items()},
        qualification_snapshot_sha256=sha(metadata['metadata/checks/collection-qualification.json']),
        purpose='Final qualified primary cache assembly and complete token/label/Loader audit',
        full_campaign_complete=True, formal_corpus_release=False, training_started=False,
        final_gate_sha256=sha(gate_bytes), gate_source_sha256=sha(gate.read_bytes()),
        source_sha256=sha(Path(__file__).read_bytes()), remote_ssd_destination=str(destination))
    metadata['INPUTS.json'] = json.dumps(contract, indent=2).encode()
    if gate_path.read_bytes() != gate_bytes or any(sha(Path(path).read_bytes()) != digest for path, digest in ready['source_index_sha256'].items()):
        raise ValueError('Final source generation changed before transfer')
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w:gz') as stream:
        for name, blob in metadata.items():
            item = tarfile.TarInfo(name)
            item.size = len(blob)
            item.mode = 0o600
            stream.addfile(item, io.BytesIO(blob))
    extract = '''import json,pathlib,sys,tarfile,hashlib
p=pathlib.Path(sys.argv[1]);p.mkdir(parents=True,exist_ok=False)
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as archive:
 for item in archive:
  relative=pathlib.PurePosixPath(item.name)
  if not item.isfile() or relative.is_absolute() or '..' in relative.parts:
   raise ValueError('Invalid frozen input member')
  target=p/item.name;target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as stream:stream.write(archive.extractfile(item).read())
c=json.loads((p/'INPUTS.json').read_text())
for name,v in c['all_files'].items():
 if hashlib.sha256((p/name).read_bytes()).hexdigest()!=v['sha256']:
  raise ValueError('Transferred final input changed')
print(json.dumps(dict(destination=str(p),input_manifest_sha256=hashlib.sha256((p/'INPUTS.json').read_bytes()).hexdigest(),files=len(c['all_files']),full_campaign_complete=c['full_campaign_complete'],training_started=False)))
'''
    result = subprocess.run([*deployment['ssh'], deployment['host'], shlex.join(['python3', '-c', extract, str(destination)])],
        input=archive.getvalue(), capture_output=True, check=True, timeout=180)
    receipt = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        destination=str(destination), input_manifest_sha256=sha(metadata['INPUTS.json']),
        final_gate_sha256=sha(gate_bytes), remote_receipt=json.loads(result.stdout),
        source_sha256=sha(Path(__file__).read_bytes()), model_calls=0, training_started=False)
    with (R / 'checks' / ('final-input-freeze-' + args.name + '.json')).open('x') as stream:
        json.dump(receipt, stream, indent=2)
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
