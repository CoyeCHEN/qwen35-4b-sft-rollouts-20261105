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
names += ['DEPLOYMENT17_ACCEPTANCE_R10.md','checks/old149-native-final-retirement-r8.json',
 'checks/direct17-r13-native-admission-fence-r14.json','checks/direct17-r14-native-config-path-acceptance.json',
 'checks/image-bandwidth-actual-argv-r8.json','stream/direct17-native-source-r14/PLAN.json',
 'stream/direct17-native-source-r14/state.json','scripts/prepare_unstarted_direct17_r14.py']
names += [str(p.relative_to(R)) for p in (R/'stream/direct17-native-source-r14/environment-outcomes').glob('*.json')]
names += ['DEPLOYMENT17_ACCEPTANCE_R11.md','DATA_FREEZE_PROGRESS.md',
 'checks/collection-operational-summary-r11.json','checks/original-private17-build-chain-acceptance-r17.json',
 'checks/private17-buildkit-r16-acceptance.json','configs/campaign-build17-r17.json',
 'checks/private-builder-tmux-stop-root-cause-r20.json','checks/private17-cold-build-directory-fence-r20.json',
 'checks/direct17-build-preparation-handoff-r17.json','checks/direct17-private-builder-r17-launcher.json',
 'stream/direct17-native-source-r13/TERMINAL.json','stream/direct17-native-source-r14/TERMINAL.json',
 'stream/direct17-native-source-r17/PLAN.json','stream/direct17-native-source-r17/state.json',
 'checks/controller-r8-offline-acceptance-r3.json','checks/controller-r8-reader-lifetime-acceptance-r3.json',
 'checks/controller-r7-staging-admission-fence-r8.json','checks/controller-r7-admission-fence-r8.json',
 'checks/CURRENT_DISPATCH_AUTHORITY_R8.json','stream/collection-r4/deployment-r8/CAMPAIGN.json',
 'stream/collection-r4/deployment-r8/state.json','checks/derived-reader-activation-r8.json',
 'checks/attempt-counter-r8-current-parity.json','checks/attempt-counter-r8-boundary-acceptance.json',
 'checks/incremental-export-r8-real-canonical-equivalence.json','checks/qualification-reader-r8-validator-acceptance.json']
names += ['checks/partial-primary-target-audit-r12/'+n for n in ['INPUTS.json','PARTIAL_DATA_TARGET_AUDIT_R12.json','CALIBFORGE_PARTIAL_DATA_MANIFEST_R12.json','TMAX_PARTIAL_DATA_MANIFEST_R12.json']]
for pattern in ['actual-teacher-eight-and-backfill-r8-*.json','actual-teacher-eight-and-backfill-r9-*.json','actual-teacher-eight-and-backfill-r10-*.json','deployment17-rollout-acceptance-r8-*.json']:
 names += [str(p.relative_to(R)) for p in (R/'checks').glob(pattern)]
names += ['scripts/'+n for n in ['run_collection_stream_r8.py','collection_attempts_r8.py','native_export_cache_r8.py','export_native_canary_calls_r8.py','audit_collection_results_r8.py','accept_controller_r8_offline_r3.py','handoff_dispatch17_r8.py','prepare_unstarted_direct17_r17.py','build_tmax_native_oci_ssd17_r17.py','accept_private17_buildkit_r16.py','handoff_private_builder_finite_fence_r20.py','launch_private17_preparation_after_handoff_r17.py','accept_original_private17_build_chain_r17.py','accept_deployment17_rollout_r8.py','capture_teacher_slots149_r10.py']]
names += ['scripts/freeze_collection_progress_r12.py','DEPLOYMENT17_PROGRESS_R12.md','checks/collection-operational-summary-r12.json',
 'checks/readiness-public-boundary-promotion-r22.json','checks/native-transport-recheck-offline-acceptance-r20.json',
 'checks/public-project-boundary-reviews-r18.json','checks/public-assigned-output-boundary-reviews-r22.json',
 'stream/native-transport-recheck17-r20/PLAN.json','stream/native-transport-recheck17-r20/state.json']
names += ['scripts/'+name for name in ['review_public_project_boundaries_r18.py','review_public_cli_boundary_r19.py',
 'review_public_assigned_outputs_r21.py','review_public_assigned_outputs_r22.py','recheck_native_transport_failures17_r20.py']]
for directory in ['stream/native-transport-recheck17-r20/environment-outcomes','stream/native-transport-recheck17-r20/ssd-trial-archives',
 'stream/direct17-native-source-r17/environment-outcomes','checks/native-environment-reviews-r10']:
 names += [str(p.relative_to(R)) for p in (R/directory).glob('*.json')]

