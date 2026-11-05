"""Supplement the immutable R15 metadata snapshot; never copy raw trajectories."""
import datetime
import hashlib
import io
import json
import tarfile
from pathlib import Path

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
names=['checks/collection-operational-progress-r15b.json','scripts/capture_teacher_slots149_r111.py','scripts/accept_deployment17_rollout_r13.py','CURRENT_HANDOFF.md','ENVIRONMENT_1000_STATUS.csv','ENVIRONMENT_FAILURES.md',
    'SAMPLING_STATUS.md','CONTROLLER_AND_MONITOR_STATUS.md',
    'checks/metadata-snapshot-r15-ssd-copy.json','checks/original-process-list-truncation-evidence-r110.json',
    'checks/ssh-native-preflight-candidate-r108.json','checks/ssh-native-preflight-eight-r108.json',
    'checks/monitor-process-format-r107-activation.json','checks/collection-monitor-last-hook-result-r28.json',
    'checks/deployment-r13-candidate-input-freeze-r104.json','checks/controller-r13-offline-acceptance-r104.json',
    'checks/controller-r13-public-dependency-acceptance-r105.json','checks/controller-r12-admission-fence-r13.json',
    'checks/controller-r12-staging-admission-fence-r13.json','checks/controller-r13-native-handoff-progress.json',
    'configs/campaign-deployment17-r13.json','client-bin-preflight-r108/ssh',
    'scripts/collection_readiness_r12.py','scripts/run_collection_stream_r12.py','scripts/campaign_image17_r12.py',
    'scripts/run_collection_stream_r13.py','scripts/collection_readiness_r13.py','scripts/campaign_image17_r13.py',
    'scripts/handoff_dispatch17_r13.py','scripts/freeze_original_process_deployment_r104.py',
    'scripts/accept_controller_r13_offline_r104.py','scripts/promote_original_process_input_r105.py',
    'scripts/observe_original_startup_process17_r99.py','scripts/observe_original_process_list_format17_r100.py',
    'scripts/observe_original_pytest_process17_r101.py','scripts/observe_original_pytest_process17_r102.py',
    'scripts/accept_original_process_format17_r103.py','scripts/accept_original_process_format17_r106.py',
    'scripts/accept_original_process_format17_r109.py','scripts/freeze_process_observation_r110.py',
    'scripts/observe_collection_process_format_r107.py','scripts/collection_reports_r107.py',
    'scripts/package_collection_metadata_r15b.py']
for revision in ['R12','R13']:
    authority=R/'checks'/('CURRENT_DISPATCH_AUTHORITY_'+revision+'.json')
    if not authority.exists():continue
    names.append(str(authority.relative_to(R)))
    value=json.loads(authority.read_text());manifest=Path(value['manifest'])
    names += [str(manifest.relative_to(R)),str(Path(value['state_path']).relative_to(R))]
    names += ['scripts/'+name for name in json.loads(manifest.read_text())['helper_sha256']]
for pattern in ['actual-teacher-eight-and-backfill-r111-*.json','deployment17-rollout-acceptance-r13-*.json']:
    names += [str(p.relative_to(R)) for p in (R/'checks').glob(pattern)]
for directory in ['checks/deployment-r13-native-approvals-r105','stream/collection-r4/deployment-r13-readiness/placements',
    'stream/collection-r4/deployment-r13-readiness/ready-revisions']:
    names += [str(p.relative_to(R)) for p in (R/directory).glob('**/*.json')]
for scope in ['original-startup-process-observation17-r99','original-startup-process-list-format17-r100',
    'original-startup-pytest-process-observation17-r101','original-startup-pytest-process-observation17-r102',
    'original-process-format-native17-r103','original-process-format-native17-r106','original-process-format-native17-r109']:
    root=R/'stream'/scope
    names += [str((root/name).relative_to(R)) for name in ['PLAN.json','state.json','TERMINAL.json']]
    for directory in ['probes','initial-outcomes','environment-outcomes','runtime-bindings','ssd-trial-archives','image-materializations','image-release']:
        names += [str(p.relative_to(R)) for p in (root/directory).glob('**/*.json')]
files={}
for name in sorted(set(names)):
    path=R/name
    if not path.is_file():continue
    if not path.resolve().is_relative_to(R) or '/trials/' in name or '/jobs/' in name or path.stat().st_size>10*1024**2:
        raise ValueError('Unexpected metadata member: '+name)
    files[name]=path.read_bytes()
manifest=dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    files=[dict(path=name,sha256=hashlib.sha256(blob).hexdigest(),bytes=len(blob)) for name,blob in sorted(files.items())],
    raw_trajectories_copied=0,images_or_environments_copied=0,
    purpose='Current operational sources, native diagnostic metadata and evidence references; final corpus release remains pending.')
files['checks/METADATA_SUPPLEMENT_R15B.json']=json.dumps(manifest,indent=2).encode()
path=R/'checks/metadata-supplement-r15b.tar.gz'
with tarfile.open(path,'x:gz') as tar:
    for name,blob in sorted(files.items()):
        info=tarfile.TarInfo(name);info.size=len(blob);info.mode=0o600;tar.addfile(info,io.BytesIO(blob))
print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size,files=len(files))))
