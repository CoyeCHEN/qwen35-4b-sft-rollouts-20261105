"""Prove the first real HF export preserves frozen vision tensors and changes language weights."""
import hashlib
import json
from pathlib import Path
from safetensors import safe_open
import torch

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')


def signatures(root,selected=None):
    index=root/'model.safetensors.index.json'
    files=set(json.loads(index.read_text())['weight_map'].values())if index.exists()else{'model.safetensors'}
    result={}
    for name in sorted(files):
        with safe_open(root/name,framework='pt',device='cpu')as f:
            keys=[k for k in f.keys()if '.visual.'in k]
            if selected is None:
                language=sorted(k for k in f.keys()if '.language_model.'in k and k.endswith('input_layernorm.weight'))
                keys+=language[:2]
            else:keys+=[k for k in selected if k in f.keys()and '.visual.'not in k]
            for key in keys:
                tensor=f.get_tensor(key)
                result[key]=dict(shape=list(tensor.shape),dtype=str(tensor.dtype),
                    sha256=hashlib.sha256(tensor.contiguous().view(torch.uint8).numpy().tobytes()).hexdigest())
    return result


def main():
    base=signatures(R/'assets/source17-r1/student-tokenizer')
    actual=signatures(R/'epoch-models/new-m1-epoch1',base)
    assert set(base)==set(actual)
    vision=[k for k in base if '.visual.'in k];language=[k for k in base if '.visual.'not in k]
    assert len(vision)==297 and all(base[k]==actual[k]for k in vision)
    assert language and all(base[k]['sha256']!=actual[k]['sha256']for k in language)
    result=dict(passed=True,actual_epoch=1,optimizer_steps=40,bitwise_identical_vision_tensors=len(vision),
        language_weight_updates={k:dict(before=base[k],after=actual[k])for k in language},
        vision_tensors={k:actual[k]for k in vision},training_or_checkpoint_modified=False,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (R/'checks/NEW_M1_EPOCH1_FROZEN_VISION_AUDIT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k not in ['vision_tensors','language_weight_updates']}))


if __name__=='__main__':main()
