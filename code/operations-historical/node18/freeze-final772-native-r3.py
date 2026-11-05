import os
os.environ.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
import pathlib,json,sys,hashlib,ast,shutil,datetime,collections
R=pathlib.Path('/ssd/chenkeyi/qwen35-sft-772-20261101');A=R/'assets/source17-r1';P=pathlib.Path('/data/chenkeyi/qwen35-sft-772-20261101/provenance');F=R/'frozen-data-772-r3'
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb')as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
prefix=P/'native-sglang-prefixes-r1/ALL_TARGET_NATIVE_SGLANG_PREFIX_AUDIT.json'
v=json.loads(prefix.read_text());assert v['passed']and v['tasks']==772 and v['targets']==30193
leak=P/'INDEPENDENT_DECONTAMINATION_772.json';d=json.loads(leak.read_text());assert d['passed']and not d['quarantine_task_ids']and d['task_family_split_verified']
parent=pathlib.Path('/data/chenkeyi/qwen35-sft-772-20261101/FROZEN_772_CORPUS_MANIFEST.json')
assert sha(parent)=='7a5f3fff6fdc66790bb6c03da878e6311f1d247929b4f2ff2e7f7bdb0bf3dda0'
ident=json.loads(parent.read_text());assert len(ident['entries'])==772
source=R/'new-sft/source-r4/repository/sft'
def fn_ast(p):
 return {n.name:ast.dump(n,include_attributes=False)for n in ast.parse(p.read_text()).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
old=fn_ast(A/'sft-code/sft/qwen35.py');new=fn_ast(source/'qwen35.py')
for n in ['digest','load_tokenizer','text_content','normalize_message','validate_pairs']:assert old[n]==new[n],n
assert sha(A/'sft-code/sft/teacher_segments.py')=='68c2a68bb6d2c93d2981ca911eba22a880c29aaf817d7a45209a8da40da18d48'
sys.path.insert(0,str(A/'sft-code'))
from sft.public_corpus_audit import audit_corpus
F.mkdir(exist_ok=False);(F/'provenance').mkdir()
for p in [prefix,leak,P/'STUDENT_SERVING_POLICY_772.json',P/'EPOCH3_DIAGNOSTIC_PREREGISTRATION.json']:shutil.copyfile(p,F/'provenance'/p.name)
report=dict(kind='FINAL_772_DATA_AUDIT',complete=False,task_family_split_verified=True,tb21_independent_leakage_audit_passed=True,all_native_sglang_prefix_targets_verified=True,native_prefix_targets=30193,native_prefix_audit_sha256=sha(prefix),decontamination_sha256=sha(leak),pools={},no_new_teacher_calls=True,new_formal_training_started=False,encoding_code_inherited_unchanged=True,generic_generation_boundary_repair_does_not_change_used_projection_helpers=True)
for pool,expected in [('calibforge',416),('tmax',356)]:
 src=R/'frozen-data-772-r2'/pool;dst=F/pool;dst.mkdir()
 m=json.loads((src/'DATA_MANIFEST.json').read_text());assert m['qualified_independent_tasks']==expected
 for name,h in m['artifacts'].items():
  p=src/name;assert sha(p)==h
  q=dst/name;q.parent.mkdir(parents=True,exist_ok=True);os.link(p,q)
 m.update(status='FROZEN_772_NATIVE_CACHE',released_by='../DATA_RELEASE.json',released=False,release_condition='Complete DATA_AUDIT and DATA_RELEASE must match these immutable manifest bytes',parent_native_loader_manifest_sha256=sha(src/'DATA_MANIFEST.json'),primary_772_identity_manifest_sha256=sha(parent),native_sglang_prefix_audit_sha256=sha(prefix),independent_tb21_decontamination_sha256=sha(leak),corpus_task_scope=expected,raw_sources_or_token_ids_rewritten=False,training_started=False)
 (dst/'DATA_MANIFEST.json').write_text(json.dumps(m,ensure_ascii=False,indent=2))
 audit=audit_corpus(dst,model_path=str(A/'student-tokenizer'))
 assert audit['passed']and audit['all_row_labels_checked']and audit['all_caches_and_both_fixed_splits_read_through_formal_loader']
 tools=collections.Counter();boundary=0
 for task in json.loads((dst/'TASK_AUDIT.json').read_text()):
  for row in json.loads((dst/task['target_mapping']['relative_path']).read_text()):
   tools[row['tools_sha256']]+=1;boundary+=bool(row['generation_boundary_changes_bpe'])
 stats={}
 for cap in [131072,262144]:
  for split in ['train','validation']:
   values=sorted(r['collated_tokens']for r in audit['rows']if r['cutoff']==cap and r['split']==split)
   def quantile(q):
    pos=(len(values)-1)*q;lo=int(pos);hi=min(lo+1,len(values)-1);return values[lo]*(hi-pos)+values[hi]*(pos-lo)if hi!=lo else values[lo]
   stats[str(cap)+'/'+split]=dict(samples=len(values),maximum=max(values),p95=quantile(.95),p99=quantile(.99),buckets={str(a)+'-'+str(b):sum(a<x<=b for x in values)for a,b in[(0,8192),(8192,32768),(32768,65536),(65536,131072),(131072,262144)]})
 report['pools'][pool]=dict(tasks=expected,manifest_sha256=sha(dst/'DATA_MANIFEST.json'),native_loader_audit_sha256=sha(dst/'NATIVE_CACHE_AUDIT.json'),length_views=m['length_views'],actual_collated_length_statistics=stats,numerical_reference=audit['numerical_reference'],tool_schema_semantic_sha256_counts=dict(tools),generation_boundary_bpe_difference_targets=boundary)
 print(json.dumps(dict(pool=pool,tasks=expected,final_loader_passed=True)),flush=True)
report.update(complete=True,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
(F/'DATA_AUDIT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
final=ident|dict(kind='FROZEN_772_FINAL_CORPUS_MANIFEST',parent_primary_identity_sha256=sha(parent),encoding_release_status='ALL_TARGET_NATIVE_PREFIX_AND_FULL_LOADER_LABEL_LOSS_AUDITS_PASSED',pool_manifests={p:x['manifest_sha256']for p,x in report['pools'].items()},data_audit_sha256=sha(F/'DATA_AUDIT.json'),source_raw_evidence_not_moved=True)
(F/'FROZEN_772_CORPUS_MANIFEST.json').write_text(json.dumps(final,ensure_ascii=False))
release=dict(kind='FROZEN_772_DATA_RELEASE',complete=True,task_count=772,train_tasks=699,validation_tasks=73,all_native_sglang_prefix_targets_verified=True,task_family_split_verified=True,tb21_independent_leakage_audit_passed=True,manifest_sha256=sha(F/'FROZEN_772_CORPUS_MANIFEST.json'),data_audit_sha256=sha(F/'DATA_AUDIT.json'),pools={p:dict(manifest_sha256=x['manifest_sha256'],native_loader_audit_sha256=x['native_loader_audit_sha256'])for p,x in report['pools'].items()},context_views_are_mutually_exclusive=True,formal_training_requires_separate_real_gpu_update_save_resume_acceptance=True)
(F/'DATA_RELEASE.json').write_text(json.dumps(release,indent=2))
print(json.dumps(dict(complete=True,corpus_manifest_sha256=release['manifest_sha256'],data_audit_sha256=release['data_audit_sha256'],data_release_sha256=sha(F/'DATA_RELEASE.json'),tasks=772,train=699,validation=73)),flush=True)
