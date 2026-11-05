import sys,pathlib,json,importlib.metadata as meta,hashlib,inspect
import torch,flash_attn,causal_conv1d,fla,liger_kernel,deepspeed,llamafactory,transformers
R=pathlib.Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
expected=json.loads((R/'assets/source17-r1/four-arm/source/repository/sft/versions.json').read_text())
versions={n:meta.version(n) for n in expected['versions']}
assert all(versions[n].split('+')[0]==v for n,v in expected['versions'].items())
lf=pathlib.Path(llamafactory.__file__).parent
assert all(hashlib.sha256((lf/p).read_bytes()).hexdigest()==sha for p,sha in expected['LF_runtime_files_match_frozen_archive'].items())
assert torch.cuda.is_available() and torch.cuda.is_bf16_supported()
x=torch.randn(1024,1024,device='cuda',dtype=torch.bfloat16,requires_grad=True)
y=(x@x.T).float().square().mean();y.backward();torch.cuda.synchronize()
assert torch.isfinite(y) and torch.isfinite(x.grad).all()
out=dict(passed=True,python=sys.version,versions=versions,cuda=torch.version.cuda,nccl=torch.cuda.nccl.version(),bf16_supported=torch.cuda.is_bf16_supported(),device=torch.cuda.get_device_name(0),matrix_forward_backward_loss=float(y),max_memory_allocated=torch.cuda.max_memory_allocated(),max_memory_reserved=torch.cuda.max_memory_reserved(),native_qwen_model_optimizer_checkpoint_acceptance=False)
(R/'checks/runtime-import-gpu-matrix-r1.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out),flush=True)
