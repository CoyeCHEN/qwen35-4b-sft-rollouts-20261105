"""Snapshot small deployment/code/audit metadata; exclude environments and raw traces."""
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
OUT = R / 'checks/operational-metadata-r299'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=False)
    declaration=json.loads((R/'configs/campaign-deployment17-r20.json').read_text())
    names=['CURRENT_HANDOFF.md','configs/campaign-deployment17-r20.json','configs/public-cpython-bootstrap-r273.py','configs/public-cpython-bootstrap-r273.compose.json','controller-runtime-r270/ACCEPTANCE.json',
        'checks/CURRENT_DISPATCH_AUTHORITY_R20.json','checks/controller-r19-admission-fence-r20.json','checks/controller-r19-staging-admission-fence-r20.json','checks/controller-r20-native-handoff-progress.json','checks/controller-r20-agent-phase-acceptance-r275.json','checks/controller-r20-offline-acceptance-r288.json',
        'checks/monitor-current-setup-r295-resource/result.json','checks/monitor-public-cli-r297-ACTIVE.json','checks/collection-monitor-last-hook-result-r28.json','checks/stream-r4-data-audit-worker.json',
        'stream/collection-r4/deployment-r20/CAMPAIGN.json','stream/collection-r4/deployment-r20/state.json','stream/public-cpython-native-prototype17-r274/environment-outcomes/task_007402_0a45b61a.json','stream/public-cpython-native-prototype17-r274/TERMINAL.json','stream/public-cpython-native-setup-recovery17-r277/PLAN.json','stream/public-cpython-native-setup-recovery17-r277/state.json']
    sources=['run_collection_stream_r20.py','collection_readiness_r20.py','handoff_dispatch17_r20.py','accept_public_cli_controller_r288.py','recover_public_cli_setup17_r277.py','capture_active_teacher_phases149_r279.py','accept_deployment17_rollout_r280.py','audit_r20_native_and_student_r302.py','observe_collection_current_setup_r293.py','collection_current_setup_blocks_r293.py','collection_reports_r294.py','test_current_setup_precedence_r296.py','check_final_data_readiness_r281.py','prepare_isolated_controller_runtime149_r270.py','accept_public_cpython_native17_r274.py','prepare_student_runtime_contract17_r257.py','prepare_student_protocol_configs17_r256.py']
    names += ['scripts/'+name for name in sources]
    for pattern in ['checks/actual-active-agent-eight-and-backfill-r279-*.json','checks/deployment17-rollout-acceptance-r280-*.json','checks/all-owned-teacher-processes-r232-20261031T1649*.json','checks/r20-native-student-joint-r302-*.json','checks/data-writer-live-io-r301-*.json','checks/native-r20-setup-phases-r298-*.json']:
        names += [str(path.relative_to(R)) for path in R.glob(pattern)]
    names += [str(path.relative_to(R)) for path in (R/'stream/public-cpython-native-setup-recovery17-r277/environment-outcomes').glob('*.json')]
    entries={}
    for name in sorted(set(names)):
        source=R/name
        if not source.is_file():raise FileNotFoundError(source)
        target=OUT/'node149'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        entries[str(target.relative_to(OUT))]=dict(sha256=sha(target),bytes=target.stat().st_size)
    remote=['staging-private-engine17-r1/public-python-origin-cache-r265/state.json','staging-private-engine17-r1/public-python-origin-cache-r265/PUBLIC_CACHE_SERVICE_R266.json','provider-public-cache-r268/ACCEPTANCE.json','provider-public-cache-r268/BUILD_ACCEPTANCE_R269.json','provider-public-cache-r268/6.log','provider-public-cache-r268/TY_PACKAGE_CHECK_EXPLICIT_RUNTIME.log','provider-maintained-source-r286/ACCEPTANCE.json','provider-maintained-source-r286/4.log','provider-maintained-source-r286/TY_PACKAGE_CHECK_EXPLICIT_RUNTIME.log','metadata-snapshots/TY_PACKAGE_RUNTIME_ACCEPTANCE_R291.json']
    listing=OUT/'REMOTE17_FILES.txt';listing.write_text('\n'.join(remote)+'\n')
    subprocess.run(['rsync','-a','--relative','--files-from='+str(listing),'-e',shlex.join(declaration['ssh']),declaration['host']+':'+declaration['runtime']['ssd_root']+'/',str(OUT/'node17')+'/'],check=True,timeout=300)
    for target in sorted((OUT/'node17').rglob('*')):
        if target.is_file():entries[str(target.relative_to(OUT))]=dict(sha256=sha(target),bytes=target.stat().st_size)
    report=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),snapshot_only=True,source_sha256=sha(Path(__file__)),files=entries,excluded=['raw Recorder/model request/response content','Task environments/images/Python archives/wheels','token caches/tokenizer files/model weights','credentials/process environments'],training_started=False)
    (OUT/'METADATA_INDEX_R299.json').write_text(json.dumps(report,indent=2))
    archive=R/'checks/operational-metadata-r299.tgz'
    with tarfile.open(archive,'x:gz') as stream:
        for path in sorted(OUT.rglob('*')):
            if path.is_file():stream.add(path,arcname=str(path.relative_to(OUT)),recursive=False)
    receipt=dict(archive=str(archive),sha256=sha(archive),bytes=archive.stat().st_size,files=len(entries)+2)
    (R/'checks/operational-metadata-r299-archive.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt))


if __name__=='__main__':
    main()
