"""A small explicit metadata backup; excludes raw trajectories, images and caches."""
import datetime
import hashlib
import io
import json
from pathlib import Path
import tarfile

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
D = R / 'checks/operational-metadata-r436'


def main():
    names = [
        'checks/TEACHER_SERVICE_HTTP402_TRIALS_R400.json',
        'checks/TEACHER_SERVICE_BALANCE_DRAIN_R398.json',
        'checks/AUTHORIZED_SERVICE_BALANCE_R432.json',
        'checks/DRAINED_CAMPAIGN_ACCOUNTING_R433.json',
        'checks/RECORDED_COST_TOKEN_SUMMARY_R435.json',
        'checks/collection-qualification.json',
        'checks/stream-r4-data-audit-worker.json',
        'checks/data-finalization-readiness-r370.json',
        'checks/SERVICE_FAILURE_DATA_WRITER_ACCEPTANCE_R413.json',
        'checks/data-writer-handoff-r414.json',
        'checks/ADMINISTRATIVE_READY_RECONCILIATION_R423.json',
        'checks/FORMAL_AVAILABLE_CACHE_AUDIT_SUMMARY_R434.json',
        'checks/FORMAL_PARTIAL_CACHE_AUDIT_SUMMARY_R417.json',
        'checks/PRIVATE_ENGINE_DRAINED_STORAGE_R431.json',
        'checks/MONITOR_DRAINED_RECONCILIATION_R430_ACTIVE.json',
        'checks/monitor-drained-r429-resource/result.json',
        'checks/monitor-drained-r428-source-equivalence.json',
        'checks/collection-monitor-last-hook-result-r28.json',
        'checks/REQUESTED_LEGACY_TRIAL_JOINT_ACCEPTANCE_R347.json',
        'checks/metadata-bandwidth-native-argv-r359.json',
        'checks/ARTIFACT_LOSS_RAW_REWARD_ONE_R382.json',
        'checks/ENCODER_NFC_REPROOF_CASES_R367.json',
        'checks/PRE_AGENT_REMAINING_RECOVERY_SCOPE_R395.json',
        'checks/POST_NATIVE_CLEANUP_RECOVERY_SCOPE_R416.json',
        'checks/TERMINAL_SUBNET_LEAK_SCOPES_R399.json',
        'checks/partial-primary-target-audit-r425/INPUTS.json',
        'configs/campaign-deployment17-r21.json',
        'manifests/SAMPLING_MANIFEST.json',
        'stream/collection-r4/deployment-r21/CAMPAIGN.json',
        'stream/collection-r4/deployment-r21/DRAIN_REQUESTED.json',
        'stream/collection-r4/deployment-r21/DRAINED.json',
        'stream/collection-r4/deployment-r21/state.json',
    ]
    patterns = [
        'checks/actual-active-agent-eight-and-backfill-r322-*.json',
        'checks/deployment17-rollout-acceptance-r323-*.json',
        'stream/public-cpython-native-setup-recovery17-r394/PLAN.json',
        'stream/public-cpython-native-setup-recovery17-r394/TERMINAL.json',
        'stream/public-cpython-native-setup-recovery17-r394/environment-outcomes/*.json',
        'stream/public-cpython-native-setup-recovery17-r415/PLAN.json',
        'stream/public-cpython-native-setup-recovery17-r415/TERMINAL.json',
        'stream/public-cpython-native-setup-recovery17-r415/environment-outcomes/*.json',
        'stream/terminal-teacher-resource-cleanup17-r412/PLAN.json',
        'stream/terminal-teacher-resource-cleanup17-r412/TERMINAL.json',
        'stream/terminal-teacher-resource-cleanup17-r412/*/ACCEPTANCE.json',
        'stream/terminal-teacher-resource-cleanup17-r412/*/PRESERVED_CONTAINER_FILES.json',
        'stream/terminal-teacher-resource-cleanup17-r412/*/SOURCE_ARCHIVE.json',
    ]
    missing = [name for name in names if not (R / name).is_file()]
    if missing:
        raise ValueError('Required metadata missing: ' + repr(missing))
    for pattern in patterns:
        found = sorted(R.glob(pattern))
        if not found:
            raise ValueError('Required bounded evidence pattern empty: ' + pattern)
        if pattern.startswith(('checks/actual-active-agent-eight-', 'checks/deployment17-rollout-')):
            # Earlier snapshots stay in the historical metadata archives.
            found = found[-1:]
        names.extend(str(path.relative_to(R)) for path in found)
    entries = {}
    payloads = {}
    for name in sorted(set(names)):
        path = R / name
        assert not path.is_symlink() and path.stat().st_size < 2_000_000
        blob = path.read_bytes()
        payloads[name] = blob
        entries[name] = dict(bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest())
    assert sum(len(blob) for blob in payloads.values()) < 8_000_000
    D.mkdir(exist_ok=False)
    index = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        purpose='Metadata only; raw Trials, Recorder, requests, token caches and images stay on servers',
        files=entries, files_count=len(entries), total_uncompressed_bytes=sum(map(len,payloads.values())),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        corpus_release_or_training_started=False)
    blob = json.dumps(index, indent=2).encode()
    (D / 'SHA256_INDEX.json').write_bytes(blob)
    payloads['SHA256_INDEX.json'] = blob
    target = D / 'metadata.tar.gz'
    with tarfile.open(target, 'w:gz') as archive:
        for name, data in sorted(payloads.items()):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o600
            archive.addfile(member, io.BytesIO(data))
    print(json.dumps(dict(archive=str(target), archive_bytes=target.stat().st_size,
        archive_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        index_sha256=hashlib.sha256(blob).hexdigest(), files=len(entries))))


if __name__ == '__main__':
    main()
