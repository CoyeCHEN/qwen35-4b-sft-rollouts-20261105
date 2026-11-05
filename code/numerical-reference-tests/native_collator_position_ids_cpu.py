"""Exercise the actual LF collator with a real, weightless Qwen model object."""
import copy, hashlib, json, time
from pathlib import Path
import torch
from accelerate import init_empty_weights
from transformers import AutoConfig, AutoModelForImageTextToText, AutoProcessor
from llamafactory.data import SFTDataCollatorWith4DAttentionMask, get_template_and_fix_tokenizer
from llamafactory.hparams import DataArguments
from datasets import load_from_disk

A = Path('/ssd/chenkeyi/qwen35-public-standard-root-cause-20261104')
R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
torch.set_num_threads(4)
path = R/'runs/new-m1-cf416-128k-e5'
processor = AutoProcessor.from_pretrained(path, local_files_only=True)
tokenizer = processor.tokenizer
template = get_template_and_fix_tokenizer(tokenizer, DataArguments(template='qwen3_5', enable_thinking=True, preserve_thinking=True))
cfg = AutoConfig.from_pretrained(path, local_files_only=True)
cfg._attn_implementation = 'eager'
with init_empty_weights(include_buffers=True):
    model = AutoModelForImageTextToText.from_config(cfg)
collator = SFTDataCollatorWith4DAttentionMask(tokenizer=tokenizer, processor=processor,
    template=template, model=model, pad_to_multiple_of=8, label_pad_token_id=-100,
    block_diag_attn=False, neat_packing=False, attn_implementation='flash_attention_2',
    compute_dtype=torch.bfloat16)
assert collator.get_rope_func is not None
rows = [json.loads(l)['row'] for l in (A/'private/INDEPENDENT_STANDARD_REAL32_ROWS.jsonl').read_text().splitlines()]
ds = load_from_disk(str(R/'frozen-data-772-r3/calibforge/cache-131072'))['train']
longest = max(range(len(ds)), key=lambda i:len(ds[i]['input_ids']))
rows.append(ds[longest]); evidence=[]
for i,row in enumerate(rows):
    n=len(row['input_ids']); batch=collator([copy.deepcopy(row)])
    ids=batch['input_ids'][0]; labels=batch['labels'][0]; mask=batch['attention_mask'][0]
    pos=batch['position_ids']; active=mask.bool()
    text_ok=ids[:n].tolist()==row['input_ids'] and labels[:n].tolist()==row['labels']
    masked_ok=bool((mask[n:]==0).all()) and bool((labels[n:]==-100).all())
    expected=torch.arange(n, dtype=pos.dtype)
    position_ok=bool((pos[..., :n]==expected).all())
    evidence.append(dict(index=i, text_length=n, collated_length=len(ids),
        original_input_labels_preserved=text_ok, dummy_and_padding_masked=masked_ok,
        active_text_positions_equal_native_text_arange=position_ok,
        position_shape=list(pos.shape), batch_keys=sorted(batch),
        attended_tokens=int(active.sum()), supervised_tokens=int((labels!=-100).sum())))
    assert text_ok and masked_ok and position_ok, evidence[-1]
report=dict(at=time.time(), cases=len(rows), longest_actual_train_row_index=longest,
    all_passed=True, model_parameters_on_meta=all(p.device.type=='meta' for p in model.parameters()),
    actual_get_rope_index_called=True, cuda_initialized=torch.cuda.is_initialized(),
    forwards=0, optimizer_steps=0, rows=evidence,
    limitation='Validates collator/positions only, not GPU masked dummy-image forward numerical equivalence.')
out=A/'results/NATIVE_LF_COLLATOR_REAL_MODEL_POSITION_IDS_CPU.json'
assert not out.exists(); out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
