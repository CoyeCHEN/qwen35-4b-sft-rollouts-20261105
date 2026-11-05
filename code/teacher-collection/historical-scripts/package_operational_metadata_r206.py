"""Freeze only source/config/operational metadata; never raw trajectories or caches."""
import datetime
import hashlib
import io
import json
from pathlib import Path
import tarfile

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
names=['CURRENT_HANDOFF.md','configs/campaign-deployment17-r17.json',
    'stream/collection-r4/deployment-r17/CAMPAIGN.json',
    'checks/CURRENT_DISPATCH_AUTHORITY_R17.json','checks/controller-r16-admission-fence-r17.json',
    'checks/controller-r17-native-handoff-progress.json','checks/controller-r17-agent-phase-acceptance-r198.json',
    'checks/controller-r17-offline-acceptance-r199.json','checks/hot-setup-observer-r202-activation.json',
    'checks/terminal-network-preservation-plan-r182.json','checks/terminal-network-cleanup-r184.json',
    'checks/terminal-scope-cleanup-r190.json','checks/data-writer-handoff-r189.json',
    'checks/data-writer-handoff-wait-r194.json','checks/data-writer-handoff-r194.json',
    'checks/terminal-recorder-isolation-acceptance-r193.json',
    'stream/cleaned-network-scopes-recheck17-r184/TERMINAL.json',
    'stream/cleaned-terminal-scope-recheck17-r190/TERMINAL.json',
    'stream/public-setup-timeout-diagnostics17-r191/TERMINAL.json',
    'stream/verifier-public-proxy-candidate17-r203/TERMINAL.json']
for pattern in ['checks/actual-active-agent-eight-and-backfill-r200-*.json',
                'checks/deployment17-rollout-acceptance-r204-*.json',
                'checks/native-setup-capacity-r196-*.json']:
    found=sorted(R.glob(pattern))
    if found:names.append(str(found[-1].relative_to(R)))
sources=['run_collection_stream_r17.py','collection_readiness_r17.py','handoff_dispatch17_r17.py',
    'freeze_hot_setup_deployment_r197.py','accept_hot_setup_phase_r198.py','accept_controller_r17_offline_r199.py',
    'preserve_cleanup_terminal_networks17_r183.py','preserve_cleanup_terminal_scope17_r185.py',
    'recheck_cleaned_network_scopes17_r184.py','recheck_cleaned_terminal_scope17_r190.py',
    'probe_public_setup_timeouts17_r191.py','accept_verifier_public_proxy_candidate17_r203.py',
    'audit_native_canary_protocol_r192.py','export_native_canary_calls_r187.py',
    'audit_stream_data_worker149_r8.py','accept_terminal_recorder_isolation_r193.py',
    'handoff_isolating_data_writer149_r194.py','capture_active_teacher_phases149_r200.py',
    'collection_reports_r201.py','observe_collection_hot_setup_r202.py','accept_deployment17_rollout_r204.py']
names.extend('scripts/'+name for name in sources)
manifest=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    scope='Code and metadata only. No model content, sessions, images, environment or token cache.',files=[])
included=[]
for name in sorted(set(names)):
    p=R/name
    if not p.exists():continue
    data=p.read_bytes();member=dict(path=name,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),
        included=len(data)<=2*1024*1024)
    manifest['files'].append(member)
    if member['included']:included.append((name,data))
target=R/'checks/operational-metadata-r206.tar.gz'
with target.open('xb') as raw:
    with tarfile.open(fileobj=raw,mode='w:gz') as archive:
        for name,data in included+[('METADATA_MANIFEST_R206.json',json.dumps(manifest,indent=2).encode())]:
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o600
            archive.addfile(info,io.BytesIO(data))
with tarfile.open(target,'r:gz') as archive:
    for member in manifest['files']:
        if member['included']:assert hashlib.sha256(archive.extractfile(member['path']).read()).hexdigest()==member['sha256']
value=dict(path=str(target),bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    included_members=len(included)+1,large_metadata_hash_only=[x for x in manifest['files'] if not x['included']])
with (R/'checks/operational-metadata-r206.json').open('x') as stream:json.dump(value,stream,indent=2)
print(json.dumps(value))
