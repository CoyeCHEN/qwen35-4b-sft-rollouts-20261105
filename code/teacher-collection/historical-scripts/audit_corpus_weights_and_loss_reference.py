"""Bind exact cache weights to the unchanged native phase1 loss evidence, CPU only."""
import ast,hashlib,json
from pathlib import Path
from sft.public_corpus import uniform_segment_mean_weights

R=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
P=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/lib/python3.11/site-packages')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
proofdir=R/'checks/stage1-adopted'
gpu=json.loads((proofdir/'qwen-liger-loss-gpu.json').read_text());assert gpu['passed']
loss_file=P/'liger_kernel/transformers/model/loss_utils.py';assert sha(loss_file)==gpu['source_sha256']
assert all(x['passed'] and x['reference_shift_count']==1 for x in gpu['cases'])
cpu=json.loads((proofdir/'causal-loss-cpu-r1.json').read_text());tail=json.loads((proofdir/'causal-loss-tail-cpu.json').read_text())
assert cpu['passed'] and tail['passed'] and all(x['model_accepts_loss_kwargs'] is False for x in cpu['cases']+tail['cases'])
model_file=P/'transformers/models/qwen3_5/modeling_qwen3_5.py';tree=ast.parse(model_file.read_text());found=False
for node in tree.body:
 if isinstance(node,ast.ClassDef) and node.name=='Qwen3_5ForConditionalGeneration':
  found=any(isinstance(v,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='accepts_loss_kwargs' for t in v.targets) and isinstance(v.value,ast.Constant) and v.value.value is False for v in node.body)
assert found
lf_file=P/'llamafactory/train/sft/trainer.py';assert 'self.model_accepts_loss_kwargs = False' in lf_file.read_text()
corpora={}
base=R/'staging/canary-qualified-r2'
for pool in ['calibforge','tmax']:
 root=base/pool;manifest=json.loads((root/'DATA_MANIFEST.json').read_text());views={}
 for cap in ['131072','262144']:
  path=root/('SAMPLE_MAPPING-'+cap+'.jsonl');assert sha(path)==manifest['artifacts'][path.name]
  mappings=[json.loads(x) for x in path.open()];splits={}
  for split in ['train','validation']:
   rows=[m for m in mappings if m['split']==split];weights=uniform_segment_mean_weights(rows)
   target_mass=[]
   for row,coefficient in zip(rows,weights['per_token_coefficients']):
    for target in row['decision_mapping']:
     left,right=target['supervised_range'];target_mass.append(dict(task_id=row['task_id'],trial_id=row['trial_id'],call_id=target['call_id'],row_index=row['row_index'],supervised_tokens=right-left,per_supervised_token_coefficient=coefficient,loss_mass=(right-left)*coefficient))
   if rows:assert abs(sum(x['loss_mass'] for x in target_mass)-1)<1e-9
   splits[split]=dict(task_segment_share=weights['task_segment_share'],task_supervised_token_share=weights['task_supervised_token_share'],targets=target_mass)
  views[cap]=dict(mapping_sha256=sha(path),splits=splits)
 corpora[pool]=dict(manifest_sha256=sha(root/'DATA_MANIFEST.json'),views=views)
report=dict(passed=True,status='PARTIAL_CANARY_WEIGHTS_AND_NATIVE_LOSS_REFERENCE_BOUND',corpora=corpora,
 reference_proofs={p.name:sha(p) for p in proofdir.glob('*.json')},
 native_runtime_files={str(p):sha(p) for p in [loss_file,model_file,lf_file,P/'transformers/trainer.py']},
 qwen_class_accepts_loss_kwargs=False,lf_processor_path_accepts_loss_kwargs=False,
 objective='At microbatch1, LF/Qwen path averages supervised tokens within each segment then averages segment losses. Uniform one-visit corpus weights shown; distributed sampler padding/final partial updates remain part of the separate training batch contract.',
 existing_gpu_evidence_scope=gpu['scope'],new_gpu_execution=False,new_model_loaded=False,new_teacher_calls=0,
 existing_cpu_evidence_scope=cpu['scope'],
 masked_context_and_eos='All final canary cache labels already checked through native Loader/Collator; adopted phase1 numerical references verify shift-once and mask/gradient semantics.',
 old_training_trajectories_loaded_or_admitted=False,
 raw_caches_and_original_data_manifests_changed=False,
 limitation='Reuses exact installed native Qwen/Liger loss-function GPU evidence and native LF CPU DDP/GA evidence; does not claim a full Qwen4B/ZeRO3 forward/backward test on these new long samples.')
p=base/'WEIGHTS_AND_LOSS_REFERENCE_AUDIT_R3.json'
with p.open('x') as stream:stream.write(json.dumps(report,indent=2))
print(json.dumps(dict(passed=True,new_gpu_execution=False,new_teacher_calls=0,pools={pool:{cap:{split:{k:v[k] for k in ['task_segment_share','task_supervised_token_share']} for split,v in x['splits'].items()} for cap,x in y['views'].items()} for pool,y in corpora.items()})))
