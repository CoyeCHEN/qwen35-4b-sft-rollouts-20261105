"""Small immutable metadata supplement; excludes raw teacher trajectories."""
import datetime
import hashlib
import io
import json
from pathlib import Path
import tarfile

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def main():
    authority = read(R / 'checks/CURRENT_DISPATCH_AUTHORITY_R9.json')
    manifest = read(Path(authority['manifest']))
    if not all(sha(R / 'scripts' / name) == digest for name,digest in manifest['helper_sha256'].items()):
        raise ValueError('Frozen controller source changed')
    state = read(Path(authority['state_path']))
    qualification = read(R / 'checks/collection-qualification.json')
    slot = next(path for path in sorted((R / 'checks').glob('actual-teacher-eight-and-backfill-r13-*.json'), reverse=True)
        if read(path)['all_eight_current_have_provider_events'] and read(path)['stable_actual_active_trial_names_through_all_probes'])
    rollout = sorted((R / 'checks').glob('deployment17-rollout-acceptance-r9-*.json'))[-1]
    summary = dict(status='PARTIAL_COLLECTION_AND_TARGET_AUDIT_CONTINUING',
        checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        r14_archive_sha256=sha(R / 'checks/metadata-snapshot-r14.tar.gz'),
        controller_state=state, frozen_controller_sources_match=True,
        qualification_checked_at=qualification['checked_at'],
        qualified_independent_tasks={pool:item['qualified_independent_tasks'] for pool,item in qualification['pools'].items()},
        actual_eight_evidence=str(slot), actual_eight_evidence_sha256=sha(slot),
        rollout_evidence=str(rollout), rollout_evidence_sha256=sha(rollout),
        latest_completed_actual_monitor_hook=read(R / 'checks/collection-monitor-last-hook-result-r28.json'),
        activated_monitor_sha256=sha(R / 'scripts/observe_collection.py'),
        monitor_same_resource_acceptance=read(R / 'checks/monitor-health-scope-r48-resource/result.json'),
        generated_protobuf_ready='checks/public-generated-protobuf-boundary-review-r49.json',
        sensor_pipeline_ready='checks/public-sensor-pipeline-readiness-review-r52.json',
        public_goal_deadlock_ready='checks/public-goal-deadlock-readiness-review-r47.json',
        deadlock_preflight_semantics='The original NOP remains VerifierTimeout/no Reward. Unchanged official tests load, the public deadlock is reproduced, and CLI/native resources are ready. No Task goal repaired. Actual teacher success still requires finished official reward1 and all data audits.',
        qwen_partial_length_inventory='checks/current-primary-qwen-length-inventory-r51.json',
        raw_call_accounting='Raw call/Thinking/usage ledgers continue unchanged; the health observer hashes and references them, with its previous full tally explicitly marked historical.',
        all1000_current17_native_ready_claimed=False, official_task_test_reward_changes=0,
        training_started=False, final_corpus_frozen=False)
    destination = R / 'checks/collection-operational-supplement-r14b.json'
    with destination.open('x') as stream:
        json.dump(summary, stream, indent=2)
    names = ['checks/collection-operational-supplement-r14b.json', str(slot.relative_to(R)), str(rollout.relative_to(R)),
        'ENVIRONMENT_1000_STATUS.csv', 'CONTROLLER_AND_MONITOR_STATUS.md', 'SAMPLING_STATUS.md',
        'checks/collection-qualification.json', 'checks/collection-monitor-last-hook-result-r28.json',
        'checks/monitor-health-scope-r48-resource/result.json', 'checks/monitor-health-scope-r48-activation.json',
        'checks/monitor-last-full-call-usage-tally-r48.json', 'checks/current-primary-qwen-length-inventory-r51.json',
        'checks/public-diagnostic-ssd-retention-r51.json', 'checks/public-goal-deadlock-readiness-review-r47.json',
        'checks/public-generated-protobuf-boundary-review-r49.json', 'checks/public-sensor-pipeline-readiness-review-r52.json', 'checks/public-cf-bootstrap-ssd-retention-r52.json',
        'checks/native-environment-reviews-r10/task_005130_c2d9f5c8.json',
        'stream/direct17-native-source-r17/state.json', 'stream/native-exact-archive-recheck17-r43/TERMINAL.json',
        'stream/cf-public-verifier-bootstrap17-r50/PLAN.json', 'stream/cf-public-verifier-bootstrap17-r50/state.json']
    names += ['scripts/' + name for name in ['observe_collection.py','observe_collection_health_scope_r48.py',
        'observe_collection_before_health_scope_r48.py','accept_monitor_resource_r48.py','collection_reports_r48.py',
        'probe_public_bootstrap17_r44.py','probe_public_bootstrap17_r44b.py', 'probe_public_goal_timeouts17_r45.py',
        'collect_trusted_official_tests17_r46.py','review_public_goal_deadlock_r47.py',
        'review_public_generated_protobuf_r49.py','review_public_sensor_pipeline_r52.py','probe_cf_public_verifier_bootstrap17_r50.py',
        'summarize_primary_qwen_lengths_r51.py','package_operational_supplement_r14b.py']]
    for scope in ['public-bootstrap-probes17-r44','public-bootstrap-probes17-r44b',
        'public-goal-timeout-probes17-r45','trusted-test-collection17-r46','cf-public-verifier-bootstrap17-r50']:
        root = R / 'stream' / scope
        names += [str(path.relative_to(R)) for path in root.rglob('*') if path.is_file() and not path.is_symlink()
            and path.suffix in ['.json','.jsonl','.txt','.log']]
    for ident in ['task_002029_b6ef6bbe','task_005130_c2d9f5c8','software-engineering_20260507_170334_011']:
        names += [str(path.relative_to(R)) for path in (R / 'stream/collection-r4/deployment-r9-readiness/ready-revisions' / ident).glob('*.json')]
    files = {}
    for name in sorted(set(names)):
        path = R / name
        if not path.exists():
            continue
        if not path.resolve().is_relative_to(R) or '/trials/' in name or '/jobs/' in name or path.stat().st_size > 10 * 1024**2:
            raise ValueError('Non-metadata or oversized artifact: ' + name)
        files[name] = path.read_bytes()
    index = '# R14B evidence index\n\n' + '\n'.join('- [' + name + '](' + name + ') SHA `' + hashlib.sha256(raw).hexdigest() + '`' for name,raw in sorted(files.items())) + '\n'
    files['EVIDENCE_INDEX_R14B.md'] = index.encode()
    (R / 'EVIDENCE_INDEX_R14B.md').write_bytes(files['EVIDENCE_INDEX_R14B.md'])
    inventory = dict(checked_at=summary['checked_at'], files=[dict(path=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()) for name,raw in sorted(files.items())],
        raw_teacher_trajectories_copied=0, images_or_environments_copied=0)
    files['checks/METADATA_SUPPLEMENT_R14B.json'] = json.dumps(inventory, indent=2).encode()
    archive = R / 'checks/metadata-supplement-r14b.tar.gz'
    with tarfile.open(archive, 'x:gz') as stream:
        for name,raw in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.mode = 0o600
            info.size = len(raw)
            stream.addfile(info, io.BytesIO(raw))
    print(json.dumps(dict(archive=str(archive), sha256=sha(archive), bytes=archive.stat().st_size,
        members=len(files), qualified=summary['qualified_independent_tasks'], actual_teachers=state['actual_teacher_trials'])))


if __name__ == '__main__':
    main()
