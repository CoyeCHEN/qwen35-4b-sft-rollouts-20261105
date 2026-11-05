import os
os.environ['CUDA_VISIBLE_DEVICES']=''
os.environ['OMP_NUM_THREADS']='2'
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['TOKENIZERS_PARALLELISM']='false'
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
import pathlib,json,sys,shutil,hashlib,datetime,numpy as np
R=pathlib.Path('/ssd/chenkeyi/qwen35-sft-772-20261101');A=R/'assets/source17-r1';F=R/'frozen-data-772-r2'
sys.path.insert(0,str(A/'sft-code'))
from sft.public_corpus_audit import audit_corpus
from datasets import load_from_disk
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb')as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
F.mkdir(exist_ok=False)
summary=dict(kind='772_EXPLICIT_USER_SCOPE_FULL_NATIVE_LOADER_ACCEPTANCE',encoding_frozen=True,formal_admission=False,sglang_all_target_gate_pending=True,pools={},source_772_manifest_sha256=sha('/data/chenkeyi/qwen35-sft-772-20261101/FROZEN_772_CORPUS_MANIFEST.json'),qwen_revision='851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a',no_new_teacher_calls=True)
for pool in ['calibforge','tmax']:
 src=A/'new-corpus-r426'/pool;dst=F/pool;shutil.copytree(src,dst)
 (dst/'NATIVE_CACHE_AUDIT.json').rename(dst/'SOURCE_PARTIAL_NATIVE_CACHE_AUDIT_R426.json')
 p=dst/'DATA_MANIFEST.json';m=json.loads(p.read_text())
 m.update(status='FROZEN_772_TOKEN_CACHE_PENDING_ALL_NATIVE_SGLANG_PREFIX_GATE',scope='User fixed772 primary tasks, CF416/TMax356; supersedes full1000 completion gate',canonical_model_resource=str(A/'student-tokenizer'),source_evidence_node='17; original evidence paths are references, not18 input data dependencies',local_cache_root=str(dst),original_partial_manifest_sha256=sha(src/'DATA_MANIFEST.json'),released=False,training_started=False)
 m['provenance']=m['provenance']|dict(scope='FIXED_772_PRIMARY_SUCCESSES',all1000_completion_required=False,frozen_scope_authorization='User 2026-11-01',primary_772_identity_manifest_sha256=summary['source_772_manifest_sha256'])
 p.write_text(json.dumps(m,ensure_ascii=False,indent=2))
 audit=audit_corpus(dst,model_path=str(A/'student-tokenizer'))
 assert audit['passed']and audit['all_caches_and_both_fixed_splits_read_through_formal_loader']and audit['all_row_labels_checked']
 lengths={}
 for cap in [131072,262144]:
  data=load_from_disk(str(dst/f'cache-{cap}'))
  for split in ['train','validation']:
   arr=np.array([len(row['input_ids'])+66 for row in data[split]],dtype=np.int64)
   lengths[f'{cap}/{split}']=dict(samples=len(arr),minimum=int(arr.min()),maximum=int(arr.max()),p95=float(np.percentile(arr,95)),p99=float(np.percentile(arr,99)),buckets={str(l)+'-'+str(r):int(((arr>l)&(arr<=r)).sum())for l,r in [(0,8192),(8192,32768),(32768,65536),(65536,131072),(131072,262144)]})
 summary['pools'][pool]=dict(tasks=m['qualified_independent_tasks'],manifest_sha256=sha(p),native_loader_audit_sha256=sha(dst/'NATIVE_CACHE_AUDIT.json'),all_labels_checked=True,manual_loss_gradient_reference=audit['numerical_reference'],length_views=m['length_views'],length_statistics=lengths)
 (F/(pool.upper()+'_DATA_AUDIT.json')).write_text(json.dumps(summary['pools'][pool]))
 print(json.dumps(dict(pool=pool,native_loader_passed=True,tasks=m['qualified_independent_tasks'])),flush=True)
summary.update(native_loader_audit_complete=True,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
(F/'DATA_AUDIT_NATIVE_LOADER.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(dict(full_loader_complete=True,sglang_all_target_gate_pending=True,formal_admission=False)),flush=True)
