"""Version prepared SFT configs against the verified canonical student resource."""
import os
os.environ.update(CUDA_VISIBLE_DEVICES='',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
import datetime
import hashlib
import json
from pathlib import Path
import yaml
from transformers import HfArgumentParser
from llamafactory.hparams import ModelArguments,DataArguments,TrainingArguments,FinetuningArguments
import torch

S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
D=S/'student-protocol-r256'
RESOURCE=S/'student-tokenizer-r155'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    D.mkdir(exist_ok=False)
    input_file=S/'student-protocol-r255/training-recipe-r1-input.json'
    recipe=json.loads(input_file.read_text())
    tokenizer_proof=S/'student-protocol-r255/TOKENIZER_CHECKPOINT_SERVING_ACCEPTANCE.json'
    accepted=json.loads(tokenizer_proof.read_text());assert accepted['passed']
    assert accepted['serving']['explicit_tokenizer_path_supported'] and not accepted['model_or_optimizer_loaded']
    assert accepted['m1_initial_tokenizer']['backend_semantics_sha256']==accepted['m2_checkpoint_reload_tokenizer']['backend_semantics_sha256']==accepted['serving']['backend_semantics_sha256']
    configs=[];old={};pending_caches=[]
    allowed={'model_name_or_path','dataset','eval_dataset','tokenized_path','output_dir'}
    parser=HfArgumentParser((ModelArguments,DataArguments,TrainingArguments,FinetuningArguments))
    overrides=dict(use_cpu=True,do_train=False,do_eval=False,bf16=False,deepspeed=None)
    for row in recipe['configs']:
        source=Path(row['path']);assert sha(source)==row['sha256'];old[str(source)]=sha(source)
        previous=yaml.safe_load(source.read_text());new=dict(previous);cap=row['context'];stage=row['stage']
        new['model_name_or_path']=str(RESOURCE if stage=='M1' else S/'student-training-r2'/('m1-'+str(cap)))
        new['output_dir']=str(S/'student-training-r2'/(stage.lower()+'-'+str(cap)))
        for key in ['dataset','eval_dataset','tokenized_path']:
            assert '-r1' in previous[key];new[key]=previous[key].replace('-r1','-r2')
        changed={k for k in new if new[k]!=previous[k]};assert changed==allowed
        assert new['learning_rate']==1e-5 and new['num_train_epochs']==5 and new['gradient_accumulation_steps']==8
        assert new['bf16'] and not new['pure_bf16'] and new['enable_thinking'] and new['preserve_thinking']
        assert not new['train_on_prompt'] and not new['mask_history'] and not new['packing']
        candidate=source.with_name(source.name.replace('-r1.yaml','-r2.yaml'));assert not candidate.exists()
        candidate.write_text(yaml.safe_dump(new,sort_keys=False,allow_unicode=True))
        parsed=parser.parse_dict(dict(new,**overrides))
        model_args,data_args,training_args,finetuning_args=parsed
        assert model_args.model_name_or_path==new['model_name_or_path'] and data_args.cutoff_len==cap
        assert data_args.enable_thinking and data_args.preserve_thinking and not data_args.train_on_prompt and not data_args.mask_history
        assert training_args.learning_rate==1e-5 and training_args.num_train_epochs==5
        assert training_args.per_device_train_batch_size*training_args.gradient_accumulation_steps*4==32
        assert finetuning_args.finetuning_type=='full'
        pending_caches.append(new['tokenized_path'])
        configs.append(dict(stage=stage,context=cap,path=str(candidate),sha256=sha(candidate),
            initialization=new['model_name_or_path'],output_dir=new['output_dir'],tokenized_path=new['tokenized_path'],
            independent_task_pool='calibforge' if stage=='M1' else 'tmax',source_config=str(source),source_config_sha256=row['sha256'],
            changed_fields=sorted(changed),native_argument_classes_cpu_parse_passed=True,parser_only_overrides=overrides))
    assert all(sha(Path(p))==digest for p,digest in old.items())
    assert not torch.cuda.is_initialized()
    lock=dict(status='TOKENIZER_TEMPLATE_PROCESSOR_POLICY_LOCKED_DATA_AND_GPU_PENDING',
        checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),configs=configs,
        source_recipe_sha256=sha(input_file),canonical_tokenizer_resource=str(RESOURCE),
        canonical_source_manifest_sha256=sha(RESOURCE/'SOURCE_MANIFEST_R155.json'),
        canonical_backend_semantics_sha256=accepted['serving']['backend_semantics_sha256'],
        official_template_sha256=accepted['serving']['template_sha256'],
        checkpoint_tokenizer_roundtrip=dict(path=str(tokenizer_proof),sha256=sha(tokenizer_proof)),
        history_thinking_policy='Pinned official Qwen3.5 last-real-user template policy; enable_thinking=true and preserve_thinking=true; only actual visible source history',
        reasoning_projection='DeepSeek reasoning_content to Qwen reasoning field; no provider-private boundary reuse',
        serving_template_kwargs=dict(enable_thinking=True),
        serving_required_arguments=dict(tokenizer_path=str(RESOURCE),reasoning_parser='qwen3',tool_call_parser='qwen3_coder'),
        serving_parser_policy=dict(force_reasoning=True,separate_reasoning=True),
        serving_model_path='The selected M1/M2 checkpoint from its candidate output_dir; tokenizer_path remains the pinned canonical resource',
        serving_native_schema_source_sha256=accepted['serving']['native_server_args_source_sha256'],
        model_resource_selection_changes_original_weight_bytes=False,
        original_configs_unchanged=old,supervision='Full Thinking+Action; each original Assistant target once; System/User/Observation/padding masked',
        global_batch=32,epochs=5,learning_rate=1e-5,planned_dp=4,candidate_gradient_accumulation=8,
        actual_dp_acceptance_required='Measure actual D; require32%D==0 and GA=32/D; world size is not assumed to equal D',
        precision='BF16 mixed; FP32 master/Adam acceptance still required on actual GPU/ZeRO optimizer',
        context_policy='256K actual acceptance first;128K only with retained256K failure evidence',
        pending_final_cache_paths=pending_caches,
        admission_requirements=['Full bounded1000 Task collection terminal and complete failure classifications','Independent complete CF/TMax corpus manifests and native full-cache audits bound by SHA','Actual Qwen GPU precision/context and actual DP group acceptance','For M2: completed matching M1 checkpoint identity and canonical tokenizer/processor reload'],
        actual_qwen_gpu_acceptance_passed=False,final_corpus_frozen=False,training_started=False,model_or_optimizer_loaded=False,cuda_initialized=False,
        source_sha256=sha(Path(__file__)))
    p=D/'STUDENT_DATA_AND_SERVING_POLICY_LOCK_R256.json';p.write_text(json.dumps(lock,indent=2))
    print(json.dumps(dict(proof=str(p),sha256=sha(p),configs=len(configs),native_cpu_parser_passed=True,old_configs_unchanged=True,training_started=False)))


if __name__=='__main__':main()
