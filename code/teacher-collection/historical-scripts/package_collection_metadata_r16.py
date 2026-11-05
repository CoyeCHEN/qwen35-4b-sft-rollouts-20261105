"""Add immutable R16 operational/audit metadata to earlier preserved snapshots."""
import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
names=['CURRENT_HANDOFF.md','CURRENT_HANDOFF_before_r15_activation.md','DEPLOYMENT17_PROGRESS_R16.md',
    'ENVIRONMENT_1000_STATUS.csv','ENVIRONMENT_FAILURES.md','TOOL_CONTRACT_FINAL.md',
    'SAMPLING_STATUS.md','TRAINING_CONFIG_LOCK.md','CONTROLLER_AND_MONITOR_STATUS.md',
    'EVIDENCE_INDEX.md','DATA_FREEZE_PROGRESS.md',
    'checks/collection-operational-progress-r16.json','checks/collection-monitor-last-hook-result-r28.json',
    'checks/data-finalization-readiness-r131.json','checks/current-primary-qwen-length-inventory-r135.json',
    'checks/COMPLETED_VERIFIER_ZERO_REVIEWS_R113.json','client-bin-native-r119/ssh','client-bin-v2/rsync',
    'scripts/audit_collection_results_r9.py','scripts/reviewed_verifier_zero_r113.py',
    'scripts/export_native_canary_calls_r8.py','scripts/collection_attempts_r8.py',
    'scripts/freeze_collection_progress_r16.py','scripts/package_collection_metadata_r16.py']
for path in (R/'scripts').glob('*.py'):
    if re.search(r'_r(?:11[1-9]|12\d|13[0-8])(?:\.py|_)',path.name):names.append(str(path.relative_to(R)))
for path in (R/'checks').glob('*.json'):
    if re.search(r'(?:r|R)(?:11[1-9]|12\d|13[0-8])(?:[.-]|$)',path.name):names.append(str(path.relative_to(R)))
for pattern in ['actual-teacher-eight-and-backfill-r124-*.json','actual-teacher-eight-and-backfill-r130-*.json',
        'deployment17-rollout-acceptance-r14-*.json','deployment17-rollout-acceptance-r15-*.json']:
    names.extend(str(path.relative_to(R)) for path in (R/'checks').glob(pattern))
for directory in ['checks/completed-verifier-zero-reviews-r113','checks/monitor-resource-profile-r132',
        'checks/monitor-resource-profile-r134','checks/monitor-health-io-r134-resource',
        'checks/partial-primary-target-audit-r136']:
    names.extend(str(path.relative_to(R)) for path in (R/directory).glob('*.json'))
for revision in ['R14','R15']:
    path=R/'checks'/('CURRENT_DISPATCH_AUTHORITY_'+revision+'.json');authority=json.loads(path.read_text())
    names.append(str(path.relative_to(R)))
    manifest=Path(authority['manifest']);doc=json.loads(manifest.read_text())
    names += [str(manifest.relative_to(R)),str(Path(authority['state_path']).relative_to(R)),
        str(Path(doc['deployment_config']).relative_to(R))]
    names += ['scripts/'+name for name in doc['helper_sha256']]
    for item in ['DRAIN_REQUESTED.json','DRAINED.json']:
        path=Path(authority['state_path']).parent/item
        if path.exists():names.append(str(path.relative_to(R)))
for name in ['controller-r13-admission-fence-r14.json','controller-r13-staging-admission-fence-r14.json',
        'controller-r14-admission-fence-r15.json','controller-r14-staging-admission-fence-r15.json',
        'controller-r14-native-handoff-progress.json','controller-r15-native-handoff-progress.json']:
    names.append('checks/'+name)
scope=R/'stream/native-ssh-pool-candidate17-r120'
for name in ['PLAN.json','state.json','OUTCOME.json']:
    names.append(str((scope/name).relative_to(R)))
for directory in ['probes','initial-outcomes','environment-outcomes','runtime-bindings','ssd-trial-archives']:
    names.extend(str(path.relative_to(R)) for path in (scope/directory).glob('**/*.json'))
files={}
for name in sorted(set(names)):
    path=R/name
    if not path.is_file():continue
    if not path.resolve().is_relative_to(R) or any('/'+part+'/' in '/'+name for part in ['trials','jobs','ssh','sources']) or path.stat().st_size>10*1024**2:
        raise ValueError('Unexpected metadata member: '+name)
    files[name]=path.read_bytes()
manifest=dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    files=[dict(path=name,sha256=hashlib.sha256(blob).hexdigest(),bytes=len(blob)) for name,blob in sorted(files.items())],
    raw_trajectories_copied=0,images_or_environments_copied=0,
    earlier_snapshots_preserved=['metadata-snapshot-r15.tar.gz','metadata-supplement-r15b.tar.gz'],
    scope='Current operational metadata and partial target audit; not final corpus release')
files['checks/METADATA_SNAPSHOT_R16.json']=json.dumps(manifest,indent=2).encode()
archive=R/'checks/metadata-snapshot-r16.tar.gz'
with tarfile.open(archive,'x:gz') as tar:
    for name,blob in sorted(files.items()):
        item=tarfile.TarInfo(name);item.size=len(blob);item.mode=0o600;tar.addfile(item,io.BytesIO(blob))
value=dict(path=str(archive),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),bytes=archive.stat().st_size,files=len(files))
with (R/'checks/metadata-snapshot-r16-identity.json').open('x') as stream:json.dump(value,stream,indent=2)
print(json.dumps(value))
