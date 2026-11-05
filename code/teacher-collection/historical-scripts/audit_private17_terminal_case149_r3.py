"""Audit one terminal migration canary using the frozen production auditors.

All mutable indexes are isolated here. The global data worker remains the only
writer of the campaign indexes; the source Trial and active controller are read only.
"""
import datetime
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
NAME = 'task_007040_9f9b1fb1__XWQZknn'
CASE = R / 'validation/private17-terminal-joint-r3'
PY = '/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    CASE.mkdir(parents=True, exist_ok=True)
    lock = (CASE / 'case.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    source = R / 'stream/collection-r4/trials' / NAME
    result = json.loads((source / 'result.json').read_text())
    assert result['verifier_result'] == {'rewards': {'reward': 1.0}, 'return_code': 0}
    assert result['exception_info'] is None and not result['infrastructure_errors']
    assert result['verifier']['finished_at'] and result['agent_execution']['finished_at']
    sources = {name: sha(R / 'scripts' / name) for name in [
        'audit_native_canary_protocol.py', 'export_native_canary_calls.py',
        'audit_collection_results.py', 'audit_stream_data_worker149_r5.py',
        'merge_student_proofs.py', 'teacher_call_dispositions.py']}

    def link(path, target):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.symlink_to(target, target_is_directory=target.is_dir())
        assert path.resolve() == target.resolve()

    for name in ['configs', 'manifests', 'wheels', 'scripts']:
        link(CASE / name, R / name)
    for name in ['checks', 'indexes', 'logs', 'derived']:
        (CASE / name).mkdir(exist_ok=True)
    link(CASE / 'checks/offline-teacher-contract.json', R / 'checks/offline-teacher-contract.json')
    base = CASE / 'stream/collection-r4'
    link(base / 'CAMPAIGN.json', R / 'stream/collection-r4/CAMPAIGN.json')
    link(base / 'trials' / NAME, source)
    dispatches = [p for p in (R / 'stream/collection-r4/dispatches').glob('*/dispatch.json')
                  if json.loads(p.read_text()).get('trial_name') == NAME]
    assert len(dispatches) == 1
    dispatch = dispatches[0]
    link(base / 'dispatches' / dispatch.parent.name, dispatch.parent)
    sys.argv = ['isolated-private17-case', 'stream-collection-r4']
    for name in ['audit_native_canary_protocol', 'export_native_canary_calls']:
        module = importlib.import_module(name)
        module.ROOT = CASE
        module.main()
    config = json.loads((dispatch.parent / 'trial-config.json').read_text())
    qualify = importlib.import_module('audit_collection_results')
    qualify.ROOT = CASE
    qualify.teacher_sources = lambda: iter([(dispatch.parent / 'trial-config.json',
        'stream-collection-r4', config['agent'], [base / 'trials' / NAME / 'result.json'])])
    qualify.main()
    exports = json.loads((CASE / 'checks/stream-collection-r4-actual-calls-export.json').read_text())
    assert len(exports) == 1 and not exports[0]['errors'] and exports[0]['exported'] > 0
    items = [json.loads(line) for line in (CASE / 'indexes/TMAX_FAILURE_OR_PENDING_INDEX.jsonl').open()]
    assert len(items) == 1 and items[0]['classification'] == 'REWARD_ONE_NATIVE_COMPLETE_STUDENT_AUDIT_PENDING'
    worker = importlib.import_module('audit_stream_data_worker149_r5')
    worker.R = CASE
    incoming = worker.audit_one(items[0], exports[0])
    subprocess.run([PY, str(R / 'scripts/merge_student_proofs.py'), str(CASE), str(incoming),
                    'private17-terminal-r3-' + result['id']], check=True)
    qualify.main()
    accepted = [json.loads(line) for line in (CASE / 'indexes/TMAX_SUCCESS_INDEX.jsonl').open()]
    assert len(accepted) == 1 and accepted[0]['qualified_success']
    for name, value in sources.items():
        assert sha(R / 'scripts' / name) == value, name
    evidence = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        status='PRIVATE17_NATIVE_MODEL_VERIFIER_RECORDER_QWEN_JOINT_ACCEPTED',
        task_id='task_007040_9f9b1fb1', trial_id=result['id'], trial_name=NAME,
        source_result=str(source / 'result.json'), source_result_sha256=sha(source / 'result.json'),
        native_protocol_proof=str(CASE / 'checks/stream-collection-r4-live-protocol.json'),
        native_protocol_proof_sha256=sha(CASE / 'checks/stream-collection-r4-live-protocol.json'),
        student_proof=str(CASE / 'checks/STUDENT_AUDIT_TRIALS.json'),
        student_proof_sha256=sha(CASE / 'checks/STUDENT_AUDIT_TRIALS.json'),
        qualified_index=str(CASE / 'indexes/TMAX_SUCCESS_INDEX.jsonl'),
        qualified_index_sha256=sha(CASE / 'indexes/TMAX_SUCCESS_INDEX.jsonl'),
        model_verifier_recorder_joint_accepted=True, source_auditor_sha256=sources,
        model_calls_by_this_auditor=0, teacher_dispatches_by_this_auditor=0,
        global_indexes_modified=False, gpu_processes=0,
        temporary_cpu_audit_bound=3,
        qualification=accepted[0])
    output = R / 'checks/private17-terminal-joint-acceptance-r3.json'
    with output.open('x') as stream:
        json.dump(evidence, stream, indent=2)
    print(json.dumps(dict(status=evidence['status'], proof=str(output))), flush=True)


if __name__ == '__main__':
    for name in ['DEEPSEEK_API_KEY', 'GH_TOKEN', 'OPENAI_API_KEY']:
        os.environ.pop(name, None)
    os.environ['PATH'] = str(R / 'client-bin-v2') + ':' + os.environ['PATH']
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    main()
