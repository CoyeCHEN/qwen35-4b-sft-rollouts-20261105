"""Report current pre-Agent setup blocks without erasing historical Ready proofs."""
import datetime
import hashlib
import json
from pathlib import Path


def instant(value):
    return datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))


def current_setup_blocks(root, ready):
    stream = Path(root) / 'stream/collection-r4'
    latest = {}
    for path in stream.glob('deployment-*/setup-failures/*.json'):
        failure = json.loads(path.read_text())
        result_path = Path(failure['native_result'])
        raw = result_path.read_bytes()
        result = json.loads(raw)
        if failure.get('model_calls') != 0 or result.get('agent_execution') or not result.get('finished_at'):
            raise ValueError('Setup block contains unreviewed Agent execution or incomplete Result')
        ident = failure['task_id']
        finished = instant(result['finished_at'])
        if ident not in latest or finished > latest[ident][0]:
            latest[ident] = (finished, dict(task_id=ident, status='ENV_BLOCKED', reason='A later native pre-Agent setup failed; historical Ready retained, awaiting a newer validated Ready proof', evidence=str(path), native_result=str(result_path), native_result_sha256=hashlib.sha256(raw).hexdigest(), finished_at=result['finished_at']))
    lines=(stream / 'teacher-lifecycle.jsonl').read_text().splitlines()
    for index,line in enumerate(lines):
        try:event=json.loads(line)
        except ValueError:
            if index==len(lines)-1:break
            raise
        if event['event'] == 'TEACHER_ADMITTED':
            ident = event['task_id']
            if ident in latest and instant(event['agent_admitted_at']) > latest[ident][0]:
                latest.pop(ident)
    for ident, proof in ready.items():
        if ident not in latest:
            continue
        result_path = Path(proof['native_nop_trial']) / 'result.json'
        value = json.loads(result_path.read_text())
        if not value.get('finished_at') or instant(value['finished_at']) <= latest[ident][0]:
            continue
        for kind in ['install', 'nop']:
            path = Path(proof['native_' + kind + '_trial']) / 'result.json'
            raw = path.read_bytes()
            result = json.loads(raw)
            if hashlib.sha256(raw).hexdigest() != proof[kind + '_result_sha256'] or not result['finished_at'] or result.get('exception_info') or result['infrastructure_errors']:
                raise ValueError('Newer Ready does not retain its exact clean native Results')
        if not (value.get('verifier') or {}).get('finished_at'):
            raise ValueError('Newer Ready lacks a completed official NOP verifier')
        latest.pop(ident)
    return {ident: value for ident, (_, value) in latest.items()}
