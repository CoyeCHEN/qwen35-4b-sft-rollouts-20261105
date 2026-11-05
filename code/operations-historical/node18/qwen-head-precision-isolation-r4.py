"""Isolate Liger's LM-head derivative and BF16 GEMM shapes; no optimizer or corpus changes."""
import os
os.environ['OMP_NUM_THREADS']='2'
import json
from pathlib import Path
import time
import torch
import torch.nn.functional as F
from datasets import load_from_disk
from transformers import AutoModelForImageTextToText
from liger_kernel.transformers import apply_liger_kernel_to_qwen3_5
from liger_kernel.transformers.fused_linear_cross_entropy import LigerFusedLinearCrossEntropyLoss

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')


def compare(a,b,atol,rtol):
    difference=0.;norm=0.;actual_norm=0.;dot=0.;bad=0;maximum=0.
    aa=a.reshape(-1);bb=b.reshape(-1)
    for begin in range(0,aa.numel(),1048576):
        x=aa[begin:begin+1048576].float();y=bb[begin:begin+1048576].float()
        difference+=float((x-y).square().sum());norm+=float(y.square().sum())
        actual_norm+=float(x.square().sum());dot+=float((x*y).sum())
        bad+=int((~torch.isclose(x,y,atol=atol,rtol=rtol)).sum())
        maximum=max(maximum,float((x-y).abs().max()))
    return dict(relative_l2=(difference/max(norm,1e-30))**.5,
        cosine=dot/max((norm*actual_norm)**.5,1e-30),norm_ratio=(actual_norm/max(norm,1e-30))**.5,
        element_failures=bad,maximum_absolute_error=maximum,atol=atol,rtol=rtol)


def check(hidden,weight,labels,dtype,reduced):
    torch.backends.cuda.matmul.allow_bf16_reduced_precision_reduction=reduced
    x=hidden.detach().to(dtype).reshape(-1,hidden.shape[-1]).requires_grad_()
    w=weight.detach().to(dtype).requires_grad_()
    y=F.pad(labels,(0,1),value=-100)[:,1:].reshape(-1)
    criterion=LigerFusedLinearCrossEntropyLoss(ignore_index=-100,reduction='mean',
        accum_dtype=torch.float32 if dtype==torch.float32 else None)
    native=criterion(w,x,y);nx,nw=torch.autograd.grad(native,(x,w))
    out=[]
    for shape in ['full','selected']:
        if shape=='full':logits=F.linear(x,w).float();target=y
        else:
            keep=y!=-100;logits=F.linear(x[keep],w).float();target=y[keep]
        manual=F.cross_entropy(logits,target,ignore_index=-100,reduction='mean')
        mx,mw=torch.autograd.grad(manual,(x,w))
        atol,rtol=(1e-5,5e-4)if dtype==torch.float32 else(.005,.05)
        row=dict(dtype=str(dtype),bf16_reduced_precision_reduction=reduced,manual_shape=shape,
            native_loss=float(native),manual_loss=float(manual),loss_error=abs(float(native-manual)),
            input_gradient=compare(nx,mx,atol,rtol),weight_gradient=compare(nw,mw,atol,rtol))
        out.append(row);print(json.dumps(row),flush=True)
        del logits,manual,mx,mw
    return out


def main():
    torch.set_num_threads(2);torch.manual_seed(42)
    apply_liger_kernel_to_qwen3_5()
    model=AutoModelForImageTextToText.from_pretrained(R/'assets/source17-r1/student-tokenizer',
        local_files_only=True,dtype=torch.bfloat16,attn_implementation='flash_attention_2').cuda().eval()
    row=load_from_disk(str(R/'frozen-data-772-r3/calibforge/cache-131072'))['train'][899]
    ids=torch.tensor([row['input_ids']],device='cuda');labels=torch.tensor([row['labels']],device='cuda')
    with torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16):
        hidden=model.model(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False).last_hidden_state
    torch.backends.cuda.matmul.allow_tf32=False
    results=[]
    for dtype,reduced in [(torch.bfloat16,True),(torch.bfloat16,False),(torch.float32,False)]:
        results+=check(hidden,model.lm_head.weight,labels,dtype,reduced)
    fp32=[r for r in results if r['dtype']=='torch.float32']
    result=dict(fp32_kernel_reference_passed=all(r['loss_error']<1e-5 and not r['input_gradient']['element_failures']and not r['weight_gradient']['element_failures']for r in fp32),
        results=results,optimizer_steps=0,training_settings_modified=False,
        scope='Real frozen CF row899 hidden states and fixed M0 head; original BF16 reduction, disabled reduction and FP32 kernel references; all outcomes retained')
    (R/'checks/QWEN_HEAD_PRECISION_ISOLATION_R4.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k!='results'}),flush=True)


if __name__=='__main__':main()
