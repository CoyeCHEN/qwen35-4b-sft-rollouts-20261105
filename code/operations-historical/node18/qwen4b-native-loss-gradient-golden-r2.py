"""Full Qwen forward and all-language gradient reference on unchanged final-cache rows; no optimizer."""
import os
os.environ['OMP_NUM_THREADS']='2'
os.environ['TOKENIZERS_PARALLELISM']='false'
import copy
import hashlib
import json
from pathlib import Path
import time

import torch
import torch.nn.functional as F
from datasets import load_from_disk
from liger_kernel.transformers import apply_liger_kernel_to_qwen3_5
from transformers import AutoModelForImageTextToText
from llamafactory.data import SFTDataCollatorWith4DAttentionMask,get_template_and_fix_tokenizer
from llamafactory.hparams import ModelArguments,DataArguments
from llamafactory.model import load_tokenizer

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
D=R/'frozen-data-772-r3'


def ids_sha(ids):return hashlib.sha256(json.dumps(ids,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def main():
    torch.set_num_threads(2);torch.manual_seed(42)
    model_path=R/'assets/source17-r1/student-tokenizer'
    apply_liger_kernel_to_qwen3_5()
    model=AutoModelForImageTextToText.from_pretrained(model_path,local_files_only=True,
        dtype=torch.bfloat16,attn_implementation='flash_attention_2').cuda().train()
    for name,p in model.named_parameters():p.requires_grad_('visual'not in name)
    assert sum(p.numel()for p in model.parameters()if p.requires_grad)==4205751296
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    module=load_tokenizer(ModelArguments(model_name_or_path=str(model_path)))
    tokenizer=module['tokenizer']
    template=get_template_and_fix_tokenizer(tokenizer,DataArguments(template='qwen3_5',enable_thinking=True,preserve_thinking=True))
    collator=SFTDataCollatorWith4DAttentionMask(template=template,tokenizer=tokenizer,
        processor=module['processor'],model=model,pad_to_multiple_of=8,label_pad_token_id=-100,
        block_diag_attn=False,neat_packing=False,attn_implementation='flash_attention_2',compute_dtype=torch.bfloat16)
    results=[]
    for pool in ['calibforge','tmax']:
        start=time.monotonic()
        mappings=[json.loads(line)for line in(D/pool/'SAMPLE_MAPPING-131072.jsonl').open()]
        selected=min((x for x in mappings if x['split']=='train'and x['supervised_tokens']>=16),key=lambda x:(x['input_tokens'],x['row_index']))
        row=load_from_disk(str(D/pool/'cache-131072'))['train'][selected['row_index']]
        assert ids_sha(row['input_ids'])==selected['input_sha256']
        assert ids_sha(row['labels'])==selected['labels_sha256']
        batch=collator([copy.deepcopy(row)])
        batch={k:v.cuda()if isinstance(v,torch.Tensor)else v for k,v in batch.items()}
        keep=batch['attention_mask'][0].bool()
        assert batch['input_ids'][0][keep].tolist()==row['input_ids']
        assert batch['labels'][0][keep].tolist()==row['labels']
        assert int((batch['labels']!=-100).sum())==selected['supervised_tokens']
        torch.cuda.reset_peak_memory_stats()
        with torch.autocast('cuda',dtype=torch.bfloat16):
            out=model(**batch,use_cache=False,skip_logits=True,output_hidden_states=True)
        native_hidden=out.hidden_states[-1].detach().clone()
        native_loss=float(out.loss.detach());out.loss.backward()
        reference={name:p.grad.detach().cpu().clone()for name,p in model.named_parameters()if p.grad is not None}
        model.zero_grad(set_to_none=True);del out
        without_labels={k:v for k,v in batch.items()if k!='labels'}
        with torch.autocast('cuda',dtype=torch.bfloat16):
            hidden=model.model(**without_labels,use_cache=False).last_hidden_state
        shifted_labels=batch['labels'][:,1:]
        target_mask=shifted_labels!=-100
        # Independent FP32 linear head and exactly one causal shift, only real labels.
        logits=F.linear(hidden[:,:-1,:][target_mask],model.lm_head.weight).float()
        manual=F.cross_entropy(logits,shifted_labels[target_mask],reduction='mean')
        manual_loss=float(manual.detach());manual.backward()
        diff2=0.;norm2=0.;maximum_relative=0.;checked=0
        for name,p in model.named_parameters():
            if p.grad is None:
                assert name not in reference
                continue
            expected=reference.pop(name).reshape(-1)
            actual=p.grad.detach().cpu().reshape(-1)
            local_diff=0.;local_norm=0.
            for begin in range(0,actual.numel(),1048576):
                a=actual[begin:begin+1048576].float();b=expected[begin:begin+1048576].float()
                local_diff+=float((a-b).square().sum());local_norm+=float(b.square().sum())
            relative=(local_diff/max(local_norm,1e-30))**.5
            maximum_relative=max(maximum_relative,relative);diff2+=local_diff;norm2+=local_norm;checked+=1
        assert not reference
        global_relative=(diff2/max(norm2,1e-30))**.5
        # Separately prove that LF's masked multimodal placeholder changes no visible history.
        with torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16):
            pure=model.model(input_ids=torch.tensor([row['input_ids']],device='cuda'),
                attention_mask=torch.ones((1,len(row['input_ids'])),dtype=torch.long,device='cuda'),
                use_cache=False).last_hidden_state[0]
        actual_hidden=hidden.detach()[0][keep]
        hidden_relative=float((actual_hidden.float()-pure.float()).norm()/pure.float().norm())
        value=dict(pool=pool,task_id=selected['task_id'],trial_id=selected['trial_id'],row_index=selected['row_index'],
            sample_sha256=selected['sample_sha256'],native_input_tokens=int(batch['input_ids'].shape[-1]),
            visible_tokens=len(row['input_ids']),supervised_tokens=selected['supervised_tokens'],
            native_liger_loss=native_loss,manual_shift_once_bf16_head_fp32_ce_loss=manual_loss,
            native_vs_reference_hidden_relative_l2_error=float((native_hidden.float()-hidden.detach().float()).norm()/native_hidden.float().norm()),
            loss_absolute_error=abs(native_loss-manual_loss),all_gradient_tensors_compared=checked,
            all_gradient_global_relative_l2_error=global_relative,maximum_parameter_gradient_relative_l2_error=maximum_relative,
            masked_placeholder_vs_deployment_hidden_relative_l2_error=hidden_relative,
            max_memory_allocated=torch.cuda.max_memory_allocated(),max_memory_reserved=torch.cuda.max_memory_reserved(),
            elapsed_seconds=time.monotonic()-start)
        print(json.dumps(value),flush=True)
        assert value['loss_absolute_error']<.00002 and global_relative<.005 and hidden_relative<.02,value
        results.append(value)
        model.zero_grad(set_to_none=True);del hidden,logits,manual,pure,actual_hidden,batch,native_hidden
    proof=dict(passed=True,results=results,optimizer_steps=0,weights_saved=False,
        model_revision='851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a',
        scope='Full fixed Qwen4B + official LF collator/FlashAttention/FLA/Liger/gradient checkpointing; all language gradients vs precision-matched BF16 head + independent FP32 CE on two complete unchanged final rows. Native DP4 optimizer/save/resume has separate acceptance.')
    (R/'checks/QWEN4B_GPU_LOSS_GRADIENT_GOLDEN_R2.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(dict(passed=True,pools=2)),flush=True)


if __name__=='__main__':main()
