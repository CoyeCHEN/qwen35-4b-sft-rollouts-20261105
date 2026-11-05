"""CPU-only native LF deployment check; model weights and real data stay external."""
import argparse
import copy
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace',required=True);parser.add_argument('--model',required=True)
    parser.add_argument('--m1-manifest',required=True)
    args=parser.parse_args()
    os.environ.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',TOKENIZERS_PARALLELISM='false',OPENHARNESS_SFT_WORKSPACE=args.workspace)
    import torch,yaml
    from accelerate import init_empty_weights
    from transformers import AutoConfig,AutoModelForImageTextToText
    from llamafactory.hparams import get_train_args,ModelArguments
    from llamafactory.model import load_tokenizer
    from llamafactory.data import get_dataset,get_template_and_fix_tokenizer,SFTDataCollatorWith4DAttentionMask
    import sft
    from sft.runtime.config import initialize
    from sft.runtime.checkpoint_archive import atomic_json,sha256
    from sft.prepare import adopt_m1,read_approval
    from sft import qwen35
    torch.set_num_threads(1)
    root=Path(args.workspace).resolve()
    initialize(root,args.model,root/'hot',root/'archive',['GPU-NOT-AUTHORIZED-FIXTURE-'+str(i)for i in range(4)])
    # This workspace is CPU-only and never authorized for GPU/formal training.
    adopted=adopt_m1(args.m1_manifest)
    versions=json.loads((Path(sft.__file__).parent/'versions.json').read_text())
    import llamafactory
    lf=Path(llamafactory.__file__).parent
    assert all(sha256(lf/name)==digest for name,digest in versions['LF_runtime_files_match_frozen_archive'].items())
    qwen35.MODEL=args.model;tokenizer=qwen35.load_tokenizer()
    fixture,meta=qwen35.encode(tokenizer,[dict(role='user',content='Synthetic deployment fixture.'),
        dict(role='assistant',reasoning_content='Check the fixture.',content='Done.')],cutoff=1024)
    assert meta['loss_tokens']>0 and meta['loss_tokens']<meta['text_tokens']
    parsed=[]
    for stage in ('m1-64k','m2-128k','m2-96k'):
        cfg=yaml.safe_load((root/'configs'/f'{stage}.yaml').read_text())
        get_train_args(cfg|dict(use_cpu=True,deepspeed=None));parsed.append(stage)
    cfg=yaml.safe_load((root/'configs/m1-64k.yaml').read_text())
    ma,da,ta,_,_=get_train_args(cfg|dict(use_cpu=True,deepspeed=None))
    module=load_tokenizer(ModelArguments(model_name_or_path=args.model))
    template=get_template_and_fix_tokenizer(module['tokenizer'],da)
    data=get_dataset(template,ma,da,ta,stage='sft',**module)
    assert(len(data['train_dataset']),len(data['eval_dataset']))==(5320,191)
    with init_empty_weights():model=AutoModelForImageTextToText.from_config(AutoConfig.from_pretrained(args.model,local_files_only=True))
    collator=SFTDataCollatorWith4DAttentionMask(template=template,model=model,tokenizer=module['tokenizer'],processor=module['processor'],
        pad_to_multiple_of=8,label_pad_token_id=-100,block_diag_attn=False,neat_packing=False,attn_implementation='sdpa',compute_dtype=torch.bfloat16)
    checked=[]
    for index in (0,5319):
        row=data['train_dataset'][index];batch=collator([copy.deepcopy(row)]);n=len(row['input_ids'])
        assert torch.equal(batch['input_ids'][0,:n],torch.tensor(row['input_ids']))
        assert torch.equal(batch['labels'][0,:n],torch.tensor(row['labels']))
        assert bool((batch['labels'][0,n:]==-100).all())
        checked.append(dict(row=index,text_tokens=n,collated_tokens=batch['input_ids'].shape[-1],loss_tokens=int((batch['labels']!=-100).sum())))
    # Prepare only: a finite two-update GA4 profile using 32 real approved M1
    # rows (4 ranks * micro1 * accumulation4 * 2). Never submit a GPU job here.
    from datasets import DatasetDict
    canary_data=root/'checks/gpu-continuous-ga4-data'
    DatasetDict(train=data['train_dataset'].select(range(32)),validation=data['eval_dataset'].select(range(4))).save_to_disk(str(canary_data),num_proc=1)
    canary=cfg|dict(tokenized_path=str(canary_data),output_dir=str(root/'hot/runs/verify-continuous-ga4'),save_steps=1,do_eval=False,eval_strategy='no',max_steps=3)
    canary_config=root/'configs/verify-continuous-ga4.yaml'
    canary_config.write_text(yaml.safe_dump(canary,sort_keys=False))
    get_train_args(canary|dict(use_cpu=True,deepspeed=None))
    atomic_json(root/'checks/gpu-continuous-ga4-plan.json',dict(purpose='bounded_nonformal_native_driver_validation',
        config=str(canary_config),config_sha256=sha256(canary_config),source_M1_manifest_sha256=sha256(args.m1_manifest),
        train_rows=32,validation_rows=4,world_size=4,gradient_accumulation_steps=4,expected_optimizer_steps=3,
        canary_only_overrides=dict(max_steps=3,reason='Stop after checkpoint-2, then resume step3 with unchanged warmup/scheduler'),
        native_driver='sft.runtime.lf_train',executed=False,queue_registered=False,
        blocker='Requires authorized four-GPU idle state, existing queue handoff and validated CUDA environment; CPU env must not execute it'))
    try:read_approval(root/'manifests/m2-approved-sources.json')
    except ValueError:pass
    else:raise AssertionError('Empty formal M2 accepted')
    assert not torch.cuda.is_initialized()
    assert not any('runtime-evidence'in p for p in __import__('sys').path)
    result=dict(status='CONFIRMED_CPU_NATIVE_DEPLOYMENT',checkout_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        package=str(sft.__file__),dependency_versions={name:metadata.version(name)for name in ('torch','transformers','datasets','accelerate','llamafactory','deepspeed')},
        critical_LF_source_SHA_verified=True,parsed_configs=parsed,m1_rows={'train':5320,'validation':191},collator=checked,
        synthetic_fixture_supervision=meta['loss_tokens'],CUDA_initialized=False,formal_training_authorized=False,
        scope='Fresh CPU environment and independent checkout; not a CUDA-kernel build or GPU training proof')
    atomic_json(root/'checks/portable-deployment.json',result);print(json.dumps(result,indent=2))


if __name__=='__main__':main()
