"""CPU mathematical golden test, explicitly NOT a 4B model-quality experiment."""
import copy,json,tempfile,time
from pathlib import Path
import torch
from datasets import Dataset
from transformers import Qwen3_5TextConfig,Qwen3_5ForCausalLM,Seq2SeqTrainingArguments
from trl import SFTConfig,SFTTrainer
from llamafactory.train.sft.trainer import CustomSeq2SeqTrainer
from llamafactory.hparams import FinetuningArguments, TrainingArguments as LFTrainingArguments
from transformers import AutoProcessor

A=Path('/ssd/chenkeyi/qwen35-public-standard-root-cause-20261104')
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');torch.set_num_threads(4);torch.manual_seed(42)
processor=AutoProcessor.from_pretrained(R/'runs/new-m1-cf416-128k-e5',local_files_only=True)
cfg=Qwen3_5TextConfig(vocab_size=128,hidden_size=32,intermediate_size=64,num_hidden_layers=2,
    num_attention_heads=2,num_key_value_heads=1,head_dim=16,
    linear_conv_kernel_dim=4,linear_key_head_dim=16,linear_value_head_dim=16,
    linear_num_key_heads=1,linear_num_value_heads=1,
    layer_types=['linear_attention','full_attention'],max_position_embeddings=128,
    eos_token_id=2,pad_token_id=0,bos_token_id=1,use_cache=False,
    rope_parameters={'rope_type':'default','rope_theta':10000.,'partial_rotary_factor':0.25,'mrope_section':[1,1,0]})
cfg._attn_implementation='eager';base=Qwen3_5ForCausalLM(cfg)
rows=[{'input_ids':[1,10,11,12,13,14,15,2],'attention_mask':[1]*8,'labels':[-100]*5+[14,15,2]},
      {'input_ids':[1,21,22,23,24,25,26,27,28,2],'attention_mask':[1]*10,'labels':[-100]*3+[23,24,25,26,27,28,2]}]
def batch(rs):return {k:torch.tensor([r[k]for r in rs])for k in ['input_ids','attention_mask','labels']}
reference=copy.deepcopy(base);reference.train();opt=torch.optim.AdamW(reference.parameters(),lr=1e-3,betas=(.9,.999),eps=1e-8,weight_decay=0)
losses=[]
for row in rows:
    loss=reference(**batch([row])).loss;losses.append(float(loss.detach()));(loss/2).backward()
manual_grad=torch.cat([p.grad.flatten()for p in reference.parameters()if p.grad is not None]);opt.step()
results=[]
for name in ['actual_public_LF_Trainer','public_TRL_Trainer']:
    model=copy.deepcopy(base);out=A/'controls/cpu-golden'/name;assert not out.exists()
    common=dict(output_dir=str(out),use_cpu=True,bf16=False,fp16=False,
        per_device_train_batch_size=1,gradient_accumulation_steps=2,max_steps=1,
        learning_rate=1e-3,optim='adamw_torch',adam_beta1=.9,adam_beta2=.999,adam_epsilon=1e-8,
        weight_decay=0.,max_grad_norm=0.,lr_scheduler_type='constant',warmup_ratio=0.,
        save_strategy='no',eval_strategy='no',report_to='none',seed=42,data_seed=42,
        disable_tqdm=True,remove_unused_columns=False,dataloader_num_workers=0)
    if name=='actual_public_LF_Trainer':
        trainer=CustomSeq2SeqTrainer(model=model,args=LFTrainingArguments(**common),
            finetuning_args=FinetuningArguments(finetuning_type='full'),processor=processor,
            tokenizer=processor.tokenizer,train_dataset=Dataset.from_list(rows),data_collator=batch)
    else:
        trainer=SFTTrainer(model=model,args=SFTConfig(**common,dataset_kwargs={'skip_prepare_dataset':True},
            max_length=None,packing=False,padding_free=False,completion_only_loss=False,
            assistant_only_loss=False,use_liger_kernel=False),
            processing_class=processor.tokenizer,train_dataset=Dataset.from_list(rows),data_collator=batch)
        trainer.model_accepts_loss_kwargs=False
    result=trainer.train()
    delta=torch.cat([(p-q).flatten()for p,q in zip(model.parameters(),reference.parameters())])
    ref_update=torch.cat([(p-q).flatten()for p,q in zip(reference.parameters(),base.parameters())])
    entry=dict(trainer=name,optimizer_steps=trainer.state.global_step,train_loss=result.training_loss,
        expected_mean_row_loss=sum(losses)/2,model_accepts_loss_kwargs=trainer.model_accepts_loss_kwargs,
        max_abs_parameter_difference_from_manual_rowmean_AdamW=float(delta.abs().max()),
        relative_l2_update_error=float(delta.norm()/ref_update.norm()))
    assert entry['max_abs_parameter_difference_from_manual_rowmean_AdamW']<2e-6,entry
    results.append(entry)
token_ref=copy.deepcopy(base);token_ref.train()
for row in rows:(token_ref(**batch([row])).loss*sum(x!=-100 for x in row['labels'])/10).backward()
token_grad=torch.cat([p.grad.flatten()for p in token_ref.parameters()if p.grad is not None])
report=dict(at=time.time(),results=results,public_Qwen_hybrid_layers=cfg.layer_types,
    supervised_token_counts=[3,7],rowmean_vs_global_tokenmean_gradient_relative_L2=float((manual_grad-token_grad).norm()/manual_grad.norm()),
    all_matched_manual=True,cuda_initialized=torch.cuda.is_initialized(),
    scope='Synthetic tiny public Qwen hybrid model, FP32 CPU, DP1 GA2. Verifies loss/GA/AdamW algebra only.',
    not_verified=['4B GPU BF16','Liger','FA2/FLA','ZeRO3 DP4','4B Checkpoint restore','Agent behavior'],
    formal_model_optimizer_steps=0,original_data_Checkpoint_ledger_modified=False)
p=A/'results/PUBLIC_LF_TRL_GA_ADAMW_CPU_GOLDEN.json';assert not p.exists();p.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
