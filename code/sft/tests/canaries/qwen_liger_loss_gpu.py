"""Bounded numerical check of the installed Qwen3.5 Liger loss path.

Uses synthetic hidden states and the real 248320-way output vocabulary; no model
checkpoint, optimizer update, benchmark, or paid request. Run on a free authorized
GPU under the existing project lock. Complements, rather than replaces, CPU DDP
Trainer checks and historical full-model GPU validation.
"""
import argparse
import fcntl
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--output',required=True)
parser.add_argument('--project-lock',required=True)
parser.add_argument('--gpu-uuid',required=True)
args=parser.parse_args()
assert os.environ.get('CUDA_VISIBLE_DEVICES')==args.gpu_uuid

with open(args.project_lock,'a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    observed=subprocess.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader'],
        capture_output=True,text=True,check=True,timeout=10).stdout
    assert not any(line.split(',')[0].strip()==args.gpu_uuid for line in observed.splitlines()),'GPU is occupied'
    import torch
    import torch.nn.functional as F
    from liger_kernel.transformers.model.loss_utils import LigerForCausalLMLoss

    torch.set_num_threads(1);torch.manual_seed(42);torch.cuda.manual_seed_all(42)
    vocabulary=248320;hidden_size=32;results=[]
    for dtype in (torch.float32,torch.bfloat16):
        for normalizer in (None,20):
            hidden=torch.randn(1,33,hidden_size,device='cuda',dtype=dtype)
            weight=torch.randn(vocabulary,hidden_size,device='cuda',dtype=dtype)*.05
            labels=torch.randint(vocabulary,(1,33),device='cuda');labels[:,:8]=-100;labels[:,15:19]=-100
            native_hidden=hidden.clone().requires_grad_();native_weight=weight.clone().requires_grad_()
            ref_hidden=hidden.clone().requires_grad_();ref_weight=weight.clone().requires_grad_()
            actual=LigerForCausalLMLoss(native_hidden,native_weight,labels,hidden_size,
                num_items_in_batch=normalizer)
            logits=F.linear(ref_hidden,ref_weight).float()
            expected=F.cross_entropy(logits[:,:-1].reshape(-1,vocabulary),labels[:,1:].reshape(-1),
                ignore_index=-100,reduction='mean' if normalizer is None else 'sum')
            if normalizer is not None:expected=expected/normalizer
            actual.backward();expected.backward();torch.cuda.synchronize()
            gradients=[]
            for name,a,b in [('hidden',native_hidden.grad,ref_hidden.grad),('head',native_weight.grad,ref_weight.grad)]:
                delta=a.float()-b.float();relative=float(delta.norm()/b.float().norm().clamp_min(1e-12))
                finite=bool(torch.isfinite(a).all() and torch.isfinite(b).all())
                gradients.append(dict(parameter=name,relative_l2_error=relative,
                    max_absolute_error=float(delta.abs().max()),finite=finite))
                assert finite and relative<(1e-4 if dtype==torch.float32 else .02)
            absolute=abs(float(actual)-float(expected))
            assert absolute<(1e-4 if dtype==torch.float32 else .02)
            assert bool((native_hidden.grad[0,:7]==0).all()) and bool((native_hidden.grad[0,-1]==0).all())
            results.append(dict(dtype=str(dtype),num_items_in_batch=normalizer,loss=float(actual),
                reference_loss=float(expected),absolute_loss_error=absolute,gradients=gradients,
                reference_shift_count=1,masked_context_and_last_position_gradient_zero=True,passed=True))
            del hidden,weight,native_hidden,native_weight,ref_hidden,ref_weight,logits,actual,expected
    source=Path(inspect.getfile(LigerForCausalLMLoss))
    proof=dict(passed=True,scope='Actual installed Qwen3.5 Liger fused head/causal loss GPU function; not a full Qwen model/ZeRO-3 training test',
        gpu_uuid=args.gpu_uuid,vocabulary=vocabulary,source_file=str(source),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),cases=results,
        peak_allocated_bytes=torch.cuda.max_memory_allocated(),peak_reserved_bytes=torch.cuda.max_memory_reserved(),
        model_updates=0,paid_requests=0)
    Path(args.output).write_text(json.dumps(proof,indent=2));print(json.dumps(proof))
