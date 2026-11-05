"""Small metadata-only snapshot; excludes raw prompts, responses and images."""
import datetime,hashlib,io,json,re,tarfile
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
index=(R/'EVIDENCE_INDEX.md').read_bytes()
names=re.findall(r'^- \[([^\]]+)\]\([^\n]+\) SHA `[0-9a-f]{64}`',index.decode(),re.M)
names+=['ACTUAL_TEACHER_EIGHT_ACCEPTANCE_R5.md','campaign-state.json',
 'checks/private17-native-task-acceptance-r3.json','checks/private17-canary-registration-r1.json',
 'checks/private17-dependency-index-policy-r3.json','checks/private17-native-ssh-dial-r3.json',
 'checks/collection-monitor-hook90-service-acceptance-r5.json',
 'checks/collection-monitor-lightweight-counter-r5.json','checks/collection-monitor-profiled-cpu-fix-r5.json',
 'checks/collection-monitor-hook90-budget-r5.json','checks/image-bandwidth-native-arguments-live-r5.json']
names += [str(p.relative_to(R)) for p in (R/'checks').glob('actual-teacher-eight-and-backfill-r5-*.json')]
names += [str(p.relative_to(R)) for p in (R/'manifests/runtime-deployments17-r1').glob('*.json')]
names += ['scripts/'+n for n in ['capture_teacher_slots149_r5.py','register_private17_canary149_r1.py','observe_collection.py','collection_reports.py','accept_private17_native_task149_r3.py']]
names += ['ACTUAL_TEACHER_EIGHT_ACCEPTANCE_R7.md','checks/private17-terminal-joint-acceptance-r3.json',
 'checks/CURRENT_DISPATCH_AUTHORITY_R7.json','checks/controller-r6-admission-fence-r7.json',
 'configs/campaign-deployment17-r7b.json','checks/deployment17-r7b-offline-and-resource-acceptance.json',
 'checks/deployment17-r7b-source-promotion.json','checks/native17-bounded-ssh-masters-r6b.json',
 'checks/initial-probe-log-history-integrity-r7.json','checks/monitor-active-selection-cache-r6.json',
 'stream/collection-r4/deployment-r7b/CAMPAIGN.json','stream/collection-r4/deployment-r7b/state.json']
names += [str(p.relative_to(R)) for p in (R/'checks').glob('actual-teacher-eight-and-backfill-r7-*.json')]
names += [str(p.relative_to(R)) for p in (R/'checks').glob('private17-actual-teacher-metadata-r7-*.json')]
names += ['DEPLOYMENT17_ACCEPTANCE_R8.md','checks/collection-monitor-r7-updated-hook-service-acceptance.json',
 'checks/legacy-resident-preparation-admission-fence-r7.json','checks/legacy-resident-preparation-retired-r7.json',
 'checks/native-structural-cache-r7-acceptance.json','checks/native-structural-cache-r7-session-rejection.json',
 'checks/qualification-scope-cache-activation-r6.json','checks/qualification-native-cache-activation-r7.json',
 'checks/direct17-context-staging-r13.json','checks/direct17-native-r13-metadata-artifact-recovery.json',
 'manifests/TMAX_UNSTARTED_DIRECT_SSD17_R13.json','stream/direct17-native-source-r13/PLAN.json',
 'stream/direct17-native-source-r13/state.json','stream/private17-original-network-acceptance-r10/state.json']
names += [str(p.relative_to(R)) for p in (R/'checks').glob('deployment17-rollout-acceptance-r7-*.json')]
names += ['scripts/'+n for n in ['accept_deployment17_rollout_r7.py','capture_teacher_slots149_r7.py',
 'stage_unstarted_native_contexts17_r13.py','prepare_unstarted_direct17_r13.py','audit_collection_results_r7.py',
 'review_public_installation_boundary_r12.py']]
files={}
for name in sorted(set(names)):
 p=R/name
 if not p.exists():continue
 assert p.resolve().is_relative_to(R) and p.is_file() and p.stat().st_size<=10*1024**2
 assert '/trials/' not in name and '/jobs/' not in name and not name.endswith(('.whl','.tar','.zip'))
 files[name]=p.read_bytes()
source_index_sha=hashlib.sha256(index).hexdigest()
for name in names:
 if name in files:
  index=re.sub(rb'(\['+re.escape(name.encode())+rb'\]\([^\n]+\) SHA `)[0-9a-f]{64}`',lambda m:m.group(1)+hashlib.sha256(files[name]).hexdigest().encode()+b'`',index)
files['EVIDENCE_INDEX.md']=index
manifest=dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_evidence_index_sha256=source_index_sha,
 files=[dict(path=n,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b)) for n,b in sorted(files.items())],
 payload='Metadata only; copied index SHA values updated to the actual snapshot bytes. Original remote index remains unchanged.',raw_trajectories_copied=0,images_or_environments_copied=0)
files['checks/METADATA_SNAPSHOT_R9.json']=json.dumps(manifest,indent=2).encode()
p=R/'checks/metadata-snapshot-r9.tar.gz'
with tarfile.open(p,'x:gz') as tar:
 for name,blob in sorted(files.items()):
  info=tarfile.TarInfo(name);info.size=len(blob);info.mode=0o600;tar.addfile(info,io.BytesIO(blob))
print(json.dumps(dict(archive=str(p),archive_bytes=p.stat().st_size,metadata_bytes=sum(map(len,files.values())),files=len(files))))
