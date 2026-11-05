"""A small explicit metadata backup; excludes raw trajectories, images and caches."""
import datetime
import hashlib
import io
import json
from pathlib import Path
import tarfile

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
D = R / 'checks/operational-resume-r460'


def main():
    names = ['checks/AUTHORIZED_SERVICE_BALANCE_R439.json', 'checks/MONITOR_DRAINED_ACTUAL_TICK_R440.json', 'checks/controller-r22-agent-phase-acceptance-r442.json', 'checks/controller-r22-offline-acceptance-r443.json', 'checks/known-verifier-cleanup-revalidation-r452.json', 'checks/original-verifier-failure-cleanup-review-r86.json', 'checks/KNOWN_VERIFIER_READY_ACCEPTANCE_R456.json', 'checks/KNOWN_VERIFIER_READY_AND_MONITOR_R457_ACTIVE.json', 'checks/monitor-known-verifier-r454-source-equivalence.json', 'checks/monitor-known-verifier-r455-resource/result.json', 'checks/monitor-published-ready-r459-resource/result.json', 'checks/TRAINING_CANDIDATE_IDENTITIES_CURRENT_R459.json', 'checks/RESTORATION_READINESS_CURRENT_R459.json', 'checks/collection-qualification.json', 'checks/collection-monitor-last-hook-result-r28.json', 'checks/stream-r4-data-audit-worker.json', 'configs/campaign-deployment17-r22.json', 'stream/official-nop-stall-diagnostic17-r450/PLAN.json', 'stream/official-nop-stall-diagnostic17-r450/TERMINAL.json', 'stream/official-nop-stall-diagnostic17-r450/initial-outcome.json', 'stream/official-nop-stall-diagnostic17-r450/READY_CANDIDATE_R452.json', 'stream/remaining-resident-buffer17-r458/PLAN.json', 'ENVIRONMENT_1000_STATUS.csv', 'ENVIRONMENT_FAILURES.md', 'TOOL_CONTRACT_FINAL.md', 'SAMPLING_STATUS.md', 'TRAINING_CONFIG_LOCK.md', 'CONTROLLER_AND_MONITOR_STATUS.md', 'EVIDENCE_INDEX.md', 'scripts/run_collection_stream_r22.py', 'scripts/collection_readiness_r22.py', 'scripts/handoff_dispatch17_r22.py', 'scripts/accept_agent_phase_r442.py', 'scripts/accept_resume_controller_r443.py', 'scripts/observe_collection_resume_r445.py', 'scripts/check_final_data_readiness_r446.py', 'scripts/freeze_final_corpus_inputs149_r447.py', 'scripts/diagnose_official_nop_stall149_r450.py', 'scripts/refresh_known_verifier_review149_r452.py', 'scripts/collection_current_setup_blocks_r453.py', 'scripts/observe_collection_known_verifier_r454.py', 'scripts/accept_monitor_resource_r455.py', 'scripts/accept_known_verifier_ready149_r456.py', 'scripts/activate_known_verifier_ready149_r457.py', 'scripts/prewarm_remaining_buffer149_r458.py', 'scripts/snapshot_resume_readiness149_r459.py', 'scripts/accept_published_ready_monitor_r459.py']
    patterns = ['checks/controller-r22-prelaunch-r444/*.json', 'checks/service-restoration-r22/*.json', 'stream/collection-r4/deployment-r21-readiness/ready-revisions/known-verifier-revalidation-r452/*.json']
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
