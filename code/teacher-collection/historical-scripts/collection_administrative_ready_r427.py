"""Read-only reconciliation of the five reviewed billing-drain setup records."""
import hashlib
import json
from pathlib import Path

PROOF_SHA = 'abc705bcb25cec3a00a9277a76dba6136bed0cef8f500eea211fb4205c6fbc38'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reconcile(root, ready, blocks):
    proof = Path(root) / 'checks/ADMINISTRATIVE_READY_RECONCILIATION_R423.json'
    if not proof.exists():
        return dict(blocks), []
    if sha(proof) != PROOF_SHA:
        raise ValueError('Reviewed administrative reconciliation changed')
    review = json.loads(proof.read_text())
    assert review['passed'] and review['reconciled_verified_environments'] == 5 and not review['unresolved']
    current = dict(blocks)
    reconciled = []
    for ident, declaration in review['cases'].items():
        if ident not in current:
            continue
        receipt = Path(declaration['receipt'])
        if sha(receipt) != declaration['sha256']:
            raise ValueError('Reviewed Ready receipt changed')
        row = json.loads(receipt.read_text())
        binding = row['administrative_admission_reconciliation']
        result_path = Path(binding['original_administrative_result'])
        if (current[ident]['native_result'] != str(result_path)
                or sha(result_path) != binding['original_administrative_result_sha256']
                or current[ident]['native_result_sha256'] != sha(result_path)):
            # A later/different actual setup failure remains a real block.
            continue
        result = json.loads(result_path.read_text())
        error = result.get('exception_info') or {}
        if (error.get('exception_type') != 'ValueError'
                or error.get('exception_message') != 'Admission drained before agent run'
                or result.get('agent_execution') or not result.get('finished_at')
                or (result_path.parent / 'agent/openharness-rollout/events.jsonl').exists()):
            raise ValueError('Reviewed administrative record now contains execution')
        if sha(binding['original_ready_receipt']) != binding['original_ready_receipt_sha256']:
            raise ValueError('Original Ready proof changed')
        if sha(row['placement']) != row['placement_sha256']:
            raise ValueError('Reviewed Ready placement changed')
        observed = ready.get(ident)
        if not observed or observed.get('engine_id') != row['engine_id']:
            raise ValueError('Reviewed environment absent from the current Ready inventory')
        for kind in ['install', 'nop']:
            source = Path(row['native_' + kind + '_trial']) / 'result.json'
            raw = json.loads(source.read_text())
            if (sha(source) != row[kind + '_result_sha256']
                    or observed.get(kind + '_result_sha256') != row[kind + '_result_sha256']
                    or not raw.get('finished_at') or raw.get('exception_info')
                    or raw.get('infrastructure_errors')):
                raise ValueError('Reviewed environment native Result differs')
            if kind == 'nop' and (not (raw.get('verifier') or {}).get('finished_at')
                    or (raw.get('verifier_result') or {}).get('rewards', {}).get('reward') not in [0, 1]):
                raise ValueError('Reviewed official verifier not completed')
        current.pop(ident)
        reconciled.append(dict(task_id=ident, receipt=str(receipt), receipt_sha256=sha(receipt)))
    return current, reconciled