names += ['DEPLOYMENT17_PROGRESS_R13.md','checks/collection-operational-summary-r13.json',
 'checks/protocol-cache-r23-contract-acceptance.json','checks/protocol-cache-r23-full-scope-acceptance.json',
 'checks/protocol-cache-r23-activation.json','checks/observer-bounded-protocol-metadata-r26.json',
 'checks/observer-bounded-r26-resource-acceptance.json','checks/monitor-usage-cache-r27-acceptance.json',
 'checks/observer-environment-metadata-r27-acceptance.json','checks/observer-r27-resource-acceptance.json',
 'checks/collection-monitor-hook-result-parser-r28.json','checks/collection-monitor-last-hook-result-r28.json',
 'checks/cf-source-and-prepared-verifier-integrity-r25.json',
 'checks/optimization-verifier-python-public-dependency-probe-r25.json',
 'checks/public-pipeline-boundary-review-r25.json','checks/public-native-recheck-boundary-reviews-r30.json',
 'checks/exact-original-archive-recheck-r29-offline-acceptance.json','checks/exact-original-archive-binding-review-r30.json',
 'checks/native-verifier-timeout-recheck-offline-acceptance-r24.json',
 'manifests/TMAX_READY_ORIGINAL_ARCHIVES_RECHECK_R29.json',
 'stream/native-transport-recheck17-r20/TERMINAL.json']
names += ['scripts/'+name for name in ['audit_native_canary_protocol_r23.py',
 'audit_native_canary_protocol_before_r23.py','protocol_trial_cache_r23.py',
 'accept_protocol_cache_r23.py','accept_protocol_cache_full_scope_r23.py','activate_protocol_cache_reader_r23.py',
 'observe_collection149.py','observe_collection149_before_hook_result_r28.py','monitor_usage_cache_r27.py',
 'audit_cf_verifier_sources_r25.py','review_public_pipeline_boundary_r25.py',
 'recheck_native_verifier_timeouts17_r24.py','recheck_exact_original_archives17_r29.py',
 'review_public_native_rechecks_r30.py','freeze_collection_progress_r13.py','package_collection_metadata_r13.py']]
for scope in ['native-verifier-timeout-recheck17-r24','native-exact-archive-recheck17-r29']:
 names += ['stream/'+scope+'/'+name for name in ['PLAN.json','state.json','TERMINAL.json']]
 for directory in ['environment-outcomes','ssd-trial-archives']:
  names += [str(p.relative_to(R)) for p in (R/'stream'/scope/directory).glob('*.json')]


names += ['DEPLOYMENT17_PROGRESS_R14.md','scripts/freeze_collection_progress_r14.py','scripts/package_collection_metadata_r14.py',
 'checks/collection-operational-summary-r14.json','checks/collection-monitor-last-hook-result-r28.json',
 'checks/controller-r9-native-handoff-progress.json','checks/controller-r9-offline-acceptance-r1.json',
 'checks/controller-r9-image-identity-acceptance-r1.json','checks/CURRENT_DISPATCH_AUTHORITY_R9.json',
 'checks/controller-r8-admission-fence-r9.json','checks/controller-r8-staging-admission-fence-r9.json',
 'checks/exact-cold-resolver17-acceptance-r9.json','configs/campaign-deployment17-r9.json',
 'stream/collection-r4/deployment-r9/CAMPAIGN.json','stream/collection-r4/deployment-r9/state.json',
 'stream/collection-r4/deployment-r8/DRAINED.json','checks/cf-candidate-receipt-mirror-reencoding-r37.json',
 'checks/public-cg-build-goal-source-proof-r39.json','checks/arrived-original-archives-readonly-audit-r34.json',
 'checks/exact-original-archive-recheck-r34-offline-acceptance.json',
 'checks/arrived-original-archives-readonly-audit-r43.json','checks/exact-original-archive-recheck-r43-offline-acceptance.json',
 'checks/historical-attempted-image-retention-gap-r35.json',
 'manifests/CF_PUBLIC_VERIFIER_DEPENDENCY_APPROVALS_R39.json',
 'manifests/CF_PUBLIC_VERIFIER_DEPENDENCY_NODE_BINDINGS_R39.json',
 'manifests/TMAX_READY_ORIGINAL_ARCHIVES_RECHECK_R34.json',
 'manifests/TMAX_READY_ORIGINAL_ARCHIVES_RECHECK_R43.json',
 'manifests/HISTORICAL_ATTEMPTED_IMAGE_RETENTION_DELTA_R35.json',
 'checks/monitor-usage-aggregate-r42-acceptance.json','checks/monitor-usage-aggregate-r42-activation.json',
 'checks/monitor-usage-aggregate-r42-resource/result.json',
 'checks/monitor-usage-aggregate-r42-resource-rejection-and-revert.json',
 'checks/monitor-resource-profile-r41/result.json']
