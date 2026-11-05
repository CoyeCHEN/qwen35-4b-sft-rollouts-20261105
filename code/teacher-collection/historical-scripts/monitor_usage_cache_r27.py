"""Exact compact usage views; raw ledgers remain authoritative and unchanged."""
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

ROOT = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
CACHE_ROOT = ROOT / 'derived/monitor-usage-cache-r27'


def records(path):
    producer = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    directory = CACHE_ROOT / path.name
    head = directory / 'head.json'
    old = None
    if head.exists():
        pointer = json.loads(head.read_text())
        name = Path(pointer['proof'])
        if name.is_absolute() or len(name.parts) != 1:
            raise ValueError('Usage view escaped its owned cache')
        blob = (directory / name).read_bytes()
        if hashlib.sha256(blob).hexdigest() != pointer['sha256']:
            raise ValueError('Usage view body changed')
        old = json.loads(blob)
        if old['producer_sha256'] != producer or old['source'] != str(path):
            raise ValueError('Usage view producer/source changed; use a new cache version')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if old is not None and old['source_sha256'] == digest:
            return old['records']
        prior = {entry[0]:entry for entry in old['records']} if old else {}
        result = []
        stream.seek(0)
        for line in stream:
            key = hashlib.sha256(line).hexdigest()
            if key in prior:
                result.append(prior[key])
                continue
            entry = json.loads(line)
            usage = entry.get('provider_final_usage')
            numeric = {k:v for k,v in (usage or {}).items() if type(v) in [int, float]}
            result.append([key, entry['trial_id'], entry['call_id'], bool(usage), numeric])
        stream.seek(0)
        if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
            raise ValueError('Usage ledger changed in place during its compact view')
    body = dict(source=str(path), source_sha256=digest, producer_sha256=producer, records=result,
        contract='Original file and line order retained; caller still deduplicates trial_id/call_id in original file order')
    blob = json.dumps(body, ensure_ascii=False).encode()
    checksum = hashlib.sha256(blob).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (digest + '-' + checksum + '.json')
    pending = target.with_name(target.name + '.pending-' + uuid4().hex)
    try:
        with pending.open('xb') as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(pending, target)
    finally:
        pending.unlink(missing_ok=True)
    pending = head.with_name('head.pending-' + uuid4().hex)
    pending.write_text(json.dumps(dict(proof=target.name, sha256=checksum)))
    pending.replace(head)
    return result
