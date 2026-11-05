"""Fixed four-arm native resume, fenced behind actual formal801 termination."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
P=R/'old-four-arm'
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
PY=R/'env/train-r1/bin/python'


def admitted():
    path=C/'REMOTE_NATIVE_EVAL_STATUS.json'
    status=json.loads(path.read_text())if path.exists()else{}
    complete=status.get('modes',{}).get('formal-n3',{}).get('complete')or{}
    models=[]
    for name in ['new-m1-cf416-128k-e5','new-m2-tmax356-128k-e5']:
        proof=R/'runs'/name/'FINAL_HF_ADMISSION.json'
        models.append(proof.exists()and json.loads(proof.read_text()).get('passed',False))
    return dict(admitted=complete.get('actual_terminal')==801 and all(models),
        actual_formal_terminal=complete.get('actual_terminal',0),new_m1_m2_final_hf=models,
        source_order='NewM1 -> NewM2 -> formal801 -> old four',old_model_training_dispatched=False)


def main(check_only):
    gate=admitted()
    if check_only:print(json.dumps(gate));return
    assert gate['admitted'],'Old study may not occupy GPUs before the new-model formal evaluation'
    sys.path.insert(0,str(P/'source/repository'))
    os.environ['OPENHARNESS_SFT_WORKSPACE']=str(P)
    from sft.runtime.checkpoint_archive import validate_checkpoint
    manifest=json.loads((P/'manifests/experiments.json').read_text())
    assert manifest['supersedes_all_prior_five_arm_plans'] and set(manifest['arms'])==set('ABCD')
    env=os.environ|dict(PYTHONPATH=str(P/'source/repository'),OPENHARNESS_SFT_WORKSPACE=str(P),
        PATH=str(PY.parent)+':'+os.environ.get('PATH','/usr/bin:/bin'),
        OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',HF_HUB_OFFLINE='1',
        TRANSFORMERS_OFFLINE='1',HF_DATASETS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',
        TMPDIR=str(R/'tmp'),TRITON_CACHE_DIR=str(R/'cache/triton'),
        TORCH_EXTENSIONS_DIR=str(R/'cache/torch_extensions'),HF_HOME=str(R/'cache/hf'))
    selected=manifest['authorized_gpu_uuids'][:4]
    with(C/'sequence-writer.lock').open('a')as writer:
        fcntl.flock(writer,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for arm in 'ABCD':
            plan=manifest['arms'][arm];output=Path(plan['output_dir']);resume=None
            completed=[]
            if output.exists():
                for path in output.glob('checkpoint-*'):
                    if not(path/'CHECKPOINT_COMPLETE.json').exists():continue
                    state=validate_checkpoint(path,require_marker=True)
                    assert state['max_steps']==530
                    identity=json.loads((path/'CHECKPOINT_COMPLETE.json').read_text())['identity']
                    assert identity['world_size']==4 and identity['config_sha256']==plan['config_sha256']
                    completed.append((state['global_step'],path))
                assert completed,'Existing arm has no valid checkpoint; never reinitialize it silently'
                step,resume=max(completed)
                if step==530:
                    subprocess.run([str(PY),str(R/'verify-old-arm-native-r1.py'),arm,'530'],env=env,check=True)
                    continue
            command=[str(PY),'-m','studies.qwen35_m2_full_causal.launch_arm','--evidence',str(P),
                '--arm',arm,'--gpu-uuids']+selected
            if resume is not None:command+=['--resume',str(resume)]
            with(P/'checks/native-resume-r2.jsonl').open('a')as log:
                log.write(json.dumps(dict(at=time.time(),arm=arm,resume=str(resume)if resume else None,
                    command=command,original_scheduler_horizon=530,no_acceptance_replay=True))+'\n')
            subprocess.run(command,env=env,check=True)
            subprocess.run([str(PY),str(R/'verify-old-arm-native-r1.py'),arm,'530'],env=env,check=True)
        (P/'checks/FOUR_NATIVE_TRAINING_RUNS_COMPLETED').write_text(str(time.time())+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');args=p.parse_args();main(args.check_only)
