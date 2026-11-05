"""Deployment metadata for the existing native SFT advance/jobs entry on node 18."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
W = R / 'new-sft/workspace'
F = R / 'frozen-data-772-r3'
SHARED = Path('/data/chenkeyi/qwen35-sft-772-20261101')
SRC = R / 'new-sft/source-r4/repository'
sys.path.insert(0, str(SRC))
os.environ['OPENHARNESS_SFT_WORKSPACE'] = str(W)
from sft.runtime.checkpoint_archive import atomic_json, sha256
from sft.runtime.config import validate_native
from sft.runtime.launch import validate_data
from sft.runtime.paths import PUBLIC_SOURCES
from sft.runtime.readiness import verify_model


def same_or_create(path, value, *, yaml_file=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        previous = yaml.safe_load(path.read_text()) if yaml_file else json.loads(path.read_text())
        if previous != value:
            raise ValueError('Frozen deployment metadata differs: ' + str(path))
    elif yaml_file:
        with path.open('x') as stream:
            stream.write(yaml.safe_dump(value, sort_keys=False))
    else:
        atomic_json(path, value)


def main():
    release = F / 'DATA_RELEASE.json'
    released = json.loads(release.read_text())
    assert sha256(release) == 'fa4f07c05af4a8156547dbdda1cba60fb20e3c8626cd41cd40de4694e5f54821'
    assert released['complete'] and released['task_count'] == 772
    audit_path = SHARED / 'provenance/ACTUAL_772_TOOL_PROMPT_PROTOCOL_AUDIT.json'
    audit = json.loads(audit_path.read_text())
    assert sha256(audit_path) == '3ed2adb8c60efe6ebf18070e582db515622bb7f4629111380844122f03eeab33'
    assert audit['passed'] and audit['agent_targets'] == 30193 and not audit['errors']
    tool_contract = dict(kind='ACTUAL_772_FINAL_ELEVEN_TOOL_CONTRACT',
        audit_path=str(audit_path), audit_sha256=sha256(audit_path),
        tools=audit['tools'], finish_enabled=True, background_jobs_enabled=True,
        tool_result_budget_enabled=True, tool_result_budget_max_chars=200000,
        tool_result_budget_preview_chars=2000, agent_skill_tool_search_enabled=False,
        time_budget_seconds=0, actual_payload_counts=audit['counts'],
        provider_hash_serialization='json.dumps(sort_keys=True,ensure_ascii=False), UTF-8',
        historical_config_variants_preserved=True)
    contract = W / 'configs/actual-eleven-tool-contract.json'
    same_or_create(contract, tool_contract)
    template = yaml.safe_load((W / 'configs/capacity-template-r4.yaml').read_text())
    output_m1 = R / 'runs/new-m1-cf416-128k-e5'
    stages = {}
    for stage, (dataset, revision, tasks) in PUBLIC_SOURCES.items():
        pool = 'calibforge' if stage == 'new-cf416-m1' else 'tmax'
        parent = F / pool / 'DATA_MANIFEST.json'
        parent_data = json.loads(parent.read_text())
        assert sha256(parent) == released['pools'][pool]['manifest_sha256']
        cache = F / pool / 'cache-131072'
        counts = {split:dict(rows=v['segments'], supervised_tokens=v['supervised_tokens'],
            independent_tasks=v['retained_independent_tasks'], targets=v['retained_targets'])
            for split,v in parent_data['length_views']['131072'].items() if split in ('train','validation')}
        artifacts = [dict(path=str(p.relative_to(cache)),bytes=p.stat().st_size,sha256=sha256(p))
                     for p in sorted(cache.rglob('*')) if p.is_file()]
        for item in artifacts:
            assert item['sha256'] == parent_data['artifacts']['cache-131072/' + item['path']]
        manifest = dict(kind='QWEN35_772_NATIVE_STAGE',stage=stage,source_dataset=dataset,
            source_revision=revision,source_primary_task_count=tasks,
            supervision_scope='all_assistant_once', original_provider_prefixes_verified=True,
            finish_enabled=True,tool_result_budget_enabled=True,
            model_revision=template['model_revision'],cutoff=131072,
            tool_contract_sha256=sha256(contract),release_manifest=str(release),
            release_manifest_sha256=sha256(release),parent_pool_manifest=str(parent),
            parent_pool_manifest_sha256=sha256(parent),
            no_truncation=True, task_groups_disjoint=True, formal_training_eligible=True,
            length_exclusion='3886 overlong original targets explicitly quarantined corpus-wide; no token truncation',
            artifacts=artifacts,counts=counts)
        validate_data(cache, manifest)
        same_or_create(W / 'manifests' / (stage + '.json'), manifest)
        cfg = dict(template)
        cfg.update(model_name_or_path=str(R/'assets/source17-r1/student-tokenizer') if pool=='calibforge' else str(output_m1),
            output_dir=str(output_m1 if pool=='calibforge' else R/'runs/new-m2-tmax356-128k-e5'),
            tokenized_path=str(cache),dataset=stage,eval_dataset=stage+'-validation',
            cutoff_len=131072,gradient_accumulation_steps=8,max_steps=-1,
            do_eval=True,eval_on_start=True,save_strategy='epoch',eval_strategy='epoch',
            save_total_limit=None,load_best_model_at_end=False,remove_unused_columns=True)
        cfg.pop('eval_steps', None)
        cfg.pop('save_steps', None)
        validate_native(cfg)
        config_path = W / 'configs' / (stage + '.yaml')
        same_or_create(config_path, cfg, yaml_file=True)
        stages[stage] = dict(config=str(config_path),config_sha256=sha256(config_path),
            data_manifest_sha256=sha256(W/'manifests'/(stage+'.json')),
            rows=counts,dp=4,ga=8,batch=32,epochs=5,
            expected_optimizer_steps=5*((counts['train']['rows']+31)//32))
        unit = 'qwen35-772-new-sft-new772-' + stage + '.service'
        dropin = Path.home()/'.config/systemd/user'/(unit+'.d')/'ssd-runtime.conf'
        dropin.parent.mkdir(parents=True,exist_ok=True)
        text='[Service]\n'+'\n'.join('Environment='+k+'='+v for k,v in {
            'PATH':str(R/'env/train-r1/bin')+':/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            'PYTORCH_CUDA_ALLOC_CONF':'expandable_segments:True','TMPDIR':str(R/'tmp'),
            'TRITON_CACHE_DIR':str(R/'cache/triton'),'TORCH_EXTENSIONS_DIR':str(R/'cache/torch-extensions'),
            'XDG_CACHE_HOME':str(R/'cache/xdg'),'HF_HOME':str(R/'cache/hf')}.items())+'\n'
        if dropin.exists() and dropin.read_text()!=text:raise ValueError('Native job drop-in changed')
        dropin.write_text(text)
    runtime_path = W/'configs/runtime.json'
    runtime=json.loads(runtime_path.read_text())
    if any((W/'jobs').glob('new772-*/job.json')):
        raise ValueError('Formal job already exists; preserve its frozen deployment')
    runtime.update(max_concurrent_gpus=4,planned_gpu_ids=['0','1','2','3'],
        capacity_acceptance=str(R/'runs/verify-capacity772-131072-dp4/CAPACITY_ACCEPTANCE.json'),
        tool_contract=str(contract),cf_retention_cache=str(F/'calibforge/cache-131072'),
        formal_training_authorized=False,formal_authorized_stage=None)
    atomic_json(runtime_path,runtime)
    verify_model()
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    result=dict(prepared=True,formal_training_started=False,stages=stages,
        final_release_sha256=sha256(release),training_config_frozen=True,
        note='Native advance still requires actual four-rank update/save/resume admission.')
    atomic_json(W/'checks/FORMAL_STAGE_DEPLOYMENT.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
