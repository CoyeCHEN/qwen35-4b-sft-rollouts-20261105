"""All supervised positions on three frozen complete inputs, one cold HF at a time.

Native LF collator, FP32 CPU backbone, chunked exact HF output head. No training.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import time
from collections import defaultdict

import torch
import torch.nn.functional as F
from datasets import load_from_disk
from transformers import AutoModelForImageTextToText
from llamafactory.model import load_tokenizer
from llamafactory.hparams import ModelArguments,DataArguments
from llamafactory.data import get_template_and_fix_tokenizer,SFTDataCollatorWith4DAttentionMask

ROOT=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
OLD=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-m2-regression-diagnosis-20261029')
parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['m1','m2']);args=parser.parse_args()
torch.set_num_threads(4);torch.manual_seed(42)
path=Path('/ssd/chenkeyi/qwen35-sft-launch-prep-20261025/hot/runs')/('m1-64k'if args.stage=='m1'else'm2-128k-tb21-10tools-20261026')
inputs=json.loads((OLD/'cpu-probe-inputs.json').read_text())
selected=[min((x for x in inputs if x['dataset']==family and x['split']=='validation'),key=lambda x:len(x['input_ids']))for family in ['m1','m2']]
selected += [x for x in inputs if x.get('selection')=='largest_train_target_with_input_under8192'][:1]
assert len(selected)==3
spec=importlib.util.spec_from_file_location('old_label_categories',OLD/'scripts/audit_supervision.py')
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
module=load_tokenizer(ModelArguments(model_name_or_path='/data/models/Qwen/Qwen3.5-4B'))
template=get_template_and_fix_tokenizer(module['tokenizer'],DataArguments(template='qwen3_5'))
started=time.monotonic()
model=AutoModelForImageTextToText.from_pretrained(path,local_files_only=True,dtype=torch.float32,
    device_map='cpu',attn_implementation='sdpa').eval()
collator=SFTDataCollatorWith4DAttentionMask(template=template,model=model,tokenizer=module['tokenizer'],
    processor=module['processor'],pad_to_multiple_of=8,label_pad_token_id=-100,block_diag_attn=False,
    neat_packing=False,attn_implementation='sdpa',compute_dtype=torch.float32)
data={'m1':load_from_disk('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-sft-preflight-20261023/data/m1-64k'),
      'm2':load_from_disk('/ssd/chenkeyi/qwen35-sft-launch-prep-20261025/m2-teacher149-candidates-v2/tokenized')}
results=[]
for number,sample in enumerate(selected):
    row=data[sample['dataset']][sample['split']][sample['index']]
    assert helpers.digest(row['input_ids'])==sample['input_sha256']
    types={};begin=0
    while begin<len(row['labels']):
        if row['labels'][begin]==-100:begin+=1;continue
        end=begin+1
        while end<len(row['labels'])and row['labels'][end]!=-100:end+=1
        categories,shape=helpers.classes(module['tokenizer'],row['input_ids'][begin:end])
        types.update(zip(range(begin,end),categories));begin=end
    positions=[i for i,value in enumerate(row['labels'])if value!=-100 and i>0]
    batch=collator([copy.deepcopy(row)])
    kwargs={k:v for k,v in batch.items()if k!='labels'and v is not None}
    begin=time.monotonic();groups=defaultdict(list)
    with torch.inference_mode():
        hidden=model.model(**kwargs,use_cache=False).last_hidden_state
        for offset in range(0,len(positions),32):
            indices=positions[offset:offset+32]
            logits=model.lm_head(hidden[0,torch.tensor(indices)-1]).float()
            labels=torch.tensor([row['labels'][i]for i in indices])
            values=F.cross_entropy(logits,labels,reduction='none')
            for index,value in zip(indices,values.tolist()):groups[types[index]].append(value)
        # One complete-model forward independently verifies this chunked head path.
        if number==0:
            indices=torch.tensor(positions[:8])-1
            actual=model(**kwargs,use_cache=False,logits_to_keep=indices).logits[0].float()
            expected=model.lm_head(hidden[0,indices]).float()
            max_error=float((actual-expected).abs().max())
            assert torch.allclose(actual,expected,atol=2e-5,rtol=2e-5)
        else:max_error=None
    record={k:v for k,v in sample.items()if k not in ('input_ids','positions','labels','categories')}
    record.update(all_supervised_positions_evaluated=True,supervised_positions=len(positions),
        category_counts={key:len(value)for key,value in groups.items()},
        category_mean_nll={key:sum(value)/len(value)for key,value in groups.items()},
        total_mean_nll=sum(map(sum,groups.values()))/len(positions),
        collated_positions=batch['input_ids'].shape[-1],real_text_tokens=len(row['input_ids']),
        source_input_sha256=sample['input_sha256'],full_forward_head_max_error=max_error,seconds=time.monotonic()-begin)
    results.append(record)
    proof=dict(model=args.stage,model_path=str(path),cpu_only=True,dtype='float32',attention='sdpa',
        scope='All targets on three representative complete frozen inputs; not full validation corpus or GPU/Liger equivalence',
        samples=results,cuda_initialized=torch.cuda.is_initialized(),elapsed_seconds=time.monotonic()-started)
    (ROOT/'checks'/(args.stage+'-full-target-nll.json')).write_text(json.dumps(proof,indent=2))
    print(json.dumps(dict(model=args.stage,dataset=record['dataset'],split=record['split'],index=record['index'],
        positions=len(positions),category_nll=record['category_mean_nll'],seconds=record['seconds'])),flush=True)
    del hidden,batch,kwargs
assert len(results)==3 and not torch.cuda.is_initialized()