names += ['scripts/'+name for name in ['run_collection_stream_r9.py','collection_readiness_r9.py',
 'campaign_image17_r9.py','resolve_cold_image17_r2.py','inspect_cold_oci_r1.py','handoff_dispatch17_r9.py',
 'accept_controller_r9_offline_r1.py','accept_deployment17_rollout_r9.py',
 'capture_teacher_slots149_r11.py','capture_teacher_slots149_r12.py','capture_teacher_slots149_r13.py',
 'build_cf_public_verifier_dependencies17_r36.py','load_cf_public_dependency_candidate17_r37.py',
 'accept_cf_public_dependency_candidates149_r37.py','approve_cf_public_dependency_candidates_r39.py',
 'accept_arrived_original_archives_r34.py','recheck_exact_original_archives17_r34.py',
 'accept_arrived_original_archives_r43.py','recheck_exact_original_archives17_r43.py',
 'archive_historical_attempted_delta149_r35.py','observe_collection_before_usage_aggregate_r42.py',
 'observe_collection_usage_aggregate_r42_rejected_resource.py','monitor_usage_aggregate_r42.py',
 'accept_monitor_usage_aggregate_r42.py','accept_monitor_resource_r42.py','profile_collection_monitor_r41.py']]
for pattern in ['actual-teacher-eight-and-backfill-r11-*.json','actual-teacher-eight-and-backfill-r12-*.json',
 'actual-teacher-eight-and-backfill-r13-*.json','deployment17-rollout-acceptance-r9-*.json']:
 names += [str(path.relative_to(R)) for path in (R/'checks').glob(pattern)]
for scope in ['native-setup-recheck17-r32','native-exact-archive-recheck17-r34',
 'native-exact-archive-recheck17-r43','historical-attempted-archive-delta-r35',
 'cf-public-dependency-native-candidates-r37']:
 names += ['stream/'+scope+'/'+name for name in ['PLAN.json','state.json','TERMINAL.json']]
 for directory in ['environment-outcomes','candidate-outcomes','ssd-trial-archives','image-materializations','image-release','build-receipts-native-bytes']:
  names += [str(path.relative_to(R)) for path in (R/'stream'/scope/directory).glob('*.json')]
 names += [str(path.relative_to(R)) for path in (R/'stream'/scope/'accepted-revisions').glob('*/*.json')]
names += [str(path.relative_to(R)) for path in (R/'stream/collection-r4/deployment-r9-readiness/placements').glob('*.json')]
names += [str(path.relative_to(R)) for path in (R/'stream/collection-r4/deployment-r9-readiness/ready-revisions').glob('*/*.json')]


names += ['DEPLOYMENT17_PROGRESS_R15.md','checks/collection-operational-summary-r15.json',
 'ENVIRONMENT_1000_STATUS.csv','ENVIRONMENT_FAILURES.md','SAMPLING_STATUS.md',
 'CONTROLLER_AND_MONITOR_STATUS.md','TOOL_CONTRACT_FINAL.md','TRAINING_CONFIG_LOCK.md',
 'checks/CURRENT_DISPATCH_AUTHORITY_R11.json','checks/CURRENT_DISPATCH_AUTHORITY_R12.json',
 'checks/collection-monitor-last-hook-result-r28.json','configs/campaign-deployment17-r11.json',
 'configs/campaign-deployment17-r12.json','manifests/PUBLIC_DEPENDENCY_IMAGE_APPROVALS_R76.json',
 'manifests/PRIVATE17_PUBLIC_IMAGE_BINDINGS_R76.json']
for directory,pattern in [('scripts','*.py'),('checks','*.json'),('manifests','*.json'),('configs','*.json')]:
 for path in (R/directory).glob(pattern):
  versions=[int(v) for v in re.findall(r'(?:[Rr])(\d+)',path.name)]
  if versions and max(versions)>=44:names.append(str(path.relative_to(R)))
for revision in ['r11','r12']:
 names += ['stream/collection-r4/deployment-'+revision+'/'+name for name in ['CAMPAIGN.json','state.json','DRAINED.json']]
 for kind in ['placements','ready-revisions']:
  names += [str(p.relative_to(R)) for p in (R/('stream/collection-r4/deployment-'+revision+'-readiness')/kind).glob('**/*.json')]
for directory in [p for p in (R/'stream').iterdir() if p.is_dir() and any(int(v)>=44 for v in re.findall(r'-r(\d+)',p.name))]:
 names += [str((directory/name).relative_to(R)) for name in ['PLAN.json','state.json','TERMINAL.json','PRIOR_ATTEMPT_GUARD.json']]
 for kind in ['environment-outcomes','candidate-outcomes','ssd-trial-archives','build-receipts','image-materializations','image-release','runtime-bindings','probes']:
  names += [str(p.relative_to(R)) for p in (directory/kind).glob('**/*.json') if '/jobs/' not in str(p) and '/trials/' not in str(p)]
for kind in ['cf-verifier-proxy-approvals-r64','public-image-approvals-r76']:
 names += [str(p.relative_to(R)) for p in (R/'checks'/kind).glob('*.json')]

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
files['checks/METADATA_SNAPSHOT_R15.json']=json.dumps(manifest,indent=2).encode()
p=R/'checks/metadata-snapshot-r15.tar.gz'
with tarfile.open(p,'x:gz') as tar:
 for name,blob in sorted(files.items()):
  info=tarfile.TarInfo(name);info.size=len(blob);info.mode=0o600;tar.addfile(info,io.BytesIO(blob))
print(json.dumps(dict(archive=str(p),archive_bytes=p.stat().st_size,metadata_bytes=sum(map(len,files.values())),files=len(files))))
