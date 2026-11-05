"""Finalize a completed native stage, using the existing seal and real cold GPU loads."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
W=R/'new-sft/workspace'
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
sys.path.insert(0,str(R))
PINNED_ASSETS=__import__('importlib').import_module('snapshot-epoch-hf18-r1').ASSETS
SRC=R/'new-sft/source-r4/repository'
sys.path.insert(0,str(SRC))
os.environ['OPENHARNESS_SFT_WORKSPACE']=str(W)
from sft.runtime.checkpoint_archive import atomic_json,sha256
from sft.runtime.hf_export import seal,final_verified
from sft.runtime.launch import exported_m1

ASSETS=('tokenizer.json','tokenizer_config.json','chat_template.jinja','vocab.json','merges.txt',
        'preprocessor_config.json','video_preprocessor_config.json','processor_config.json',
        'special_tokens_map.json','added_tokens.json')


def canonical_assets(model):
    canonical=R/'assets/source17-r1/student-tokenizer'
    manifest=model/'CANONICAL_PROCESSOR_ASSETS.json'
    if manifest.exists():
        value=json.loads(manifest.read_text())
        assert all(sha256(model/x['name'])==x['sha256']==PINNED_ASSETS[x['name']] for x in value['files'])
        return
    assert not (model/'HF_EXPORT_COMPLETE.json').exists(),'Do not rewrite a sealed HF export'
    exported_m1(model)
    backup=R/'hf-packaging-originals'/model.name
    backup.mkdir(parents=True,exist_ok=True)
    files=[];changes=[]
    for name in ASSETS:
        source=canonical/name;dest=model/name
        if not source.exists():
            if dest.exists():
                old=sha256(dest)
                saved=backup/(name+'.'+old)
                if not saved.exists():shutil.copyfile(dest,saved)
                assert sha256(saved)==old
                dest.unlink()
                changes.append(dict(name=name,old_sha256=old,canonical_absent=True,backup=str(saved)))
            continue
        expected=sha256(source)
        assert expected==PINNED_ASSETS[name], 'Frozen canonical asset changed: '+name
        if not dest.exists() or dest.is_symlink() or sha256(dest)!=expected:
            old=sha256(dest) if dest.exists() else None
            if old:
                saved=backup/(name+'.'+old)
                if not saved.exists():shutil.copyfile(dest,saved)
                assert sha256(saved)==old
            temporary=model/(name+'.canonical.tmp')
            shutil.copyfile(source,temporary)
            assert sha256(temporary)==expected
            temporary.replace(dest)
            changes.append(dict(name=name,old_sha256=old,canonical_sha256=expected))
        files.append(dict(name=name,sha256=expected,source=str(source.resolve())))
    atomic_json(manifest,dict(files=files,changes=changes,at=time.time(),
        scope='Completed derived HF packaging only; model weights/config, native checkpoints and frozen caches are untouched.'))


def hf_gpu_load(model):
    import torch
    from transformers import AutoTokenizer,AutoModelForImageTextToText
    torch.set_num_threads(2)
    tokenizer=AutoTokenizer.from_pretrained(model,local_files_only=True)
    loaded=AutoModelForImageTextToText.from_pretrained(model,local_files_only=True,
        dtype=torch.bfloat16,attn_implementation='flash_attention_2').cuda().eval()
    batch=tokenizer.apply_chat_template([dict(role='user',content='Compute 1+1.')],
        add_generation_prompt=True,enable_thinking=True,return_tensors='pt',return_dict=True)
    batch={k:v.cuda() for k,v in batch.items()}
    with torch.inference_mode():output=loaded.generate(**batch,max_new_tokens=16,do_sample=False)
    generated=output.shape[-1]-batch['input_ids'].shape[-1]
    assert generated>0 and torch.isfinite(loaded.lm_head.weight).all()
    atomic_json(model/'HF_LOAD_SMOKE.json',dict(model_loaded=True,generated_tokens=generated,
        cuda_initialized=True,gpu_uuid=str(torch.cuda.get_device_properties(0).uuid),
        max_memory_allocated=torch.cuda.max_memory_allocated(),
        export_manifest_sha256=sha256(model/'HF_EXPORT_COMPLETE.json'),
        scope='Independent cold Transformers full HF/Tokenizer GPU load and actual generation; no optimizer.'))


def admit(model):
    import yaml
    from sft.runtime import jobs
    from sft.runtime.paths import PUBLIC_STAGES,config_path
    stage=next(s for s in PUBLIC_STAGES if Path(yaml.safe_load(config_path(s).read_text())['output_dir']).resolve()==model)
    assert jobs.status('new772-'+stage)['status']=='completed','Native training must finish before HF packaging'
    exported_m1(model)
    with (C/'training.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        canonical_assets(model)
        seal(model)
        if not final_verified(model):
            row=subprocess.check_output(['nvidia-smi','-i','0','--query-gpu=uuid,memory.used',
                '--format=csv,noheader,nounits'],text=True).strip().split(',')
            assert row[0].strip()=='GPU-7b40e1e7-c43c-ba4f-10ed-397f948eeed1' and int(row[1])<100
            env=os.environ|dict(CUDA_VISIBLE_DEVICES=row[0].strip(),HF_HUB_OFFLINE='1')
            subprocess.run([sys.executable,__file__,'--hf-load',str(model)],env=env,check=True,timeout=600)
        assert final_verified(model)
        if not (model/'TOOL_PROTOCOL_SMOKE.json').exists():
            subprocess.run([sys.executable,str(R/'cold-hf-native-cli-smoke-r4.py'),str(model)],check=True,timeout=1200)
        proof=json.loads((model/'TOOL_PROTOCOL_SMOKE.json').read_text())
        assert proof['passed'] and proof['export_manifest_sha256']==sha256(model/'HF_EXPORT_COMPLETE.json')
        release=json.loads((R/'checks/NEW11_STUDENT_HARNESS_RELEASE_R5.json').read_text())
        assert proof['wheel_sha256']==release['wheel_sha256']
        atomic_json(model/'FINAL_HF_ADMISSION.json',dict(passed=True,stage=stage,
            export_manifest_sha256=sha256(model/'HF_EXPORT_COMPLETE.json'),
            hf_load_smoke_sha256=sha256(model/'HF_LOAD_SMOKE.json'),
            native_cli_smoke_sha256=sha256(model/'TOOL_PROTOCOL_SMOKE.json'),
            student_harness_wheel_sha256=proof['wheel_sha256'],
            canonical_processor_assets_sha256=sha256(model/'CANONICAL_PROCESSOR_ASSETS.json'),
            tokenizer_template_processor_files={n:sha256(model/n)for n in PINNED_ASSETS},
            source_sha256=sha256(Path(__file__)),at=time.time()))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--hf-load',action='store_true');parser.add_argument('model')
    args=parser.parse_args();model=Path(args.model).resolve()
    hf_gpu_load(model) if args.hf_load else admit(model)
