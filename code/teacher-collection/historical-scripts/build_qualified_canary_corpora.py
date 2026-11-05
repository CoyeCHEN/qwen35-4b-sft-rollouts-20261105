"""Partial admission integration build; never presented as complete CF500/TMax500."""
import gzip
import json
from pathlib import Path
from sft.public_corpus import build_corpus,file_sha
from sft.public_corpus_audit import audit_corpus
from sft.qwen35 import load_tokenizer,REVISION,TEMPLATE_SHA

r=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
inputs=r/'staging/canary-qualified-r1-inputs'
exports={}
for d in [r/'sources/canary-calls-all',r/'validation/original-env-20261030/sources/canary-calls-all',r/'validation/original-env-final2-20261030/sources/canary-calls-all']:
 for p in d.glob('*.jsonl.gz'):
  with gzip.open(p,'rt') as stream:item=json.loads(next(stream))
  if item['trial_id'] in exports:assert file_sha(p)==file_sha(exports[item['trial_id']])
  exports[item['trial_id']]=p
tokenizer=load_tokenizer()
for pool in ['calibforge','tmax']:
 source=inputs/(pool.upper()+'_SUCCESS_INDEX.jsonl')
 rows=[json.loads(x) for x in source.open()]
 output=r/'staging/canary-qualified-r1'/pool
 manifest=build_corpus(tokenizer,pool=pool,success_records=rows,exports=exports,output=output,
  provenance=dict(scope='PARTIAL_CANARY_INTEGRATION_ONLY',full_campaign_complete=False,
   success_index_sha256=file_sha(source),qwen_revision=REVISION,official_template_sha256=TEMPLATE_SHA,
   encoder_sha256=file_sha(r/'sft-code/sft/teacher_segments.py'),
   corpus_builder_sha256=file_sha(r/'sft-code/sft/public_corpus.py'),
   serving_policy=dict(enable_thinking=True,reasoning_parser='qwen3',tool_call_parser='qwen3_coder',force_reasoning=True,separate_reasoning=True)))
 audit=audit_corpus(output,model_path='/data/models/Qwen/Qwen3.5-4B')
 print(json.dumps(dict(pool=pool,qualified_tasks=manifest['qualified_independent_tasks'],
  native_cache_audit_passed=audit['passed'],row_count=len(audit['rows']),views=manifest['length_views'])),flush=True)
