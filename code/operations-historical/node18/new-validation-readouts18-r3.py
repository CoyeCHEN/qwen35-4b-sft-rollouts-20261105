"""Six preregistered epoch validation readouts using the existing finite scorer."""
import importlib
import hashlib
import json
from pathlib import Path
import subprocess
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
snapshot=importlib.import_module('snapshot-epoch-hf18-r2')
gpu5=importlib.import_module('gpu5_readiness18_r1')
GPU='GPU-7b634c3e-13ae-5243-19dd-b6edddf9a543'
PLAN=[(stage,run,per_epoch,epoch,pools)for stage,run,per_epoch,pools in [
    ('new-m1','new-m1-cf416-128k-e5',40,['calibforge']),
    ('new-m2','new-m2-tmax356-128k-e5',25,['tmax','calibforge'])]for epoch in (1,3,5)]


def final_hf_ready_for_nll(source,step):
    # Teacher-forced NLL requires the sealed, completed model, not Agent success.
    export=source/'HF_EXPORT_COMPLETE.json';cold=source/'HF_LOAD_SMOKE.json'
    checkpoint=source/('checkpoint-'+str(step))/'CHECKPOINT_COMPLETE.json'
    if not all(path.exists()for path in [export,cold,checkpoint]):return False
    manifest=json.loads(export.read_text());loaded=json.loads(cold.read_text())
    trainer=json.loads((source/'trainer_state.json').read_text())
    assert manifest['complete_final_hf']and loaded['model_loaded']and loaded['generated_tokens']>0
    assert loaded['export_manifest_sha256']==hashlib.sha256(export.read_bytes()).hexdigest()
    assert trainer['global_step']==step and trainer['epoch']==5
    return True


def advance(state):
    observed=[]
    for stage,run,per_epoch,epoch,pools in PLAN:
        tag=stage+'-epoch'+str(epoch)
        output=R/'nll-audits'/tag
        complete=output/'NLL_AUDIT_COMPLETE.json'
        if complete.exists():
            proof=json.loads(complete.read_text())
            if not proof['passed'] or set(proof['summaries'])!=set(pools):
                raise ValueError('NLL completion identity differs: '+tag)
            if any(v['unique_rows']!={'calibforge':146,'tmax':86}[p]for p,v in proof['summaries'].items()):
                raise ValueError('NLL unique-row coverage differs: '+tag)
            observed.append(dict(tag=tag,status='complete',proof=str(complete)))
            continue
        unit='qwen35-new772-full-nll-'+tag+'-20261101-r1.service'
        properties=dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,
            '-p','LoadState','-p','MainPID','-p','ActiveState','-p','Result'],text=True).splitlines())
        if properties['ActiveState']=='active':
            observed.append(dict(tag=tag,status='native_audit_running',unit=properties));break
        if output.exists() or properties['LoadState']!='not-found':
            observed.append(dict(tag=tag,status='prior_native_audit_requires_inspection',unit=properties));break
        source=R/'runs'/run
        if epoch==5:
            if not final_hf_ready_for_nll(source,per_epoch*epoch):continue
            model=source
        else:
            if not(source/('checkpoint-'+str(per_epoch*epoch))/'CHECKPOINT_COMPLETE.json').exists():continue
            model=R/'epoch-models'/tag
            if not model.exists():snapshot.snapshot(stage,epoch)
        readiness=gpu5.inspect()
        if not readiness['ready']:
            observed.append(dict(tag=tag,status='waiting_for_idle_authorized_audit_gpu5',gpu_readiness=readiness));break
        command=['systemd-run','--user','--unit='+unit,'--property=MemoryMax=96G',
            '--property=StandardOutput=append:'+str(R/'logs'/('nll-'+tag+'.log')),
            '--property=StandardError=append:'+str(R/'logs'/('nll-'+tag+'.log')),
            str(R/'env/train-r1/bin/python'),str(R/'score-frozen-validation18-r3.py'),
            '--model',str(model),'--tag',tag,'--pools']+pools
        subprocess.run(command,check=True,capture_output=True,text=True)
        observed.append(dict(tag=tag,status='native_finite_audit_submitted',gpu_uuid=GPU,pools=pools))
        break
    state['unique_validation_readouts']=observed
    target=C/'NATIVE_UNIQUE_VALIDATION_READOUT_STATUS.json'
    temp=target.with_name(target.name+'.tmp')
    temp.write_text(json.dumps(dict(at=time.time(),readouts=observed,planned=6,
        actual_complete=sum(x['status']=='complete'for x in observed),
        m2_must_include_fixed_cf_validation=True,no_weight_or_recipe_selection=True),indent=2)+'\n');temp.replace(target)
