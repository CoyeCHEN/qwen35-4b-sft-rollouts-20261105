"""Create isolated new-route configuration, reuse environment/storage services.

Never submits a job, authorizes training, copies weights, or approves data.
"""
import json
import os
from pathlib import Path
import shutil

import yaml

from sft.runtime.config import initialize,validate_native,native_arguments
from sft.runtime.paths import PUBLIC_STAGES
from sft.runtime.checkpoint_archive import sha256,atomic_json

EVIDENCE=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
ROOT=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/workspace')
OLD=Path('/ssd/chenkeyi/qwen35-calibforge-ab-20261027')
MODEL=Path('/data/models/Qwen/Qwen3.5-4B')
storage=json.loads((OLD/'configs/checkpoint-storage.json').read_text())
uuids=['GPU-bb31693b-95f6-4416-ec41-dd75511c2c59','GPU-0db8aea7-b003-06fb-d197-d047c1d67bcb',
       'GPU-d2499600-e80e-4fb8-40ef-b6f0f919d2d8','GPU-00f3c3df-16e0-f31f-4066-bdee4c8cdff2']
initialize(ROOT,MODEL,storage['hot_root'],Path(storage['archive_root']).parent,uuids)
os.environ['OPENHARNESS_SFT_WORKSPACE']=str(ROOT)
# The already running native archive path/worker consumes the same hot queue.
# No second timer or controller is installed; no old output/config is changed.
atomic_json(ROOT/'configs/checkpoint-storage.json',storage)
shutil.copyfile(OLD/'checks/model-identity.json',ROOT/'checks/model-identity.json')
runtime=json.loads((ROOT/'configs/runtime.json').read_text())
runtime.update(training_plan='new_cf500_tmax500',training_recipe='calibforge_appendix_e',
    campaign_id=EVIDENCE.name,planned_gpu_ids=['0','1','2','3'],hot_root=storage['hot_root'],
    goal_authorized=True,
    tool_contract=str(ROOT/'configs/public-tool-contract.json'),
    project_training_lock='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-sft-preflight-20261023/runs/training.lock',
    public_stage_gpu_evidence={},source_checkout=str(EVIDENCE/'sources/sft-stage-gates-20261030T0115'),
    formal_training_authorized=False,formal_authorized_stage=None,
    authorization_basis='Latest user Goal authorizes gated new CF500 M1 then TMax500 M2; this script does not pass or bypass readiness')
atomic_json(ROOT/'configs/runtime.json',runtime)
offline=json.loads((EVIDENCE/'checks/ten-tool-finish-off-offline.json').read_text())
contract=dict(status='FROZEN_PENDING_LIVE_VALIDATION',finish=False,tools=offline['tool_names'],
    schema_sha256=[offline['codec_provider_tools_sha256']],system_prompt_sha256=offline['system_prompt_sha256'],
    teacher_config_sha256=offline['teacher_config_sha256'],offline_proof_sha256=sha256(EVIDENCE/'checks/ten-tool-finish-off-offline.json'),
    native_token_observation_enabled=True,real_runtime_proof=None)
atomic_json(ROOT/'configs/public-tool-contract.json',contract)
base=yaml.safe_load((ROOT/'configs/m2-128k.yaml').read_text())
common=dict(runtime_recipe='calibforge_appendix_e',learning_rate=1e-5,num_train_epochs=10,
    gradient_accumulation_steps=32,weight_decay=0.0,warmup_ratio=0.05,mask_history=False,
    save_strategy='epoch',eval_strategy='epoch',save_total_limit=None,load_best_model_at_end=False,
    eval_on_start=True,lr_scheduler_kwargs={})
outputs={stage:Path(storage['hot_root'])/'runs'/stage for stage in PUBLIC_STAGES}
parsed={}
for index,stage in enumerate(PUBLIC_STAGES):
    config=base|common|dict(model_name_or_path=str(MODEL if index==0 else outputs[PUBLIC_STAGES[0]]),
        tokenized_path=str(ROOT/'data'/stage),output_dir=str(outputs[stage]),
        dataset=stage+'-train',eval_dataset=stage+'-validation')
    assert not outputs[stage].exists(),'An existing run directory must never be overwritten'
    validate_native(config)
    destination=ROOT/'configs'/f'{stage}.yaml';destination.write_text(yaml.safe_dump(config,sort_keys=False))
    from llamafactory.hparams import get_train_args
    get_train_args(native_arguments(config)|dict(use_cpu=True,deepspeed=None))
    parsed[stage]=dict(passed=True,config_path=str(destination),config_sha256=sha256(destination),
        initialization=config['model_name_or_path'],output_dir=config['output_dir'],
        planned_optimizer_steps=None,reason='Actual qualified training trajectories/segments are not frozen yet')
for unused in ['configs/m1-64k.yaml','configs/m2-128k.yaml','configs/m2-96k.yaml',
               'configs/m2-tool-contract.json','manifests/m2-approved-sources.json']:
    (ROOT/unused).unlink()  # Only defaults created by initialize above in this new workspace.
proof=dict(passed=True,configs=parsed,workspace=str(ROOT),models_copied=0,environments_created=0,
    jobs_submitted=0,timers_created=0,archive_worker_reused=storage['archive_service'],
    recipe_basis='Previously user-frozen CalibForge Appendix E candidate; not asserted optimal or GPU accepted',
    loss_policy='all_assistant_once; retain the inherited candidate, do not silently substitute current-assistant-only',
    fresh_dataset_required=True,new_training_authorized_by_this_script=False)
atomic_json(EVIDENCE/'checks/new-public-stage-config-parsing.json',proof)
print(json.dumps(proof))
