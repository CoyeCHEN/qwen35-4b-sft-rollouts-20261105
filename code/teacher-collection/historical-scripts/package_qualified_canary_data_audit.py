"""Freeze partial corpus integration evidence without a final-release claim."""
from pathlib import Path
import hashlib,json
R=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
root=R/'staging/canary-qualified-r2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
pools={};totals={str(cap):{} for cap in [131072,262144]}
for pool in ['calibforge','tmax']:
 p=root/pool/'DATA_MANIFEST.json';a=root/pool/'NATIVE_CACHE_AUDIT.json'
 m=json.loads(p.read_text());audit=json.loads(a.read_text());assert audit['passed'] and audit['manifest_sha256']==sha(p)
 assert audit['all_caches_and_both_fixed_splits_read_through_formal_loader']
 assert audit['all_row_labels_checked'] and audit['numerical_reference']['passed']
 pools[pool]=dict(qualified_independent_tasks=m['qualified_independent_tasks'],primary_trajectories=m['primary_trajectories'],
  manifest=dict(path=str(p),sha256=sha(p)),native_audit=dict(path=str(a),sha256=sha(a)),length_views=m['length_views'])
for cap in totals:
 for key in ['retained_independent_tasks','original_targets','retained_targets','segments','multi_assistant_samples','complete_tasks','closing_tasks','supervised_tokens']:
  totals[cap][key]=sum(z[key] for p in pools.values() for z in p['length_views'][cap].values())
report=dict(status='PARTIAL_CANARY_CORPUS_INTEGRATION_PASSED_NOT_A_FINAL_RELEASE',
 full_campaign_complete=False,planned_independent_tasks=1000,qualified_independent_tasks=sum(p['qualified_independent_tasks'] for p in pools.values()),
 source_builder_commit='1f49d212bd17346ef1d33c13dd23c4a1f7f99386',
 source_files={str(p.relative_to(R)):sha(p) for p in [R/'sft-code/sft/public_corpus.py',R/'sft-code/sft/public_corpus_audit.py',R/'sft-code/sft/teacher_segments.py']},
 pools=pools,combined_length_views=totals,
 supervised_unit='Each original agent Assistant decision exactly once per length view; current targets plus input-only overlapping histories',
 separate_counts='Independent tasks, primary trajectories, decisions, segments, and segments with multiple new Assistant targets are reported separately',
 split_policy='Original family/task split unchanged. Current CF valid successes happen to all be train; no validation rebalance by success.',
 raw_failures_variants_and_multimodal_traces_retained=True,
 unsupported_multimodal_traces_admitted=0,
 real_compaction_trial='434c6c5b-fbc2-4d08-930a-81e62b70a148',
 real_compaction_source_agent_targets=199,
 real_compaction_reasoning_and_output_contract='Checked on actual agent and auxiliary requests by native CANARY_GATE',
 manual_loss_gradient_reference='Actual cache label windows and native collator, tiny random CPU Llama; all reported gradient errors zero. No Qwen 4B/GPU/kernel equivalence claim.',
 full_final_cache_audit_still_required_after_all_collection=True,release=False)
target=root/'DATA_AUDIT.json';assert not target.exists();target.write_text(json.dumps(report,indent=2));print(json.dumps(dict(status=report['status'],qualified_tasks=report['qualified_independent_tasks'],views=totals)))
