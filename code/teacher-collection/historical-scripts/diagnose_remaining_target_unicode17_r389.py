"""Diagnose the two remaining target round-trip failures without editing them."""
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

E=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
os.environ.update(CUDA_VISIBLE_DEVICES='',QWEN35_MODEL_PATH=str(S/'student-tokenizer-r155'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='1')
sys.path.insert(0,str(E/'sft-code-nfc-prefix-r4'))
from sft.qwen35 import load_tokenizer,normalize_message


def main():
 ident='2b6ff11d-304e-45f2-a3fe-cd56a9aa03ed'
 root=S/'data-canonical-trials-r366'/ident
 proof=json.loads((root/'checks/canary-qwen-projection-all-v4.json').read_text())[0]
 errors={x['call_id'] for x in proof['errors']}
 assert len(errors)==2 and proof['projected']==28 and proof['calls']==30
 source,=(root/'sources/canary-calls-all').glob('*.jsonl.gz')
 tokenizer=load_tokenizer();decode=lambda ids:tokenizer.decode(ids,skip_special_tokens=False,clean_up_tokenization_spaces=False)
 rows=[]
 for line in gzip.open(source,'rt'):
  call=json.loads(line)
  if call['call_id'] not in errors:continue
  history=[normalize_message(x) for x in call['provider_payload']['messages']]
  response=normalize_message(call['assistant_response'])
  options=dict(tools=call['provider_payload'].get('tools'),enable_thinking=True)
  prefix=tokenizer.apply_chat_template(history,tokenize=False,add_generation_prompt=True,**options)
  rendered=tokenizer.apply_chat_template(history+[response],tokenize=False,add_generation_prompt=False,**options)
  assert rendered.startswith(prefix);suffix=rendered[len(prefix):]
  pids=tokenizer.encode(prefix,add_special_tokens=False);sids=tokenizer.encode(suffix,add_special_tokens=False)
  native=tokenizer.apply_chat_template(history,tokenize=True,return_dict=False,add_generation_prompt=True,**options)
  normalize=tokenizer.backend_tokenizer.normalizer.normalize_str
  row=dict(call_id=call['call_id'],actual_native_prefix_token_ids_exact=pids==native,
   decoded_input_equals_official_normalizer=decode(pids)==normalize(prefix),
   decoded_target_equals_original_target=decode(sids)==suffix,
   original_target_affected_by_official_nfc=normalize(suffix)!=suffix,
   decoded_target_equals_normalized_target=decode(sids)==normalize(suffix),
   target_surrogate_count=sum(0xD800<=ord(c)<=0xDFFF for c in suffix),
   no_original_source_or_target_edits=True)
  rows.append(row)
 assert {x['call_id'] for x in rows}==errors
 report=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),trial_id=ident,
  source_export_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),rows=rows,
  whole_trial_remains_quarantined=True,projected_targets_are_not_promoted_as_a_partial_success=True,
  teacher_calls=0,new_gpu_processes=0,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 p=S/'metadata-snapshots/TARGET_UNICODE_QUARANTINE_R389.json'
 with p.open('x') as stream:json.dump(report,stream,indent=2)
 print(json.dumps(report))


if __name__=='__main__':main()
