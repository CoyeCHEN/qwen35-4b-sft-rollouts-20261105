"""Native LF Loader/Collator diagnostic on all derived real-canary rows.

The reward-zero TMax rows are diagnostics only. No GPU, 4B training, or final
dataset admission is performed. The numerical check uses a tiny CPU model.
"""
import copy
import argparse
import gzip
import hashlib
import inspect
import json
import os
from pathlib import Path

os.environ['CUDA_VISIBLE_DEVICES']=''
import torch
import torch.nn.functional as F
from datasets import Dataset,DatasetDict
from transformers import LlamaConfig,LlamaForCausalLM
from llamafactory.data import get_dataset,get_template_and_fix_tokenizer,SFTDataCollatorWith4DAttentionMask
from llamafactory.hparams import ModelArguments,DataArguments,TrainingArguments
from llamafactory.model import load_tokenizer
from sft.qwen35 import digest,TEMPLATE_SHA

ROOT=Path(os.environ.get('CF_TMAX_AUDIT_ROOT','/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all-canaries',action='store_true')
    args=parser.parse_args()
    suffix='all-v4' if args.all_canaries else 'v4'
    torch.set_num_threads(2);torch.manual_seed(42)
    model_args=ModelArguments(model_name_or_path=os.environ['QWEN35_MODEL_PATH'])
    module=load_tokenizer(model_args);tokenizer=module['tokenizer']
    assert digest(tokenizer.chat_template)==TEMPLATE_SHA
    template=get_template_and_fix_tokenizer(tokenizer,DataArguments(template='qwen3_5',enable_thinking=True,preserve_thinking=True))
    assert digest(tokenizer.chat_template)==TEMPLATE_SHA
    collator=SFTDataCollatorWith4DAttentionMask(template=template,tokenizer=tokenizer,
        processor=module['processor'],model=None,pad_to_multiple_of=8,label_pad_token_id=-100,
        block_diag_attn=False,neat_packing=False,attn_implementation='sdpa',compute_dtype=torch.float32)
    projection=json.loads((ROOT/'checks'/('canary-qwen-projection-'+suffix+'.json')).read_text())
    records=[];windows=[];quarantined=[]
    for item in projection:
        if item['errors'] or not item.get('lengths',{}).get('262144',{}).get('segments'):
            quarantined.append(dict(trial_id=item['trial_id'],reason='Structural errors or no samples within cutoff'))
            continue
        info=item['lengths']['262144'];path=Path(info['cache'])
        assert hashlib.sha256(path.read_bytes()).hexdigest()==info['cache_sha256']
        samples=[json.loads(line) for line in gzip.open(path,'rt')];pool='tmax' if item['task'].startswith('tmax/') else 'calibforge'
        cache=ROOT/'derived'/('canary-loader-diagnostic-'+suffix)/pool
        if args.all_canaries:cache=cache/item['trial_id']
        cache.parent.mkdir(parents=True,exist_ok=True)
        DatasetDict(train=Dataset.from_list([s['row'] for s in samples])).save_to_disk(str(cache))
        data_args=DataArguments(template='qwen3_5',tokenized_path=str(cache),cutoff_len=262144,
            enable_thinking=True,preserve_thinking=True,train_on_prompt=False,packing=False)
        training_args=TrainingArguments(output_dir=str(ROOT/'derived'/('canary-loader-output-'+suffix)/pool/item['trial_id']),
            use_cpu=True,do_train=True,report_to='none',dataloader_num_workers=0)
        loaded=get_dataset(template,model_args,data_args,training_args,'sft',tokenizer,module['processor'])
        data=loaded['train_dataset'];assert len(data)==len(samples)
        rows=[]
        for index,row in enumerate(data):
            expected=samples[index]['row'];assert digest(row)==digest(expected)
            batch=collator([copy.deepcopy(row)]);length=len(row['input_ids'])
            assert batch['input_ids'][0,:length].tolist()==row['input_ids']
            assert batch['labels'][0,:length].tolist()==row['labels']
            assert bool((batch['labels'][0,length:]==-100).all())
            assert int((batch['labels']!=-100).sum())==sum(x!=-100 for x in row['labels'])
            rows.append(dict(index=index,source_input_tokens=length,collated_tokens=batch['input_ids'].shape[-1],
                masked_appended_positions=batch['input_ids'].shape[-1]-length,
                supervised_tokens=int((batch['labels']!=-100).sum()),all_source_positions_preserved=True,
                all_added_positions_masked=True,input_sha256=digest(row['input_ids']),labels_sha256=digest(row['labels'])))
            first=next(i for i,v in enumerate(row['labels']) if v!=-100)
            left=max(0,first-32);right=min(length,first+48)
            windows.append(dict(input_ids=row['input_ids'][left:right],attention_mask=[1]*(right-left),labels=row['labels'][left:right],images=[],videos=[],audios=[]))
        records.append(dict(pool=pool,source_trial=item['trial_id'],rows=rows,cache=str(cache),
            all_original_targets_once=info['all_original_targets_once'],
            all_rows_loaded_through_formal_loader=True,training_admission=False))
    from sft.public_corpus_audit import _numerical_reference
    numerical=_numerical_reference(collator,windows[:2])
    files={}
    for obj in [get_dataset,SFTDataCollatorWith4DAttentionMask]:
        path=Path(inspect.getfile(obj));files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    report=dict(passed=True,records=records,numerical_reference=numerical,
        model_resource=model_args.model_name_or_path,tokenizer_class=type(tokenizer).__module__+'.'+type(tokenizer).__name__,
        quarantined_trials=quarantined,
        native_runtime_files=files,official_template_sha256=TEMPLATE_SHA,cuda_initialized=torch.cuda.is_initialized(),
        scope='All rows of each converted canary diagnostic cache; final independent corpora must repeat this full-cache check',
        raw_success_index_unchanged=True)
    assert not report['cuda_initialized']
    (ROOT/'checks'/('canary-native-loader-'+suffix+'.json')).write_text(json.dumps(report,indent=2));print(json.dumps(report))


if __name__=='__main__':main()
