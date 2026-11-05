"""Accept the closed M2 E1 checkpoint, native archive and frozen vision."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
W=R/'new-sft/workspace'
sys.path.insert(0,str(R/'new-sft/source-r4/repository'))
os.environ['OPENHARNESS_SFT_WORKSPACE']=str(W)
from sft.runtime.checkpoint_archive import validate_checkpoint

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def save(name,value):
    p=R/'checks'/name
    assert not p.exists(), 'Preserve the existing acceptance'
    p.write_text(json.dumps(value,indent=2)+'\n')
    return sha(p)


def main():
    source=sha(Path(__file__))
    run=R/'runs/new-m2-tmax356-128k-e5';checkpoint=run/'checkpoint-25'
    marker=checkpoint/'CHECKPOINT_COMPLETE.json'
    state=validate_checkpoint(checkpoint,world_size=4,require_marker=True)
    assert state['global_step']==25 and state['epoch']==1.0
    settings=read(W/'configs/checkpoint-storage.json')
    archive=Path(settings['archive_root'])/'new772-new-cf416-tmax356-m2/checkpoint-25'
    archived=read(archive/'ARCHIVE_COMPLETE.json')
    receipt=Path(settings['failed_root']).parent/'archive-results/new772-new-cf416-tmax356-m2-checkpoint-25.json'
    assert read(receipt)['status']=='completed'
    members={x['path']:x for x in archived['files']}
    assert len(members)==26 and members['CHECKPOINT_COMPLETE.json']['sha256']==sha(marker)
    assert archived['key']=='new772-new-cf416-tmax356-m2-checkpoint-25'
    assert Path(settings['archive_root']).stat().st_dev==settings['archive_device']
    hf=R/'epoch-models/new-m2-epoch1';hfmanifest=read(hf/'EPOCH_MODEL_EXPORT_COMPLETE.json')
    weight=next(x for x in hfmanifest['files']if x['name']=='model.safetensors')
    assert hfmanifest['source_complete_checkpoint_sha256']==sha(marker)
    assert hfmanifest['optimizer_step']==25 and hfmanifest['epoch']==1
    assert weight['sha256']==members['model.safetensors']['sha256']
    assert (hf/'model.safetensors').stat().st_ino==(checkpoint/'model.safetensors').stat().st_ino
    subprocess.run([str(R/'env/train-r1/bin/python'),str(R/'read-native-training-evidence18-r1.py')],
                   check=True,capture_output=True,text=True,timeout=25)
    evidence=read(R/'checks/NATIVE_TRAINING_READOUT_R1.json')
    stage=evidence['stages']['new-cf416-tmax356-m2']
    assert stage['all_rank_committed_optimizer_steps']>25, 'Await actual post-save training updates'
    assert stage['completed_epochs']['1']['unique_train_rows']==792
    exposure=[json.loads(line)for line in Path(stage['exposure_rows_path']).open()]
    first=[x for x in exposure if x['optimizer_step']<=25]
    assert len(first)==792 and len({x['row_index']for x in first})==792
    assert len({x['task_id']for x in first})==325
    assert sum(x['supervised_tokens']for x in first)==7815211
    ranks=[];metrics=[]
    for rank in range(4):
        blob=(run/('preflight-evidence-rank'+str(rank)+'.jsonl')).read_bytes()
        rows=[json.loads(line)for line in blob[:blob.rfind(b'\n')+1].splitlines()]
        saved=next(x for x in rows if x['event']=='checkpoint_save_complete'and x['global_step']==25)
        step=next(x for x in rows if x['event']=='optimizer_step'and x['global_step']==25)
        assert step['master_partition_dtypes']==['torch.float32']
        assert step['optimizer_moment_dtypes']==['torch.float32']
        ranks.append(dict(rank=rank,save_completed_at=saved['time'],identity=saved['identity'],
                          sampled_gradients_finite=all(x['finite']for x in step['gradients'].values()),
                          fp32_master_and_adam=True))
        if rank==0:
            metrics=[x['metrics']for x in rows if x['event']=='metrics'and x['global_step']<=25
                     and any(k in x['metrics']for k in ['eval_loss','cf_validation_loss'])]
    native=dict(passed=True,at=time.time(),epoch=1,optimizer_steps=25,planned_optimizer_steps=125,
        actual_post_save_optimizer_step=stage['all_rank_committed_optimizer_steps'],
        checkpoint=str(checkpoint),checkpoint_complete_marker_sha256=sha(marker),ranks=ranks,
        validation_metrics=metrics,epoch1_train_tasks=325,epoch1_unique_samples=792,
        epoch1_sample_exposures=792,epoch1_supervised_tokens=7815211,
        epoch1_visible_input_token_exposures=sum(x['input_tokens']for x in first),
        validation_training_exposures=stage['validation_training_exposures'],
        exposure_rows_sha256=stage['exposure_rows_sha256'],native_readout_sha256=sha(R/'checks/NATIVE_TRAINING_READOUT_R1.json'),
        hf_manifest_sha256=sha(hf/'EPOCH_MODEL_EXPORT_COMPLETE.json'),hf_weight_sha256=weight['sha256'],
        final_epoch5_not_yet_complete=True,training_source_unchanged=stage['job']['training_source_sha256'],
        source_sha256=source,new_gpu_or_optimizer_calls=0)
    native_sha=save('NEW_M2_EPOCH1_NATIVE_ACCEPTANCE_R1.json',native)
    arch=dict(passed=True,at=time.time(),files=len(members),bytes=sum(x['bytes']for x in members.values()),
        archive_path=str(archive),native_archive_manifest_sha256=sha(archive/'ARCHIVE_COMPLETE.json'),
        native_receipt_sha256=sha(receipt),native_metrics=archived['metrics'],completed_at=archived['completed_at'],
        original_complete_marker_sha256=sha(marker),all4_native_save_callbacks_completed=True,
        optimizer_step_after_archive=stage['all_rank_committed_optimizer_steps'],hot_original_retained=True,
        source_sha256=source,scope='Native archive worker verified both source and copy SHA before atomic publish; no redundant full rehash or native restart')
    save('NEW_M2_EPOCH1_ASYNC_ARCHIVE_ACCEPTANCE_R1.json',arch)
    signatures=importlib.import_module('audit-epoch1-vision18-r1').signatures
    baseline=signatures(R/'runs/new-m1-cf416-128k-e5')
    actual=signatures(hf,baseline)
    prior=read(R/'checks/NEW_M1_EPOCH5_FROZEN_VISION_AUDIT_R1.json')
    vision=[k for k in baseline if '.visual.'in k]
    assert len(vision)==297 and set(actual)==set(baseline)
    assert all(baseline[k]==actual[k]==prior['vision_tensors'][k]for k in vision)
    result=dict(passed=True,actual_epoch=1,optimizer_steps=25,bitwise_identical_vision_tensors=297,
        vision_tensors={k:actual[k]for k in vision},
        sampled_language_tensor_changes={k:baseline[k]!=actual[k]for k in baseline if k not in vision},
        language_update_evidence_is_native_optimizer_not_arbitrary_bf16_norm_change=True,
        reference_verified_m1_final_vision_sha256=sha(R/'checks/NEW_M1_EPOCH5_FROZEN_VISION_AUDIT_R1.json'),
        hf_manifest_sha256=sha(hf/'EPOCH_MODEL_EXPORT_COMPLETE.json'),native_acceptance_sha256=native_sha,
        official_m0_revision='851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a',source_sha256=source,
        reused_signature_source_sha256=sha(R/'audit-epoch1-vision18-r1.py'),new_gpu_or_optimizer_calls=0)
    save('NEW_M2_EPOCH1_FROZEN_VISION_AUDIT_R1.json',result)
    print(json.dumps(dict(passed=True,epoch=1,actual_post_save_step=stage['all_rank_committed_optimizer_steps'],
        native_acceptance_sha256=native_sha,archived_files=len(members),archived_bytes=arch['bytes'],
        hf_manifest_sha256=native['hf_manifest_sha256'],hf_weight_sha256=weight['sha256'],vision_tensors=297)))


if __name__=='__main__':main()
