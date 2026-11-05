"""Write versioned CPU-parsed candidates only; never start training or touch GPUs."""
import hashlib,json,os
from pathlib import Path
import yaml
from llamafactory.hparams import get_train_args
R=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
W=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/workspace')
base=yaml.safe_load((W/'configs/new-cf500-m1-128k.yaml').read_text())
old_files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (W/'configs').glob('*') if p.is_file()}
result=[]
for cap in [262144,131072]:
 names=[f'new-cf500-m1-b32-e5-{cap//1024}k-r1',f'new-cf500-tmax500-m2-b32-e5-{cap//1024}k-r1']
 output_root=Path('/ssd/chenkeyi/qwen35-calibforge-ab-20261027/hot/runs')
 for index,name in enumerate(names):
  config=base|dict(learning_rate=1e-5,num_train_epochs=5,gradient_accumulation_steps=8,
   per_device_train_batch_size=1,bf16=True,pure_bf16=False,fp16=False,optim='adamw_torch',
   lr_scheduler_type='cosine',warmup_ratio=.05,weight_decay=0.0,cutoff_len=cap,
   mask_history=False,train_on_prompt=False,enable_thinking=True,preserve_thinking=True,
   packing=False,neat_packing=False,output_dir=str(output_root/name),
   model_name_or_path='/data/models/Qwen/Qwen3.5-4B' if index==0 else str(output_root/names[0]),
   dataset=name+'-train',eval_dataset=name+'-validation',tokenized_path=str(W/'data'/name))
  config.pop('runtime_recipe',None)
  file=W/'configs'/(name+'.yaml')
  if file.exists():raise FileExistsError('Never overwrite training config')
  parsed=config|dict(use_cpu=True,deepspeed=None)
  get_train_args(parsed)
  file.write_text(yaml.safe_dump(config,sort_keys=False))
  result.append(dict(stage='M1' if index==0 else 'M2',context=cap,path=str(file),sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
   cpu_native_parser_passed=True,initialization=config['model_name_or_path'],output_dir=config['output_dir']))
for name,digest in old_files.items():
 if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Old config was modified')
proof=dict(status='VERSIONED_CANDIDATES_LOCKED_GPU_AND_DATA_ACCEPTANCE_PENDING',configs=result,learning_rate=1e-5,
 target_global_batch=32,epochs=5,per_device_batch=1,planned_data_parallel_size=4,candidate_GA=8,
 launch_gate='Measure actual native data parallel group D; require32 % D ==0 and GA=32/D before training. World size is not assumed to equal DP size.',
 precision='BF16 mixed; FP32 master weights/Adam states required at actual ZeRO optimizer acceptance',
 optimizer='AdamW',scheduler='Cosine',warmup_ratio=.05,weight_decay=0,
 context_policy='Actual256K acceptance first;128K candidate only if256K fails with retained evidence',
 supervision='Full Thinking+Action; each original Assistant target once; input-only history/Observation/System/User/padding',
 dataset_freeze_required=True,gpu_acceptance_passed=False,new_gpu_processes=0,training_started=False,old_configs_unchanged=True,
 old_config_sha256=old_files,deepspeed_config_sha256=hashlib.sha256((W/'configs/ds_z3.json').read_bytes()).hexdigest())
(R/'checks/TRAINING_RECIPE_B32_E5_R1.json').write_text(json.dumps(proof,indent=2))
print(json.dumps(proof))
