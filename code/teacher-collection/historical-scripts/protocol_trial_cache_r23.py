"""Cache unchanged terminal protocol rows with full content revalidation.

There is no legacy adoption. Every initial row comes from the unchanged full
protocol scan. Every reuse hashes every Recorder file and the native Result.
"""
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from native_export_cache_r8 import inputs as recorder_inputs
from native_export_cache_r8 import sha, verify_references
from run_collection_stream_r4 import R

CACHE_ROOT = R / 'derived/native-protocol-cache-r23'
POLICY_FILES = [R / 'scripts/audit_native_canary_protocol_before_r23.py',
    R / 'checks/offline-teacher-contract.json',
    R / 'configs/teacher-native-11tools-summary-r1.json']


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def lookup(trial, producer, wheel):
    result_path = trial / 'result.json'
    if not result_path.exists() or not json.loads(result_path.read_text()).get('finished_at'):
        return None, None
    value = recorder_inputs(trial)
    value.update(protocol_producer_sha256=sha(producer), protocol_cache_sha256=sha(Path(__file__)),
        protocol_wheel_sha256=sha(wheel), policy_sha256={str(p):sha(p) for p in POLICY_FILES},
        native_trial_config_sha256=sha(trial / 'config.json') if (trial / 'config.json').exists() else None)
    key = identity(value)
    matches = list((CACHE_ROOT / key[:2]).glob(key + '-*.json'))
    if len(matches) > 1:
        raise ValueError('Ambiguous protocol row cache for identical evidence')
    if not matches:
        return value, None
    path = matches[0]
    blob = path.read_bytes()
    if path.name != key + '-' + hashlib.sha256(blob).hexdigest() + '.json':
        raise ValueError('Protocol cache content digest changed')
    body = json.loads(blob)
    if body['inputs'] != value:
        raise ValueError('Protocol cache does not bind current evidence')
    verify_row(trial, value, body['row'])
    return value, body['row']


def verify_row(trial, value, row):
    result = json.loads((trial / 'result.json').read_text())
    journal = next(x['sha256'] for x in value['files'] if x['path'] == 'events.jsonl')
    if row['trial_directory'] != str(trial) or row['journal_sha256'] != journal:
        raise ValueError('Protocol row belongs to another original Recorder')
    if row['native_result_present'] is not True or row['native_reward'] != (result.get('verifier_result') or {}).get('rewards'):
        raise ValueError('Protocol row changed the original native reward')
    if row['native_exception'] != (result.get('exception_info') or {}).get('exception_type'):
        raise ValueError('Protocol row changed the original native exception')


def store(trial, value, row, producer, wheel):
    verify_row(trial, value, row)
    references = verify_references(trial, value)
    current, prior = lookup(trial, producer, wheel)
    if current != value:
        raise ValueError('Original Recorder or policy changed during protocol scan')
    if prior is not None:
        if prior != row:
            raise ValueError('Full protocol scan disagrees with existing cache')
        return
    body = dict(inputs=value, row=row, verified_artifact_references=references,
        origin='UNCHANGED_FULL_NATIVE_PROTOCOL_SCAN_NO_LEGACY_ADOPTION')
    blob = json.dumps(body, ensure_ascii=False).encode()
    key = identity(value)
    directory = CACHE_ROOT / key[:2]
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (key + '-' + hashlib.sha256(blob).hexdigest() + '.json')
    temporary = target.with_name(target.name + '.pending-' + uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
