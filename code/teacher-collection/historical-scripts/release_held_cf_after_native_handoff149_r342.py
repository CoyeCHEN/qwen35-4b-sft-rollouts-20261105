"""Release exactly one temporary setup hold after accepted native R21 authority."""
import datetime
import json
from pathlib import Path

from collection_attempts_r8 import attempt_counts
import collection_readiness_r21 as n

IDENT = 'machine-learning_20260419_065313_002'
R = n.R
BLOCK = R / 'checks/task-source-boundary-reviews-r7' / (IDENT + '.json')
OLD_SHA = '843e8962f68655677f1cdcaebd76092e1a622d07a06dc02026057d4e04f13820'


def main():
    authority_path = R / 'checks/CURRENT_DISPATCH_AUTHORITY_R21.json'
    authority = json.loads(authority_path.read_text())
    manifest_path = Path(authority['manifest'])
    if n.sha(manifest_path) != authority['manifest_sha256']:
        raise ValueError('New Campaign changed')
    manifest = json.loads(manifest_path.read_text())
    if manifest['deployment_config_sha256'] != n.CONFIG_SHA or manifest['source_sha256'] != n.sha(R / 'scripts/run_collection_stream_r21.py'):
        raise ValueError('New authority is outside the exact native acceptance')
    if any(n.sha(R / 'scripts' / name) != digest for name, digest in manifest['helper_sha256'].items()):
        raise ValueError('Frozen controller helper source changed')
    proc = Path('/proc') / str(authority['pid'])
    if str(R / 'scripts/run_collection_stream_r21.py').encode() not in proc.joinpath('cmdline').read_bytes().split(b'\0'):
        raise ValueError('New controller PID identity differs')
    state = json.loads(Path(authority['state_path']).read_text())
    if state['pid'] != authority['pid'] or state['runtime_node'] != '17' or state['runtime_engine_id'] != n.NODE['engine_id'] or state['actual_teacher_trials'] > 8:
        raise ValueError('New native runtime state is not accepted')
    fence = json.loads((R / 'checks/controller-r20-admission-fence-r21.json').read_text())
    if not fence['old_native_admission_disabled'] or n.sha(Path(fence['drain_request'])) != fence['drain_request_sha256']:
        raise ValueError('Old authority is not fenced')
    accepted_path = R / 'checks/controller-r21-offline-acceptance-r337.json'
    accepted = json.loads(accepted_path.read_text())
    if not accepted['passed'] or accepted['deployment_config_sha256'] != n.CONFIG_SHA:
        raise ValueError('Exact native dependency acceptance missing')
    ready = Path(accepted['native_ready_receipt'])
    if n.sha(ready) != accepted['native_ready_receipt_sha256'] or json.loads(ready.read_text())['status'] != 'ENV_READY':
        raise ValueError('New native Ready receipt changed')
    for row in accepted['native_results'].values():
        result = Path(row['trial']) / 'result.json'
        value = json.loads(result.read_text())
        if n.sha(result) != row['result_sha256'] or not value.get('finished_at') or value.get('exception_info') or value.get('infrastructure_errors'):
            raise ValueError('Original native install/NOP failed or changed')
    history = R / 'checks/verifier-dependency-recheck-r314/ADMISSION_BLOCK.json'
    if n.sha(history) != OLD_SHA or n.sha(BLOCK) != OLD_SHA or attempt_counts().get(IDENT) != 1:
        raise ValueError('Preserve changed hold or Teacher budget')
    value = dict(status='ENV_READY', task_id=IDENT, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        reason='Exact original CLI and official NOP passed on private17 SSD; accepted R21 is the unique new-admission authority',
        supersedes_historical_hold=str(history), supersedes_historical_hold_sha256=OLD_SHA,
        native_ready_receipt=str(ready), native_ready_receipt_sha256=n.sha(ready),
        deployment_config_sha256=n.CONFIG_SHA, authority=str(authority_path), authority_sha256=n.sha(authority_path),
        native_acceptance=str(accepted_path), native_acceptance_sha256=n.sha(accepted_path),
        original_task_tests_reward_and_teacher_contract_unchanged=True,
        previous_teacher_attempts_preserved=1, maximum_remaining_teacher_attempts=1,
        source_sha256=n.sha(Path(__file__)), teacher_dispatches_by_this_helper=0)
    intent = R / 'checks/verifier-dependency-recheck-r342/RELEASE_INTENT.json'
    n.freeze(intent, value)
    temp = BLOCK.with_suffix('.r342.pending')
    temp.write_text(json.dumps(value, indent=2))
    temp.chmod(0o600)
    temp.replace(BLOCK)
    n.freeze(intent.parent / 'RELEASE_APPLIED.json', dict(task_id=IDENT, active_gate=str(BLOCK),
        active_gate_sha256=n.sha(BLOCK), intent_sha256=n.sha(intent), teacher_dispatches_by_this_helper=0))
    print(json.dumps(dict(task_id=IDENT, hold_released=True, native_dispatch_left_to_sole_controller=True,
        active_gate_sha256=n.sha(BLOCK), remaining_attempts=1)))


if __name__ == '__main__':
    main()
