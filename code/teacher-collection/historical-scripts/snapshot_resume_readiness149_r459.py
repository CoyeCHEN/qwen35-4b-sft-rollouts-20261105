"""Current admission, environment and bounded buffer evidence without model calls."""
from collections import Counter
import datetime
import json
from pathlib import Path

import collection_readiness_r21 as n
from collection_attempts_r8 import attempt_counts
from run_collection_stream_r22 import freeze


def main():
    R = n.R
    counts = attempt_counts()
    preview_paths = sorted((R/'checks/controller-r22-prelaunch-r444').glob('*.json'))
    previews = [(path,json.loads(path.read_text())) for path in preview_paths]
    actual = max(((path,value) for path,value in previews if value['check_only'] is False),key=lambda item:item[1]['checked_at'])
    path,preview = actual
    observation = json.loads(Path(preview['service_observation']).read_text())
    assert observation['http_status'] == 200 and observation['balance_available'] is False
    assert preview['status'] == 'PRELAUNCH_BLOCKED_ORIGINAL_SERVICE_BALANCE' and len(preview['validated_ready_tasks']) == 22
    assert not preview['environment_blocks'] and not preview['new_controller_started']
    assert not (R/'checks/controller-r21-admission-fence-r22.json').exists() and not (R/'checks/CURRENT_DISPATCH_AUTHORITY_R22.json').exists()
    writers = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            argv = (process/'cmdline').read_bytes().split(b'\0')
        except OSError:
            continue
        if any(value.startswith(str(R/'scripts/run_collection_stream_r').encode()) for value in argv):
            writers.append(int(process.name))
    assert not writers
    active = {}
    for line in (R/'stream/collection-r4/teacher-lifecycle.jsonl').open():
        event = json.loads(line)
        if event['event'] == 'TEACHER_ADMITTED':
            active[event['trial_name']] = event
        elif event['event'] in ['TEACHER_AGENT_ENDED','TEACHER_FINALIZED']:
            active.pop(event['trial_name'],None)
    assert not active
    buffer_path = R/'stream/remaining-resident-buffer17-r458/TERMINAL.json'
    buffer = json.loads(buffer_path.read_text())
    assert buffer['terminal'] and buffer['resident_ready_tasks'] == 8 and buffer['teacher_budget_unchanged']
    resident = []
    for ident,value in buffer['outcomes'].items():
        assert value['status'] == 'VALIDATED_READY_TASK_IMAGE_RESIDENT_ON17'
        assert n.image_info(value['image_id']) is not None
        resident.append(dict(task_id=ident,image_id=value['image_id'],ready_receipt=value['ready_receipt'],ready_receipt_sha256=value['ready_receipt_sha256'],
            known_original_nop_limitation=value['known_original_nop_limitation']))
    qualification_path = R/'checks/collection-qualification.json'
    qualification = json.loads(qualification_path.read_text())
    assert {key:value['qualified_independent_tasks'] for key,value in qualification['pools'].items()} == {'calibforge':416,'tmax':356}
    progress = json.loads((R/'progress.json').read_text())
    assert progress['runtime17_native_ready_by_pool'] == {'calibforge':318,'tmax':435} and not progress['runtime17_current_setup_blocks']
    assert progress['all1000_environment_checks_terminal']
    observer_proof = json.loads((R/'checks/monitor-published-ready-r459-resource/result.json').read_text())
    assert observer_proof['passed'] and observer_proof['source_sha256'] == n.sha(R/'scripts/observe_collection.py')
    worker = json.loads((R/'checks/stream-r4-data-audit-worker.json').read_text())
    assert worker['source_revision'] == 'r13' and not worker['pending_futures'] and not worker['errors']
    assert attempt_counts() == counts
    out = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        status='ALL_REMAINING22_ENVIRONMENTS_READY_WITH_EIGHT_RESIDENT_TASKS_SERVICE_BALANCE_BLOCKED',
        actual_teacher_trials=0,writable_collection_controllers=writers,r22_prepared_not_started=True,
        original_service_balance_available=False,actual_resume_entry_preview=str(path),actual_resume_entry_preview_sha256=n.sha(path),
        service_observation=preview['service_observation'],service_observation_sha256=n.sha(Path(preview['service_observation'])),
        r22_controller_source_sha256=n.sha(R/'scripts/run_collection_stream_r22.py'),r22_deployment_config_sha256=n.sha(R/'configs/campaign-deployment17-r22.json'),
        r22_launcher_source_sha256=n.sha(R/'scripts/handoff_dispatch17_r22.py'),remaining_authorized_tasks=preview['remaining_authorized_tasks'],
        current17_native_ready_by_pool=progress['runtime17_native_ready_by_pool'],current17_setup_blocks={},
        all1000_original_environment_checks_terminal=True,historical_completed_tasks_not_replayed_for17_migration=247,
        prepared_resident_ready_tasks=resident,prepared_buffer_sha256=n.sha(buffer_path),live_teacher_queue_buffer=False,
        images_and_nop_preparation_are_not_actual_teachers=True,actual_or_conservative_attempts=sum(counts.values()),
        independent_attempted_tasks=len(counts),attempt_histogram=dict(Counter(counts.values())),
        qualified_primary_tasks={'calibforge':416,'tmax':356},qualification_sha256=n.sha(qualification_path),
        data_worker=dict(pid=worker['pid'],revision=worker['source_revision'],pending=0,errors={}),
        full_current772_cache_audit_sha256='24430fbef7e873c508b3c699b9cd9854dd602571bc9834ec2dc168b4d81bea41',
        monitor_actual_source_sha256=n.sha(R/'scripts/observe_collection.py'),monitor_postpublication_resource_result=observer_proof,
        formal_corpus_frozen=False,training_started=False,model_calls=0,source_sha256=n.sha(Path(__file__)))
    freeze(R/'checks/RESTORATION_READINESS_CURRENT_R459.json',out)
    print(json.dumps({key:value for key,value in out.items() if key not in ['prepared_resident_ready_tasks','remaining_authorized_tasks','monitor_postpublication_resource_result']}))


if __name__=='__main__':
    main()
