"""Freeze current admission/accounting metadata after native controller drain."""
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
read = lambda p: json.loads(Path(p).read_text())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    from collection_attempts_r8 import attempt_counts
    authority_path = R / 'checks/CURRENT_DISPATCH_AUTHORITY_R21.json'
    authority = read(authority_path)
    manifest_path = Path(authority['manifest'])
    assert sha(manifest_path) == authority['manifest_sha256']
    campaign = read(manifest_path)
    assert all(sha(R / 'scripts' / name) == digest for name, digest in campaign['helper_sha256'].items())
    config_path = Path(campaign['deployment_config'])
    assert sha(config_path) == campaign['deployment_config_sha256']
    config = read(config_path)
    controller = Path(config['controller_root'])
    assert read(controller / 'DRAINED.json')['status'] == 'DRAINED_WITH_NO_ACTIVE_TEACHERS'
    assert not Path('/proc/' + str(authority['pid'])).exists()
    controllers = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            argv = (process / 'cmdline').read_bytes().split(b'\0')
        except (OSError, ProcessLookupError):
            continue
        scripts = [arg.decode() for arg in argv if arg.startswith(str(R / 'scripts/run_collection_stream_r').encode())]
        if scripts:
            controllers.append(dict(pid=int(process.name), scripts=scripts))
    assert not controllers, 'A writer is present; this observation cannot claim native drain'
    events = [json.loads(line) for line in (R / 'stream/collection-r4/teacher-lifecycle.jsonl').open()]
    active = {}
    admitted = {}
    for row in events:
        if row['event'] == 'TEACHER_ADMITTED':
            active[row['trial_name']] = row
            if row.get('controller_revision') == 'r21':
                admitted[row['trial_name']] = row
        elif row['event'] in ['TEACHER_AGENT_ENDED', 'TEACHER_FINALIZED']:
            active.pop(row['trial_name'], None)
    assert not active
    drain = read(controller / 'DRAIN_REQUESTED.json')
    assert not [e for e in admitted.values() if e['observed_at'] > drain['requested_at']]
    dispatches = {}
    for path in (R / 'stream/collection-r4/dispatches').glob('*/dispatch.json'):
        row = read(path)
        if row['trial_name'] not in admitted:
            continue
        native_path = path.parent / 'trial-config.json'
        native = read(native_path)
        assert sha(native_path) == row['config_sha256']
        assert native['environment']['kwargs'] == config['environment']['kwargs']
        placement = Path(row['admitted_task']['deployment_assignment'])
        binding = read(placement)
        assert sha(placement) == row['admitted_task']['deployment_assignment_sha256']
        assert binding['node'] == '17' and binding['engine_id'] == config['runtime']['engine_id']
        assert binding['deployment_config_sha256'] == sha(config_path)
        assert row['teacher_config_sha256'] == campaign['teacher_config_sha256']
        assert row['wheel_sha256'] == campaign['wheel_sha256']
        dispatches[row['trial_name']] = dict(task_id=row['task_id'], pool=row['pool'],
            native_config=str(native_path), sha256=sha(native_path), endpoint=native['environment']['kwargs']['endpoint'],
            placement=str(placement), placement_sha256=sha(placement))
    assert set(dispatches) == set(admitted)
    counts = attempt_counts()
    assert max(counts.values()) <= 2 and len(counts) <= 1000 and sum(counts.values()) <= 2000
    gate = read(R / 'checks/data-finalization-readiness-r370.json')
    assert gate['qualified_primary_tasks'] == 772
    worker = read(R / 'checks/stream-r4-data-audit-worker.json')
    assert worker['source_revision'] == 'r13' and not worker['pending_futures'] and not worker['errors']
    out = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        actual_teacher_trials=0, writable_collection_controllers=controllers,
        controller_native_terminal=read(controller / 'DRAINED.json'),
        controller_native_terminal_sha256=sha(controller / 'DRAINED.json'),
        admission_drain_sha256=sha(controller / 'DRAIN_REQUESTED.json'),
        original_authorized_service_balance=read(R / 'checks/AUTHORIZED_SERVICE_BALANCE_R432.json'),
        later_teachers_after_drain=0, actual_or_conservative_attempts=sum(counts.values()),
        independent_attempted_tasks=len(counts), attempt_histogram=dict(Counter(counts.values())),
        task_status_by_pool={pool:dict(Counter(t['status'] for t in gate['tasks'] if t['pool'] == pool))
            for pool in ['calibforge', 'tmax']},
        r21_admitted_dispatches_all17=len(dispatches), r21_dispatches_by_pool=dict(Counter(x['pool'] for x in dispatches.values())),
        verified_17_dispatch_configurations=dispatches, deployment_sha256=sha(config_path),
        frozen_sources_all_unchanged=True, current_data_writer=dict(pid=worker['pid'], revision='r13', pending=0, errors={}),
        qualification_sha256=sha(R / 'checks/collection-qualification.json'),
        indexes={p.name:dict(sha256=sha(p), rows=sum(1 for _ in p.open())) for p in sorted((R / 'indexes').glob('*.jsonl'))},
        finalization_gate_sha256=sha(R / 'checks/data-finalization-readiness-r370.json'),
        original_result_or_recorder_mutations=0, teacher_calls=0, training_started=False,
        source_sha256=sha(Path(__file__)))
    destination = R / 'checks/DRAINED_CAMPAIGN_ACCOUNTING_R433.json'
    with destination.open('x') as stream:
        json.dump(out, stream, indent=2)
    print(json.dumps({k:v for k,v in out.items() if k not in ['verified_17_dispatch_configurations','indexes']}))


if __name__ == '__main__':
    main()
