"""Export a complete epoch3 native checkpoint for diagnostics without touching its shards."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
ASSETS={
 'tokenizer_config.json':'3dd1cee8a0cb8f51800bcb47bd157eeef5bda2d39c85b7569892b9af95170071',
 'tokenizer.json':'5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42',
 'chat_template.jinja':'a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715',
 'vocab.json':'ce99b4cb2983d118806ce0a8b777a35b093e2000a503ebde25853284c9dfa003',
 'merges.txt':'a9d356d7bdf1ef4949e3e748e95b8e10ad9d4e2e838eddc38a0a7b6b94d1db8d',
 'preprocessor_config.json':'27225450ac9c6529872ee1924fcb0962ff5634834f817040f444118116f4e516',
 'video_preprocessor_config.json':'7768af27c1fafa9cc9011c1dc20067e03f8915e03b63504550e11d5066986d13'}

def sha(p):
    h=hashlib.sha256()
    with p.open('rb')as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def snapshot(stage,epoch=3):
    assert epoch in (1,3)
    run,per_epoch={'new-m1':('new-m1-cf416-128k-e5',40),'new-m2':('new-m2-tmax356-128k-e5',25)}[stage]
    step=per_epoch*epoch
    source=R/'runs'/run/('checkpoint-'+str(step))
    marker=source/'CHECKPOINT_COMPLETE.json'
    assert marker.exists(),'Wait for complete native checkpoint; never copy an in-flight save'
    state=json.loads((source/'trainer_state.json').read_text())
    assert state['global_step']==step and epoch-.01<=state['epoch']<=epoch+.01
    target=R/'epoch-models'/(stage+'-epoch'+str(epoch))
    if target.exists():
        proof=json.loads((target/'EPOCH_MODEL_EXPORT_COMPLETE.json').read_text())
        assert proof['source_complete_checkpoint_sha256']==sha(marker)
        assert all(sha(target/f['name'])==f['sha256']for f in proof['files'])
        return str(target)
    index=source/'model.safetensors.index.json'
    weights=set(json.loads(index.read_text())['weight_map'].values())if index.exists()else{'model.safetensors'}
    stage_dir=target.with_name(target.name+'.staging')
    assert not stage_dir.exists(),'Preserve interrupted diagnostic staging for inspection'
    stage_dir.mkdir(parents=True)
    for name in sorted(weights):
        p=source/name
        assert p.is_file()and not p.is_symlink()and p.parent==source
        os.link(p,stage_dir/name)
    for name in ['config.json','model.safetensors.index.json','generation_config.json']:
        if(source/name).exists():shutil.copyfile(source/name,stage_dir/name)
    for name,expected in ASSETS.items():
        p=R/'assets/source17-r1/student-tokenizer'/name
        assert sha(p)==expected,'Canonical tokenizer/processor asset changed: '+name
        shutil.copyfile(p,stage_dir/name)
    files=[dict(name=p.name,bytes=p.stat().st_size,sha256=sha(p))for p in sorted(stage_dir.iterdir())]
    proof=dict(kind='CANONICAL_INTERMEDIATE_EPOCH_HF_EXPORT',stage=stage,epoch=epoch,optimizer_step=step,
        source_checkpoint=str(source),source_complete_checkpoint_sha256=sha(marker),files=files,
        native_checkpoint_untouched=True,weight_files_are_immutable_same_ssd_hardlinks=True,
        is_final_epoch5_model=False,remaining_training_epochs_must_continue=True,
        official_m0_revision='851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a')
    (stage_dir/'EPOCH_MODEL_EXPORT_COMPLETE.json').write_text(json.dumps(proof,indent=2)+'\n')
    stage_dir.rename(target)
    return str(target)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['new-m1','new-m2']);p.add_argument('--epoch',type=int,choices=[1,3],default=3);args=p.parse_args()
    print(snapshot(args.stage,args.epoch))
