"""Snapshot explicit small operational evidence; no environments or raw model data."""
import datetime
import hashlib
import io
import json
from pathlib import Path
import tarfile

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


def main():
    names = ['CURRENT_HANDOFF.md', 'ENVIRONMENT_1000_STATUS.csv', 'ENVIRONMENT_FAILURES.md',
        'TOOL_CONTRACT_FINAL.md', 'SAMPLING_STATUS.md', 'TRAINING_CONFIG_LOCK.md',
        'CONTROLLER_AND_MONITOR_STATUS.md', 'EVIDENCE_INDEX.md', 'DATA_FREEZE_PROGRESS.md',
        'configs/campaign-deployment17-r21.json', 'checks/CURRENT_DISPATCH_AUTHORITY_R21.json',
        'stream/collection-r4/deployment-r21/CAMPAIGN.json', 'stream/collection-r4/deployment-r21/state.json',
        'checks/controller-r20-admission-fence-r21.json', 'checks/controller-r20-staging-admission-fence-r21.json',
        'checks/controller-r21-native-handoff-progress.json', 'checks/controller-r21-offline-acceptance-r337.json',
        'checks/controller-r21-agent-phase-acceptance-r318.json', 'checks/data-writer-handoff-r313.json',
        'checks/reviewed-data-writer-acceptance-r312.json', 'checks/reviewed-new-zero-r310.json',
        'checks/stream-r4-data-audit-worker.json', 'checks/collection-qualification.json',
        'checks/native-ssh-pool-live-roundtrip-r329.json', 'checks/native-ssh-fallback-repeat-r330.json',
        'checks/native-ssh-missing-short-socket-r331.json', 'checks/native-ssh-stalled-socket-maintenance-r332-refused.json',
        'checks/native-ssh-stalled-socket-maintenance-r333.json', 'checks/native-ssh-roundtrips-after-cleanup-timeout-r353.json',
        'checks/STORAGE_RUNTIME_PROOF_R344.json', 'checks/REQUESTED_LEGACY_TRIAL_JOINT_ACCEPTANCE_R347.json',
        'checks/native-rsync-live-r339.json', 'checks/USER_AUTHORIZED_IMAGE_BANDWIDTH_POLICY_R1.json',
        'checks/image-bandwidth-live-acceptance-r1.json', 'checks/monitor-public-cli-r327-ACTIVE.json',
        'checks/monitor-public-cli-r350-ACTIVE.json', 'checks/collection-monitor-last-hook-result-r28.json',
        'checks/monitor-native-handoff-r349-resource/result.json', 'checks/final-input-freeze-negative-r343.json',
        'checks/verifier-dependency-recheck-r314/ADMISSION_BLOCK.json',
        'checks/verifier-dependency-recheck-r342/RELEASE_INTENT.json',
        'checks/verifier-dependency-recheck-r342/RELEASE_APPLIED.json']
    sources = ['run_collection_stream_r21.py', 'collection_readiness_r21.py', 'handoff_dispatch17_r338.py',
        'audit_stream_data_worker149_r11.py', 'audit_collection_results_r11.py', 'reviewed_verifier_zero_r311.py',
        'cleanup_terminal_native_trial_r334.py', 'recover_transport_setup17_r335.py',
        'accept_remaining_verifier_dependency17_r336.py', 'accept_remaining_verifier_deployment_r337.py',
        'quarantine_stalled_native_ssh_socket149_r332.py', 'quarantine_stalled_native_ssh_socket149_r333.py',
        'release_held_cf_after_native_handoff149_r342.py', 'recover_transport_probe_setup17_r346.py',
        'cleanup_terminal_native_trial_r354.py', 'accept_official_nop_after_cleanup17_r355.py',
        'recover_original_cli_setup17_r357.py', 'freeze_final_corpus_inputs149_r340.py',
        'freeze_final_corpus_inputs149_r352.py', 'observe_collection_native_handoff_r348.py',
        'activate_native_handoff_monitor_r350.py', 'capture_active_teacher_phases149_r322.py',
        'accept_deployment17_rollout_r323.py', 'check_final_data_readiness_r324.py']
    names += ['scripts/' + name for name in sources]
    for pattern in ['checks/actual-active-agent-eight-and-backfill-r279-20261031T18*.json',
        'checks/actual-active-agent-eight-and-backfill-r322-*.json',
        'checks/deployment17-rollout-acceptance-r323-*.json',
        'checks/all-owned-teacher-processes-r232-20261031T18*.json',
        'checks/r20-native-student-joint-r302-20261031T18*.json']:
        names += [str(p.relative_to(R)) for p in R.glob(pattern)]
    for scope in ['public-cpython-native-setup-recovery17-r335', 'signed-debian-native-acceptance17-r336',
        'public-cpython-native-setup-recovery17-r346', 'official-nop-after-cleanup17-r355',
        'public-cpython-native-setup-recovery17-r357']:
        base = R / 'stream' / scope
        names += [str(p.relative_to(R)) for name in ['PLAN.json', 'state.json', 'TERMINAL.json'] if (p := base / name).exists()]
        names += [str(p.relative_to(R)) for p in (base / 'environment-outcomes').glob('*.json')]
    blobs = {}
    for name in sorted(set(names)):
        path = R / name
        blob = path.read_bytes()
        if len(blob) > 4_000_000:
            raise ValueError('Unexpected large metadata member: ' + name)
        if path.suffix == '.json':
            json.loads(blob)
        blobs[name] = blob
    index = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), snapshot_only=True,
        whole_campaign_consistent_input_freeze=False, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        files={name: dict(sha256=hashlib.sha256(blob).hexdigest(), bytes=len(blob)) for name, blob in blobs.items()},
        excluded=['environments', 'images', 'wheels', 'raw request/response or Recorder content', 'token caches', 'credentials'],
        formal_training_started=False)
    blobs['METADATA_INDEX_R358.json'] = json.dumps(index, indent=2).encode()
    archive = R / 'checks/execution-recovery-r358.tgz'
    with tarfile.open(archive, 'x:gz') as stream:
        for name, blob in blobs.items():
            member = tarfile.TarInfo(name)
            member.size = len(blob)
            member.mode = 0o600
            stream.addfile(member, io.BytesIO(blob))
    receipt = dict(archive=str(archive), bytes=archive.stat().st_size,
        sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), members=len(blobs))
    (R / 'checks/execution-recovery-r358-archive.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
