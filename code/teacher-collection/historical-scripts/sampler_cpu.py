"""Inspect native LF/Accelerate batch indices on the actual old Arrow datasets.

No samples are fetched, collated, forwarded, or trained. Joins actual sampler
indices with the already verified row maps; four CPU/Gloo ranks, no CUDA.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile

import torch
from datasets import load_from_disk
from transformers import AutoProcessor,LlamaConfig,LlamaForCausalLM
from llamafactory.hparams import FinetuningArguments,TrainingArguments
from llamafactory.train.sft.trainer import CustomSeq2SeqTrainer

parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
torch.set_num_threads(1)
processor=AutoProcessor.from_pretrained('/data/models/Qwen/Qwen3.5-4B',local_files_only=True)
sources=[('m1',4,
    '/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-sft-preflight-20261023/data/m1-64k',
    '/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-sft-preflight-20261023/manifests/m1-train-rows.jsonl'),
    ('m2',4,'/ssd/chenkeyi/qwen35-sft-launch-prep-20261025/m2-teacher149-candidates-v2/tokenized',
     '/ssd/chenkeyi/qwen35-sft-launch-prep-20261025/m2-teacher149-candidates-v2/train-rows.jsonl')]
results=[]
for name,ga,data_path,index_path in sources:
    data=load_from_disk(data_path)['train'];metadata=list(map(json.loads,Path(index_path).open()))
    assert len(data)==len(metadata)
    torch.manual_seed(42)
    model=LlamaForCausalLM(LlamaConfig(vocab_size=128,hidden_size=16,intermediate_size=32,
        num_hidden_layers=1,num_attention_heads=2,num_key_value_heads=2))
    with tempfile.TemporaryDirectory(prefix='lf-sampler-only-') as temp:
        settings=TrainingArguments(output_dir=temp,use_cpu=True,gradient_accumulation_steps=ga,
            per_device_train_batch_size=1,dataloader_num_workers=0,seed=42,data_seed=42,
            save_strategy='no',report_to='none',ddp_find_unused_parameters=False,disable_tqdm=True)
        trainer=CustomSeq2SeqTrainer(model=model,args=settings,
            finetuning_args=FinetuningArguments(finetuning_type='full'),
            processor=processor,tokenizer=processor.tokenizer,train_dataset=data)
        loader=trainer.get_train_dataloader()
        loader.set_epoch(0)
        indices=[int(index) for batch in loader.batch_sampler for index in batch]
        assert torch.distributed.get_world_size()==4
        ranks=[None]*4;torch.distributed.all_gather_object(ranks,indices)
        counts=Counter(index for rank in ranks for index in rank)
        assert set(counts)==set(range(len(data))) and all(n in (1,2)for n in counts.values())
        repeated=[dict(dataset_index=i,copies=n,supervised_tokens=metadata[i]['loss_tokens'],
            source_identity={k:metadata[i].get(k)for k in ['task_id','task_group','trial_id','call_id','trajectory']})
            for i,n in sorted(counts.items())if n>1]
        results.append(dict(dataset=name,source_unique_rows=len(data),actual_sampler_exposures=sum(counts.values()),
            per_rank_exposures=[len(rank)for rank in ranks],duplicate_rows=len(repeated),duplicates=repeated,
            extra_supervised_tokens=sum((row['copies']-1)*row['supervised_tokens']for row in repeated),
            dropped_rows=0,seed=42,data_seed=42,epoch=0,dataloader_drop_last=settings.dataloader_drop_last,
            actual_loader_class=type(loader).__name__,actual_batch_sampler_class=type(loader.batch_sampler).__name__,
            rank_index_sha256=[hashlib.sha256(json.dumps(rank).encode()).hexdigest()for rank in ranks],
            historical_exact_rank_batch_trace='UNAVAILABLE; this is a native reconstruction with frozen data and actual defaults'))
    del trainer,loader,model,data
    torch.distributed.barrier()
proof=dict(passed=True,scope='Native LF/Accelerate sampler on actual frozen Arrow datasets; no model forward, optimizer or GPU',
    cases=results,cuda_initialized=torch.cuda.is_initialized(),model_updates=0)
assert not proof['cuda_initialized']
if torch.distributed.get_rank()==0:
    with Path(args.output).open('x') as stream:json.dump(proof,stream,indent=2)
    print(json.dumps(proof))
torch.distributed.destroy_process_group()
