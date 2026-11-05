"""Memoize the unchanged raw-SSE export for immutable terminal Recorders.

Every use hashes all Recorder files and the native Result. Initial adoption
also verifies every recorded artifact reference against its content address.
The gzip and ledger remain the original canonical output, never a new target.
"""
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from run_collection_stream_r4 import R


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def inputs(trial):
    root=trial/'agent/openharness-rollout'
    files=[]
    for path in sorted(root.rglob('*')):
        if path.is_file():files.append(dict(path=str(path.relative_to(root)),sha256=sha(path),bytes=path.stat().st_size))
    return dict(trial=str(trial),result_sha256=sha(trial/'result.json'),files=files,
        legacy_producer_sha256=sha(R/'scripts/export_native_canary_calls_before_r8.py'),
        producer_sha256=sha(R/'scripts/export_native_canary_calls_r8.py'),
        cache_sha256=sha(Path(__file__)),classifier_sha256=sha(R/'scripts/teacher_call_dispositions.py'))


def identity(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def verify_references(trial,value):
    from foundation.rollouts.export import artifactRefs
    root=trial/'agent/openharness-rollout';files={x['path']:x for x in value['files']};refs={}
    for entry in value['files']:
        path=root/entry['path']
        if path.name=='events.jsonl':
            for line in path.open():
                for ref in artifactRefs(json.loads(line)):
                    refs[(str(path.parent.relative_to(root)),ref['$artifact'],ref['size'],ref['encoding'])]=ref
        elif path.name=='manifest.json':
            for ref in artifactRefs(json.loads(path.read_text())):
                refs[(str(path.parent.relative_to(root)),ref['$artifact'],ref['size'],ref['encoding'])]=ref
    for (prefix,digest,size,_),ref in refs.items():
        if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid recorded content address')
        key=str(Path(prefix)/'artifacts'/digest)
        artifact=files.get(key)
        if artifact is None or artifact['sha256']!=digest or artifact['bytes']!=size:
            raise ValueError('Raw Recorder reference missing or corrupt: '+key)
    return len(refs)


def verified_outputs(row,ledger,value):
    binding=Path(row['call_dispositions'])
    if sha(binding)!=row['call_dispositions_sha256'] or sha(row['export'])!=row['export_sha256']:
        raise ValueError('Existing canonical export or call ledger binding changed')
    data=json.loads(binding.read_text())
    journal=next(x['sha256'] for x in value['files'] if x['path']=='events.jsonl')
    if data['source_journal_sha256']!=journal or data['classifier_sha256']!=value['classifier_sha256']:
        return False
    result=json.loads((Path(value['trial'])/'result.json').read_text())
    if row['trial_id']!=result['id'] or row['source_trial']!=value['trial'] or row['reward']!=(result.get('verifier_result') or {}).get('rewards'):
        return False
    if len(ledger)!=len(data['calls']) or {x['call_id'] for x in ledger}!={x['call_id'] for x in data['calls']}:
        raise ValueError('Per-Trial cost ledger does not cover all recorded calls')
    task=Path(result['config']['task']['path']).name
    if any(x['source_journal_sha256']!=journal or x['trial_id']!=result['id'] or x['task_id']!=task for x in ledger):
        raise ValueError('Per-Trial ledger refers to another source')
    return True


def store(trial,value,row,ledger,origin):
    if inputs(trial)!=value:raise ValueError('Recorder changed during export proof construction')
    if not verified_outputs(row,ledger,value):raise ValueError('Canonical outputs do not bind the exact original Recorder')
    body=dict(inputs=value,row=row,ledger=ledger,origin=origin,
        contract='Original full SSE/native equivalence export reused only for identical terminal inputs and identical canonical output SHA')
    blob=json.dumps(body,ensure_ascii=False).encode();digest=hashlib.sha256(blob).hexdigest()
    directory=R/'derived/native-export-cache-r8'/row['trial_id'];directory.mkdir(parents=True,exist_ok=True)
    target=directory/(identity(value)+'-'+digest+'.json')
    temporary=target.with_name(target.name+'.pending-'+uuid4().hex)
    try:
        with temporary.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
        os.link(temporary,target)
    finally:temporary.unlink(missing_ok=True)
    return target


def reuse(trial,value,previous_row,previous_ledger):
    ident=json.loads((trial/'result.json').read_text())['id']
    directory=R/'derived/native-export-cache-r8'/ident;key=identity(value)
    matches=list(directory.glob(key+'-*.json'))
    if len(matches)>1:raise ValueError('Multiple canonical export proofs for identical inputs')
    if matches:
        proof=matches[0];blob=proof.read_bytes()
        if proof.name!=key+'-'+hashlib.sha256(blob).hexdigest()+'.json':raise ValueError('Canonical export cache proof changed')
        body=json.loads(blob)
        if body['inputs']!=value or not verified_outputs(body['row'],body['ledger'],value):
            raise ValueError('Cached canonical export no longer matches exact original evidence')
        return body['row'],body['ledger'],'CACHE_REHASHED'
    if previous_row is None:return None
    if not verified_outputs(previous_row,previous_ledger,value):return None
    reference_count=verify_references(trial,value)
    store(trial,value,previous_row,previous_ledger,dict(kind='ADOPTED_UNCHANGED_LEGACY_RAW_SSE_EXPORT',verified_recorded_references=reference_count))
    return previous_row,previous_ledger,'LEGACY_EXPORT_ADOPTED_AFTER_REFERENCE_VALIDATION'
